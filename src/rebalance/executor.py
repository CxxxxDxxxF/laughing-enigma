"""Rebalance execution bridge.

This module provides a deterministic bridge that converts RebalancePlan trade intents
into executable Signals and runs them through PaperExecutionEngine.

Determinism guarantees:
- Same plan + same prices → same signals
- Deterministic rounding (explicit rule)
- Deterministic execution order
- Continue-on-error: errors recorded but execution continues
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import math

from .planner import RebalancePlan, TradeIntent, TradeDirection, RebalanceError
from ..execution import Signal, SignalType, PaperExecutionEngine, Order, Fill
from ..core.artifacts import ArtifactStore
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..lifecycle.runner import ExecutionMode


class RebalanceExecutionError(Exception):
    """Error raised when rebalance execution fails."""
    pass


# Rounding methods are strings: "floor", "round", "ceil"


@dataclass
class IntentExecutionResult:
    """Result of executing a single trade intent.
    
    Attributes:
        intent_id: Identifier for the trade intent (strategy_id)
        intent: Original trade intent
        signal: Signal generated (None if generation failed)
        order: Order created (None if order submission failed)
        fills: List of fills (empty if execution failed)
        success: Whether intent was successfully executed
        error: Error message if execution failed
    """
    
    intent_id: str
    intent: TradeIntent
    signal: Optional[Signal] = None
    order: Optional[Order] = None
    fills: List[Fill] = None
    success: bool = False
    error: Optional[str] = None
    
    def __post_init__(self):
        """Initialize fills list if None."""
        if self.fills is None:
            self.fills = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "intent_id": self.intent_id,
            "intent": self.intent.to_dict(),
            "signal": {
                "timestamp": self.signal.timestamp.isoformat(),
                "instrument": self.signal.instrument,
                "signal_type": self.signal.signal_type.value,
                "quantity": self.signal.quantity,
                "price_limit": self.signal.price_limit,
                "strategy_id": self.signal.strategy_id,
                "metadata": self.signal.metadata,
            } if self.signal else None,
            "order": self.order.to_dict() if self.order else None,
            "fills": [fill.to_dict() for fill in self.fills],
            "success": self.success,
            "error": self.error,
        }


@dataclass
class RebalanceExecutionResult:
    """Result of executing a rebalance plan.
    
    Attributes:
        execution_id: Unique identifier for this execution
        execution_timestamp: When execution was performed
        plan_id: ID of the RebalancePlan executed
        intent_results: List of execution results (one per intent)
        execution_summary: Summary statistics
        mapping: Mapping of intent_id → signal_id → order_id → fill_ids
    """
    
    execution_id: str
    execution_timestamp: datetime
    plan_id: str
    intent_results: List[IntentExecutionResult]
    execution_summary: Dict[str, Any]
    mapping: Dict[str, Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "execution_id": self.execution_id,
            "execution_timestamp": self.execution_timestamp.isoformat(),
            "plan_id": self.plan_id,
            "intent_results": [ir.to_dict() for ir in self.intent_results],
            "execution_summary": self.execution_summary,
            "mapping": self.mapping,
        }


class RebalanceSignalMapper:
    """Maps TradeIntent to Signal objects for execution.
    
    This mapper converts trade intents (capital amounts) into execution-ready
    Signals (quantities) using deterministic price-based sizing.
    
    Attributes:
        rounding_method: Rounding method for quantity calculation
                        ("floor", "round", or "ceil")
        min_quantity: Minimum quantity (default: 0.0)
        
    Determinism:
        Same intent + same price → same signal
        Rounding is deterministic (no floating point ambiguity)
    """
    
    def __init__(self, rounding_method: str = "floor", min_quantity: float = 0.0):
        """Initialize signal mapper.
        
        Args:
            rounding_method: Rounding method ("floor", "round", or "ceil")
            min_quantity: Minimum quantity (trades below this are rejected)
            
        Raises:
            ValueError: If rounding_method is invalid
        """
        if rounding_method not in ("floor", "round", "ceil"):
            raise ValueError(
                f"rounding_method must be 'floor', 'round', or 'ceil', got: {rounding_method}"
            )
        
        self.rounding_method = rounding_method
        self.min_quantity = min_quantity
    
    def map_intent_to_signal(
        self,
        intent: TradeIntent,
        price: float,
        instrument: str,
        timestamp: Optional[datetime] = None
    ) -> Signal:
        """Map trade intent to execution signal.
        
        Process:
        1. Convert amount to quantity using price
        2. Apply rounding rule
        3. Check minimum quantity
        4. Map direction to SignalType
        5. Create Signal
        
        Args:
            intent: Trade intent to map
            price: Price per unit for quantity calculation
            instrument: Instrument identifier
            timestamp: Optional signal timestamp (defaults to now)
            
        Returns:
            Signal object ready for execution
            
        Raises:
            RebalanceExecutionError: If quantity rounds to zero or below minimum
        """
        if price <= 0:
            raise RebalanceExecutionError(f"Price must be positive, got: {price}")
        
        if intent.direction == TradeDirection.HOLD:
            raise RebalanceExecutionError("Cannot map HOLD intent to signal")
        
        # Convert amount to quantity
        raw_quantity = intent.amount / price
        
        # Apply rounding
        if self.rounding_method == "floor":
            quantity = math.floor(raw_quantity)
        elif self.rounding_method == "round":
            quantity = round(raw_quantity)
        elif self.rounding_method == "ceil":
            quantity = math.ceil(raw_quantity)
        else:
            raise RebalanceExecutionError(f"Invalid rounding method: {self.rounding_method}")
        
        # Check minimum quantity
        if quantity < self.min_quantity:
            raise RebalanceExecutionError(
                f"Quantity {quantity} below minimum {self.min_quantity} for intent {intent.strategy_id}"
            )
        
        # Check if quantity rounds to zero
        if quantity == 0:
            raise RebalanceExecutionError(
                f"Quantity rounds to zero for intent {intent.strategy_id} "
                f"(amount={intent.amount}, price={price})"
            )
        
        # Map direction to SignalType
        if intent.direction == TradeDirection.BUY:
            signal_type = SignalType.BUY
        elif intent.direction == TradeDirection.SELL:
            signal_type = SignalType.SELL
        else:
            raise RebalanceExecutionError(f"Unknown trade direction: {intent.direction}")
        
        # Create signal timestamp
        if timestamp is None:
            timestamp = datetime.now()
        
        # Create signal
        signal = Signal(
            timestamp=timestamp,
            instrument=instrument,
            signal_type=signal_type,
            quantity=float(quantity),  # Ensure float type
            price_limit=None,  # Market orders for rebalance
            strategy_id=intent.strategy_id,
            metadata={
                "rebalance_intent_id": intent.strategy_id,
                "original_amount": intent.amount,
                "price": price,
                "rounding_method": self.rounding_method,
            }
        )
        
        return signal


def execute_rebalance_plan(
    plan: RebalancePlan,
    execution_engine: PaperExecutionEngine,
    price_by_strategy_or_instrument: Dict[str, float],
    mapper: Optional[RebalanceSignalMapper] = None,
    execution_id: Optional[str] = None,
    execution_timestamp: Optional[datetime] = None,
    execution_mode: Optional['ExecutionMode'] = None
) -> RebalanceExecutionResult:
    """Execute a rebalance plan through paper execution engine.
    
    Process:
    1. For each trade intent (skip HOLD):
       a. Get price for strategy/instrument
       b. Map intent to signal using mapper
       c. Submit signal to execution engine (creates order)
       d. Execute order at provided price
       e. Capture results
    2. Build intent → signal → order → fill mapping
    3. Compute execution summary
    4. Return execution result
    
    Failure handling (continue-on-error):
    - Missing price: Record error, continue
    - Quantity rounds to zero: Record error, continue
    - Risk limit rejection: Record error, continue
    - All errors are captured in IntentExecutionResult
    
    Determinism guarantees:
    - Same plan + same prices → same signals
    - Deterministic execution order (intent order)
    - Same mapper config → same rounding
    
    Args:
        plan: RebalancePlan to execute
        execution_engine: PaperExecutionEngine to execute through
        price_by_strategy_or_instrument: Dictionary mapping strategy_id or instrument → price
        mapper: Optional signal mapper (default: RebalanceSignalMapper with floor rounding)
        execution_id: Optional execution identifier (required in LIVE mode)
        execution_timestamp: Optional execution timestamp (required in LIVE mode)
        execution_mode: Optional execution mode (ExecutionMode enum, for validation)
        
    Returns:
        RebalanceExecutionResult with execution results and mapping
        
    Raises:
        RebalanceExecutionError: If execution setup fails (not per-intent errors) or LIVE mode validation fails
        
    Example:
        >>> prices = {"strat_1": 150.0, "strat_2": 200.0}
        >>> result = execute_rebalance_plan(plan, engine, prices)
        >>> print(f"Successful: {result.execution_summary['successful_intents']}")
        >>> print(f"Failed: {result.execution_summary['failed_intents']}")
    """
    # Validate LIVE/LIVE_DRY mode requirements
    if execution_mode is not None:
        # Check for LIVE or LIVE_DRY mode (string comparison to avoid circular import)
        if str(execution_mode) in ("live", "live_dry"):
            if execution_id is None:
                raise RebalanceExecutionError("LIVE mode requires explicit execution_id")
            if execution_timestamp is None:
                raise RebalanceExecutionError("LIVE mode requires explicit execution_timestamp")
    
    # Generate execution_id if not provided (SIMULATION mode only)
    if execution_id is None:
        execution_id = f"rebalance_exec_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Use provided timestamp or fallback to now (SIMULATION mode only)
    if execution_timestamp is None:
        execution_timestamp = datetime.now()
    
    if mapper is None:
        mapper = RebalanceSignalMapper(rounding_method="floor")
    
    intent_results: List[IntentExecutionResult] = []
    mapping: Dict[str, Dict[str, Any]] = {}
    
    # Extract instrument from execution engine (assumes single instrument per engine)
    instrument = execution_engine.instrument
    
    # Execute each intent (skip HOLD)
    for intent in plan.trade_intents:
        if intent.direction == TradeDirection.HOLD:
            # Skip HOLD intents
            result = IntentExecutionResult(
                intent_id=intent.strategy_id,
                intent=intent,
                success=True,  # HOLD is successful by definition
                error=None
            )
            intent_results.append(result)
            continue
        
        # Try to get price
        price = None
        try:
            # Try strategy_id first, then instrument
            price = price_by_strategy_or_instrument.get(intent.strategy_id)
            if price is None:
                price = price_by_strategy_or_instrument.get(instrument)
            
            if price is None:
                raise RebalanceExecutionError(
                    f"Price not found for intent {intent.strategy_id} "
                    f"(tried strategy_id and instrument={instrument})"
                )
        except Exception as e:
            # Missing price - record error and continue
            result = IntentExecutionResult(
                intent_id=intent.strategy_id,
                intent=intent,
                success=False,
                error=f"Price lookup failed: {e}"
            )
            intent_results.append(result)
            continue
        
        # Map intent to signal
        signal = None
        try:
            signal = mapper.map_intent_to_signal(
                intent=intent,
                price=price,
                instrument=instrument,
                timestamp=plan.plan_timestamp
            )
        except Exception as e:
            # Signal generation failed (quantity rounds to zero, etc.)
            result = IntentExecutionResult(
                intent_id=intent.strategy_id,
                intent=intent,
                success=False,
                error=f"Signal generation failed: {e}"
            )
            intent_results.append(result)
            continue
        
        # Submit signal (creates order)
        order = None
        try:
            order = execution_engine.submit_order(signal)
        except Exception as e:
            # Order submission failed (risk limits, etc.)
            result = IntentExecutionResult(
                intent_id=intent.strategy_id,
                intent=intent,
                signal=signal,
                success=False,
                error=f"Order submission failed: {e}"
            )
            intent_results.append(result)
            continue
        
        # Execute order
        fills = []
        try:
            fills = execution_engine.execute_order(order, price, timestamp=plan.plan_timestamp)
        except Exception as e:
            # Order execution failed
            result = IntentExecutionResult(
                intent_id=intent.strategy_id,
                intent=intent,
                signal=signal,
                order=order,
                success=False,
                error=f"Order execution failed: {e}"
            )
            intent_results.append(result)
            continue
        
        # Success
        result = IntentExecutionResult(
            intent_id=intent.strategy_id,
            intent=intent,
            signal=signal,
            order=order,
            fills=fills,
            success=True,
            error=None
        )
        intent_results.append(result)
        
        # Build mapping
        mapping[intent.strategy_id] = {
            "signal_id": f"{signal.timestamp.isoformat()}_{signal.instrument}_{signal.signal_type.value}",
            "order_id": order.id,
            "fill_ids": [fill.id for fill in fills],
        }
    
    # Compute execution summary
    successful = [r for r in intent_results if r.success]
    failed = [r for r in intent_results if not r.success]
    
    total_intents = len(plan.trade_intents)
    successful_intents = len(successful)
    failed_intents = len(failed)
    
    total_fills = sum(len(r.fills) for r in intent_results)
    total_volume = sum(sum(fill.quantity * fill.price for fill in r.fills) for r in successful)
    
    execution_summary = {
        "total_intents": total_intents,
        "successful_intents": successful_intents,
        "failed_intents": failed_intents,
        "success_rate": successful_intents / total_intents if total_intents > 0 else 0.0,
        "total_fills": total_fills,
        "total_volume": total_volume,
        "error_summary": {
            "missing_price": sum(1 for r in failed if "Price lookup" in (r.error or "")),
            "signal_generation": sum(1 for r in failed if "Signal generation" in (r.error or "")),
            "order_submission": sum(1 for r in failed if "Order submission" in (r.error or "")),
            "order_execution": sum(1 for r in failed if "Order execution" in (r.error or "")),
        }
    }
    
    return RebalanceExecutionResult(
        execution_id=execution_id,
        execution_timestamp=execution_timestamp,
        plan_id=plan.plan_id,
        intent_results=intent_results,
        execution_summary=execution_summary,
        mapping=mapping
    )


def persist_rebalance_execution(
    result: RebalanceExecutionResult,
    artifact_store: ArtifactStore
) -> str:
    """Persist rebalance execution result to artifact store.
    
    Args:
        result: RebalanceExecutionResult to persist
        artifact_store: ArtifactStore instance
        
    Returns:
        Execution identifier
        
    Raises:
        RebalanceExecutionError: If persistence fails
    """
    try:
        # Also get final positions from execution engine
        positions = {}
        if hasattr(result, 'execution_engine_ref'):  # Could store engine reference if needed
            pass  # For now, positions are tracked in execution engine session
        
        execution_data = result.to_dict()
        execution_json = json.dumps(execution_data, indent=2).encode('utf-8')
        artifact_store.store(result.execution_id, "rebalance_execution.json", execution_json)
        return result.execution_id
    except Exception as e:
        raise RebalanceExecutionError(f"Failed to persist rebalance execution: {e}") from e

