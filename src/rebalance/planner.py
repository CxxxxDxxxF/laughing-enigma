"""Rebalance planning engine.

This module provides deterministic rebalance planning that converts portfolio
allocation targets into actionable trade intents.

Determinism guarantees:
- Same allocation + same current state + same config → same plan
- Deterministic trade intent generation
- Deterministic constraint enforcement
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

from ..allocation import AllocationResult, PortfolioAllocation
from ..core.artifacts import ArtifactStore
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..lifecycle.runner import ExecutionMode


class RebalanceError(Exception):
    """Error raised when rebalance planning fails."""
    pass


class TradeDirection(str, Enum):
    """Direction of a trade intent."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"  # No trade needed


@dataclass
class CurrentPortfolioState:
    """Current portfolio state before rebalancing.
    
    Represents the current capital allocation across strategies.
    
    Attributes:
        strategy_allocations: Dictionary mapping strategy_id -> current capital
        total_capital: Total capital in portfolio
        timestamp: Timestamp of this state snapshot
        drawdown_tracker: Optional drawdown tracker for Topstep-style rules
        positions_by_instrument: Dictionary mapping instrument -> Position dict (from Position.to_dict())
            Used for hold-quantity validation mode (Phase 15)
        
    Note:
        If strategy_id is not in strategy_allocations, current allocation is 0.
        positions_by_instrument stores Position serialized as dict for persistence.
    """
    
    strategy_allocations: Dict[str, float]
    total_capital: float
    timestamp: datetime
    drawdown_tracker: Optional['DrawdownTracker'] = None
    positions_by_instrument: Optional[Dict[str, Dict[str, Any]]] = None
    
    def get_allocation(self, strategy_id: str) -> float:
        """Get current allocation for a strategy.
        
        Args:
            strategy_id: Strategy identifier
            
        Returns:
            Current capital allocated (0.0 if not found)
        """
        return self.strategy_allocations.get(strategy_id, 0.0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        result = {
            "strategy_allocations": self.strategy_allocations,
            "total_capital": self.total_capital,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.drawdown_tracker is not None:
            result["drawdown_tracker"] = self.drawdown_tracker.to_dict()
        if self.positions_by_instrument is not None:
            result["positions_by_instrument"] = self.positions_by_instrument
        return result


@dataclass
class TradeIntent:
    """Intent to trade a specific amount for a strategy.
    
    This represents a trade that should be executed to move from current
    allocation to target allocation. It does NOT place any orders.
    
    Attributes:
        strategy_id: Strategy identifier
        direction: Trade direction (BUY, SELL, or HOLD)
        amount: Amount to trade (positive number, in capital units)
        current_allocation: Current capital allocated
        target_allocation: Target capital allocated
        delta: Change needed (target - current)
        
    Note:
        - BUY: Increase allocation (delta > 0)
        - SELL: Decrease allocation (delta < 0)
        - HOLD: No change needed (delta within threshold)
        - amount is always positive (absolute value of delta)
    """
    
    strategy_id: str
    direction: TradeDirection
    amount: float
    current_allocation: float
    target_allocation: float
    delta: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "strategy_id": self.strategy_id,
            "direction": self.direction.value,
            "amount": self.amount,
            "current_allocation": self.current_allocation,
            "target_allocation": self.target_allocation,
            "delta": self.delta,
        }


@dataclass
class RebalanceConfig:
    """Configuration for rebalance planning.
    
    Attributes:
        rebalance_threshold_pct: Minimum change percentage to trigger rebalance
                                 (default: 0.05 = 5%)
                                 If delta is less than threshold, no trade
        max_turnover_pct: Maximum turnover as percentage of total capital
                          (default: 1.0 = 100%, no limit)
                          If total turnover exceeds this, scale down proportionally
        min_trade_size: Minimum trade size in capital units (default: 0.0)
                        Trades smaller than this are filtered out
        allow_partial_rebalance: If True, allow partial rebalance if max_turnover binds
                                 (default: True)
                                 If False, reject rebalance if max_turnover exceeded
        
    Note:
        rebalance_threshold_pct is applied per-strategy.
        max_turnover_pct is applied to total portfolio turnover.
    """
    
    rebalance_threshold_pct: float = 0.05  # 5% default
    max_turnover_pct: float = 1.0  # 100% = no limit
    min_trade_size: float = 0.0
    allow_partial_rebalance: bool = True
    
    def __post_init__(self):
        """Validate rebalance config."""
        if self.rebalance_threshold_pct < 0.0 or self.rebalance_threshold_pct > 1.0:
            raise ValueError(
                f"rebalance_threshold_pct must be between 0.0 and 1.0, "
                f"got: {self.rebalance_threshold_pct}"
            )
        
        if self.max_turnover_pct <= 0.0:
            raise ValueError(
                f"max_turnover_pct must be positive, got: {self.max_turnover_pct}"
            )
        
        if self.min_trade_size < 0.0:
            raise ValueError(
                f"min_trade_size must be non-negative, got: {self.min_trade_size}"
            )


@dataclass
class RebalancePlan:
    """Complete rebalance plan.
    
    Attributes:
        plan_id: Unique identifier for this rebalance plan
        plan_timestamp: When plan was created
        allocation_result_id: ID of AllocationResult used
        current_state: Current portfolio state
        config: Rebalance configuration used
        trade_intents: List of trade intents to execute
        metrics: Rebalance metrics
    """
    
    plan_id: str
    plan_timestamp: datetime
    allocation_result_id: str
    current_state: CurrentPortfolioState
    config: RebalanceConfig
    trade_intents: List[TradeIntent]
    metrics: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "plan_id": self.plan_id,
            "plan_timestamp": self.plan_timestamp.isoformat(),
            "allocation_result_id": self.allocation_result_id,
            "current_state": self.current_state.to_dict(),
            "config": {
                "rebalance_threshold_pct": self.config.rebalance_threshold_pct,
                "max_turnover_pct": self.config.max_turnover_pct,
                "min_trade_size": self.config.min_trade_size,
                "allow_partial_rebalance": self.config.allow_partial_rebalance,
            },
            "trade_intents": [ti.to_dict() for ti in self.trade_intents],
            "metrics": self.metrics,
        }


def _compute_deltas(
    allocation_result: AllocationResult,
    current_state: CurrentPortfolioState
) -> Dict[str, float]:
    """Compute allocation deltas (target - current) for each strategy.
    
    Args:
        allocation_result: Target allocations
        current_state: Current portfolio state
        
    Returns:
        Dictionary mapping strategy_id -> delta (target - current)
    """
    deltas = {}
    
    # Compute deltas for strategies in target allocation
    for alloc in allocation_result.allocations:
        current = current_state.get_allocation(alloc.strategy_id)
        target = alloc.allocated_capital
        deltas[alloc.strategy_id] = target - current
    
    # Check for strategies in current state but not in target (should be sold)
    for strategy_id, current in current_state.strategy_allocations.items():
        if strategy_id not in deltas:
            # Strategy not in target allocation - full sell
            deltas[strategy_id] = -current
    
    return deltas


def _apply_rebalance_threshold(
    deltas: Dict[str, float],
    current_state: CurrentPortfolioState,
    threshold_pct: float
) -> Dict[str, float]:
    """Apply rebalance threshold to filter small changes.
    
    Args:
        deltas: Allocation deltas
        current_state: Current portfolio state
        threshold_pct: Minimum change percentage to trigger rebalance
        
    Returns:
        Filtered deltas (small changes set to 0)
    """
    filtered_deltas = {}
    
    for strategy_id, delta in deltas.items():
        current = current_state.get_allocation(strategy_id)
        
        # Compute change percentage
        if current > 0:
            change_pct = abs(delta) / current
        else:
            # New strategy (current = 0) - always include if delta > 0
            change_pct = 1.0 if delta > 0 else 0.0
        
        # Apply threshold
        if change_pct >= threshold_pct:
            filtered_deltas[strategy_id] = delta
        else:
            filtered_deltas[strategy_id] = 0.0
    
    return filtered_deltas


def _apply_min_trade_size(
    deltas: Dict[str, float],
    min_trade_size: float
) -> Dict[str, float]:
    """Filter out trades smaller than minimum trade size.
    
    Args:
        deltas: Allocation deltas
        min_trade_size: Minimum trade size
        
    Returns:
        Filtered deltas (small trades set to 0)
    """
    filtered_deltas = {}
    
    for strategy_id, delta in deltas.items():
        if abs(delta) >= min_trade_size:
            filtered_deltas[strategy_id] = delta
        else:
            filtered_deltas[strategy_id] = 0.0
    
    return filtered_deltas


def _apply_max_turnover(
    deltas: Dict[str, float],
    total_capital: float,
    max_turnover_pct: float,
    allow_partial: bool
) -> Dict[str, float]:
    """Apply maximum turnover constraint.
    
    Args:
        deltas: Allocation deltas
        total_capital: Total capital
        max_turnover_pct: Maximum turnover as percentage
        allow_partial: If True, scale down proportionally; if False, raise error
        
    Returns:
        Constrained deltas
        
    Raises:
        RebalanceError: If max_turnover exceeded and allow_partial is False
    """
    # Compute total turnover (sum of absolute deltas)
    total_turnover = sum(abs(d) for d in deltas.values())
    max_turnover = total_capital * max_turnover_pct
    
    if total_turnover <= max_turnover:
        return deltas
    
    # Turnover exceeded
    if not allow_partial:
        raise RebalanceError(
            f"Total turnover {total_turnover:.2f} exceeds maximum {max_turnover:.2f} "
            f"({max_turnover_pct:.1%}). Set allow_partial_rebalance=True to scale down."
        )
    
    # Scale down proportionally
    scale_factor = max_turnover / total_turnover
    constrained_deltas = {strategy_id: delta * scale_factor for strategy_id, delta in deltas.items()}
    
    return constrained_deltas


def _generate_trade_intents(
    deltas: Dict[str, float],
    allocation_result: AllocationResult,
    current_state: CurrentPortfolioState
) -> List[TradeIntent]:
    """Generate trade intents from deltas.
    
    Args:
        deltas: Allocation deltas (after constraints applied)
        allocation_result: Target allocations
        current_state: Current portfolio state
        
    Returns:
        List of trade intents
    """
    trade_intents = []
    
    # Create target allocation lookup
    target_lookup = {alloc.strategy_id: alloc.allocated_capital for alloc in allocation_result.allocations}
    
    for strategy_id, delta in deltas.items():
        if abs(delta) < 1e-6:  # Effectively zero
            direction = TradeDirection.HOLD
            amount = 0.0
        elif delta > 0:
            direction = TradeDirection.BUY
            amount = delta
        else:  # delta < 0
            direction = TradeDirection.SELL
            amount = abs(delta)
        
        current = current_state.get_allocation(strategy_id)
        target = target_lookup.get(strategy_id, 0.0)
        
        trade_intent = TradeIntent(
            strategy_id=strategy_id,
            direction=direction,
            amount=amount,
            current_allocation=current,
            target_allocation=target,
            delta=delta
        )
        
        trade_intents.append(trade_intent)
    
    return trade_intents


def _compute_rebalance_metrics(
    trade_intents: List[TradeIntent],
    total_capital: float,
    original_deltas: Dict[str, float]
) -> Dict[str, Any]:
    """Compute rebalance metrics.
    
    Args:
        trade_intents: List of trade intents
        total_capital: Total capital
        original_deltas: Original deltas (before constraints)
        
    Returns:
        Dictionary of metrics
    """
    # Count trades (excluding HOLD)
    trades = [ti for ti in trade_intents if ti.direction != TradeDirection.HOLD]
    num_trades = len(trades)
    
    # Compute total turnover
    total_turnover = sum(ti.amount for ti in trades)
    turnover_pct = (total_turnover / total_capital * 100.0) if total_capital > 0 else 0.0
    
    # Compute percent of capital moved
    total_original_turnover = sum(abs(d) for d in original_deltas.values())
    percent_moved = (total_turnover / total_original_turnover * 100.0) if total_original_turnover > 0 else 0.0
    
    # Count by direction
    buy_count = sum(1 for ti in trades if ti.direction == TradeDirection.BUY)
    sell_count = sum(1 for ti in trades if ti.direction == TradeDirection.SELL)
    
    # Compute buy/sell amounts
    buy_amount = sum(ti.amount for ti in trades if ti.direction == TradeDirection.BUY)
    sell_amount = sum(ti.amount for ti in trades if ti.direction == TradeDirection.SELL)
    
    return {
        "num_trades": num_trades,
        "total_turnover": total_turnover,
        "turnover_pct": turnover_pct,
        "percent_capital_moved": percent_moved,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "buy_amount": buy_amount,
        "sell_amount": sell_amount,
    }


def plan_rebalance(
    allocation_result: AllocationResult,
    current_state: CurrentPortfolioState,
    config: Optional[RebalanceConfig] = None,
    plan_id: Optional[str] = None,
    plan_timestamp: Optional[datetime] = None,
    execution_mode: Optional['ExecutionMode'] = None
) -> RebalancePlan:
    """Plan a rebalance from current state to target allocations.
    
    Process:
    1. Compute allocation deltas (target - current)
    2. Apply rebalance threshold (filter small changes)
    3. Apply minimum trade size (filter tiny trades)
    4. Apply maximum turnover constraint (scale down if needed)
    5. Generate trade intents
    6. Compute metrics
    
    Determinism guarantees:
    - Same allocation + same current state + same config → same plan
    - Deterministic constraint application order
    - Deterministic trade intent generation
    
    Args:
        allocation_result: Target allocations from allocation layer
        current_state: Current portfolio state
        config: Rebalance configuration (default: RebalanceConfig with defaults)
        plan_id: Optional plan identifier (required in LIVE mode)
        plan_timestamp: Optional plan timestamp (required in LIVE mode)
        execution_mode: Optional execution mode (ExecutionMode enum, for validation)
        
    Returns:
        RebalancePlan with trade intents and metrics
        
    Raises:
        RebalanceError: If rebalance planning fails or LIVE mode validation fails
        
    Example:
        >>> config = RebalanceConfig(
        ...     rebalance_threshold_pct=0.05,
        ...     max_turnover_pct=0.5,
        ...     min_trade_size=1000.0
        ... )
        >>> plan = plan_rebalance(allocation_result, current_state, config)
        >>> print(f"Number of trades: {plan.metrics['num_trades']}")
        >>> print(f"Total turnover: ${plan.metrics['total_turnover']:,.2f}")
    """
    # Validate LIVE/LIVE_DRY mode requirements
    if execution_mode is not None:
        # Check for LIVE or LIVE_DRY mode (string comparison to avoid circular import)
        if str(execution_mode) in ("live", "live_dry"):
            if plan_id is None:
                raise RebalanceError("LIVE mode requires explicit plan_id")
            if plan_timestamp is None:
                raise RebalanceError("LIVE mode requires explicit plan_timestamp")
    
    # Generate plan_id if not provided (SIMULATION mode only)
    if plan_id is None:
        plan_id = f"rebalance_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Use provided timestamp or fallback to now (SIMULATION mode only)
    if plan_timestamp is None:
        plan_timestamp = datetime.now()
    
    if config is None:
        config = RebalanceConfig()
    
    try:
        # Step 1: Compute deltas
        original_deltas = _compute_deltas(allocation_result, current_state)
        
        # Step 2: Apply rebalance threshold
        deltas = _apply_rebalance_threshold(
            original_deltas,
            current_state,
            config.rebalance_threshold_pct
        )
        
        # Step 3: Apply minimum trade size
        deltas = _apply_min_trade_size(deltas, config.min_trade_size)
        
        # Step 4: Apply maximum turnover constraint
        deltas = _apply_max_turnover(
            deltas,
            current_state.total_capital,
            config.max_turnover_pct,
            config.allow_partial_rebalance
        )
        
        # Step 5: Generate trade intents
        trade_intents = _generate_trade_intents(deltas, allocation_result, current_state)
        
        # Step 6: Compute metrics
        metrics = _compute_rebalance_metrics(trade_intents, current_state.total_capital, original_deltas)
        
        # plan_timestamp already set above
        return RebalancePlan(
            plan_id=plan_id,
            plan_timestamp=plan_timestamp,
            allocation_result_id=allocation_result.allocation_id,
            current_state=current_state,
            config=config,
            trade_intents=trade_intents,
            metrics=metrics
        )
        
    except Exception as e:
        raise RebalanceError(f"Failed to plan rebalance: {e}") from e


def persist_rebalance_plan(
    plan: RebalancePlan,
    artifact_store: ArtifactStore
) -> str:
    """Persist rebalance plan to artifact store.
    
    Args:
        plan: RebalancePlan to persist
        artifact_store: ArtifactStore instance
        
    Returns:
        Plan identifier
        
    Raises:
        RebalanceError: If persistence fails
    """
    try:
        plan_json = json.dumps(plan.to_dict(), indent=2).encode('utf-8')
        artifact_store.store(plan.plan_id, "rebalance_plan.json", plan_json)
        return plan.plan_id
    except Exception as e:
        raise RebalanceError(f"Failed to persist rebalance plan: {e}") from e

