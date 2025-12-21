"""Survivability control layer for position size enforcement.

This module implements deterministic controls to prevent position size violations
by clamping capital allocations before they reach rebalance planning.

Key principle:
- Position size limits are enforced at allocation time, not execution time
- Capital allocations are clamped to max_capital_allowed = max_position_size * price
- Control events are logged for auditability and analysis
- Deterministic: same inputs → same outputs
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from ..allocation.allocator import AllocationResult, PortfolioAllocation


class ControlEventSeverity(str, Enum):
    """Severity levels for control events."""
    INFO = "info"
    WARN = "warn"


@dataclass
class ControlEvent:
    """Control event record for auditability.
    
    Attributes:
        code: Event code (e.g., "POSITION_SIZE_CAP_BINDING")
        message: Human-readable message
        severity: Event severity ("info" | "warn")
        metadata: Additional event data (dict)
        
    Note:
        Control events are informational/warning only, not violations.
        They document when controls are applied but do not halt execution.
    """
    
    code: str
    message: str
    severity: ControlEventSeverity
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "metadata": self.metadata,
        }


@dataclass
class SurvivabilityControlConfig:
    """Configuration for survivability controls.
    
    Attributes:
        position_cap_policy: Policy for enforcing position size limits
            - "cap_quantity": Clamp capital allocation to max_capital_allowed
            - "scale_targets": Scale down all targets proportionally (not implemented yet)
        max_position_size_default: Default maximum position size in units (if not specified per instrument)
        max_position_size_by_instrument: Optional dict mapping instrument -> max position size
        allow_cash_residual: If True, allow unallocated capital (default: True)
        redistribute_residual: If True, redistribute capped capital to other strategies by rank (default: False)
            
    Note:
        - max_position_size_by_instrument takes precedence over max_position_size_default
        - If redistribute_residual=False, capped capital remains unallocated
        - If redistribute_residual=True, capital is redistributed deterministically by strategy rank
    """
    
    position_cap_policy: str = "cap_quantity"
    max_position_size_default: float = 1000.0
    max_position_size_by_instrument: Optional[Dict[str, float]] = None
    allow_cash_residual: bool = True
    redistribute_residual: bool = False
    
    def __post_init__(self):
        """Validate config."""
        if self.position_cap_policy not in ("cap_quantity", "scale_targets"):
            raise ValueError(
                f"position_cap_policy must be 'cap_quantity' or 'scale_targets', "
                f"got: {self.position_cap_policy}"
            )
        
        if self.max_position_size_default <= 0:
            raise ValueError(
                f"max_position_size_default must be positive, "
                f"got: {self.max_position_size_default}"
            )
        
        if self.position_cap_policy == "scale_targets":
            raise NotImplementedError("scale_targets policy not yet implemented")


def _get_max_position_size(
    instrument: str,
    config: SurvivabilityControlConfig
) -> float:
    """Get maximum position size for an instrument.
    
    Args:
        instrument: Instrument identifier
        config: Control configuration
        
    Returns:
        Maximum position size in units
    """
    if config.max_position_size_by_instrument:
        return config.max_position_size_by_instrument.get(
            instrument,
            config.max_position_size_default
        )
    return config.max_position_size_default


def _get_price_for_strategy(
    strategy_id: str,
    price_by_strategy_or_instrument: Dict[str, float],
    instrument: Optional[str] = None
) -> Optional[float]:
    """Get price for a strategy.
    
    Tries strategy_id first, then instrument if provided.
    
    Args:
        strategy_id: Strategy identifier
        price_by_strategy_or_instrument: Price dictionary
        instrument: Optional instrument identifier to try as fallback
        
    Returns:
        Price if found, None otherwise
    """
    # Try strategy_id first
    price = price_by_strategy_or_instrument.get(strategy_id)
    if price is not None:
        return price
    
    # Try instrument if provided
    if instrument:
        price = price_by_strategy_or_instrument.get(instrument)
        if price is not None:
            return price
    
    return None


def apply_survivability_controls(
    allocation_result: AllocationResult,
    price_by_strategy_or_instrument: Dict[str, float],
    config: SurvivabilityControlConfig,
    instrument: Optional[str] = None  # Single instrument assumption for now
) -> Tuple[AllocationResult, List[ControlEvent]]:
    """Apply survivability controls to capital allocation.
    
    This function clamps capital allocations to prevent position size violations
    by enforcing max_capital_allowed = max_position_size * price per strategy.
    
    Process (cap_quantity policy):
    1. For each strategy allocation:
       a. Get price for strategy/instrument
       b. Compute max_capital_allowed = max_position_size * price
       c. If allocated_capital > max_capital_allowed:
          - Clamp to max_capital_allowed
          - Record control event with utilization metrics
    2. If redistribute_residual=True:
       - Redistribute capped capital to non-capped strategies by rank
    3. Recompute allocation metrics
    4. Return adjusted AllocationResult and control events
    
    Determinism guarantees:
    - Same allocation + same prices + same config → same adjusted allocation
    - Deterministic clamping order (by strategy rank/order)
    - Deterministic redistribution (by strategy rank)
    
    Args:
        allocation_result: Original allocation result
        price_by_strategy_or_instrument: Dictionary mapping strategy_id or instrument -> price
        config: Control configuration
        instrument: Optional instrument identifier (assumes single instrument per portfolio)
        
    Returns:
        Tuple of (adjusted_allocation_result, control_events)
        
    Note:
        - If price is not found for a strategy, allocation is left unchanged (no event recorded)
        - Control events are informational/warning only, not errors
        - adjusted_allocation_result has same structure as original but with clamped capital values
    """
    events: List[ControlEvent] = []
    
    # Get max position size (assumes single instrument for now)
    max_position_size = _get_max_position_size(
        instrument or "DEFAULT",
        config
    )
    
    # Create adjusted allocations
    adjusted_allocations: List[PortfolioAllocation] = []
    total_capped_capital = 0.0
    capped_strategies: List[str] = []
    
    for alloc in allocation_result.allocations:
        # Get price for this strategy
        price = _get_price_for_strategy(
            alloc.strategy_id,
            price_by_strategy_or_instrument,
            instrument
        )
        
        if price is None or price <= 0:
            # Price not found or invalid - leave allocation unchanged
            adjusted_allocations.append(alloc)
            continue
        
        # Compute max capital allowed
        max_capital_allowed = max_position_size * price
        
        # Check if allocation exceeds limit
        if alloc.allocated_capital > max_capital_allowed:
            # Clamp to max
            original_capital = alloc.allocated_capital
            capped_capital = original_capital - max_capital_allowed
            total_capped_capital += capped_capital
            capped_strategies.append(alloc.strategy_id)
            
            # Create adjusted allocation
            adjusted_alloc = PortfolioAllocation(
                strategy_id=alloc.strategy_id,
                experiment_name=alloc.experiment_name,
                experiment_version=alloc.experiment_version,
                allocated_capital=max_capital_allowed,
                allocation_fraction=alloc.allocation_fraction,  # Will be recomputed later
                robustness_score=alloc.robustness_score,
                rank=alloc.rank
            )
            adjusted_allocations.append(adjusted_alloc)
            
            # Record control event
            utilization = original_capital / max_capital_allowed
            event = ControlEvent(
                code="POSITION_SIZE_CAP_BINDING",
                message=f"Strategy {alloc.strategy_id} allocation clamped: "
                       f"${original_capital:,.2f} -> ${max_capital_allowed:,.2f} "
                       f"(utilization: {utilization:.2%})",
                severity=ControlEventSeverity.WARN,
                metadata={
                    "strategy_id": alloc.strategy_id,
                    "target_capital": original_capital,
                    "capped_capital": max_capital_allowed,
                    "price": price,
                    "max_position_size": max_position_size,
                    "utilization": utilization,
                    "capped_amount": capped_capital,
                }
            )
            events.append(event)
        else:
            # No clamping needed
            adjusted_allocations.append(alloc)
    
    # Redistribute capped capital if requested
    if config.redistribute_residual and total_capped_capital > 0.0:
            # Redistribute to non-capped strategies by rank (highest rank = best strategy)
            non_capped_allocations = [
                a for a in adjusted_allocations
                if a.strategy_id not in capped_strategies
            ]
            
            if non_capped_allocations:
                # Sort by robustness_score descending (best strategies first)
                non_capped_allocations.sort(key=lambda x: -x.robustness_score)
            
            # Redistribute proportionally by robustness score
            total_robustness = sum(a.robustness_score for a in non_capped_allocations)
            if total_robustness > 0:
                for alloc in non_capped_allocations:
                    share = alloc.robustness_score / total_robustness
                    additional_capital = total_capped_capital * share
                    
                    # Check if this would also exceed limit
                    price = _get_price_for_strategy(
                        alloc.strategy_id,
                        price_by_strategy_or_instrument,
                        instrument
                    )
                    
                    if price and price > 0:
                        max_capital_allowed = max_position_size * price
                        new_capital = alloc.allocated_capital + additional_capital
                        
                        if new_capital > max_capital_allowed:
                            # Can't fully redistribute, clamp this one too
                            additional_capital = max_capital_allowed - alloc.allocated_capital
                            new_capital = max_capital_allowed
                            
                            event = ControlEvent(
                                code="POSITION_SIZE_CAP_BINDING",
                                message=f"Strategy {alloc.strategy_id} reached limit during redistribution",
                                severity=ControlEventSeverity.INFO,
                                metadata={
                                    "strategy_id": alloc.strategy_id,
                                    "redistributed_capital": additional_capital,
                                }
                            )
                            events.append(event)
                        
                        # Update allocation
                        idx = next(
                            i for i, a in enumerate(adjusted_allocations)
                            if a.strategy_id == alloc.strategy_id
                        )
                        adjusted_allocations[idx] = PortfolioAllocation(
                            strategy_id=alloc.strategy_id,
                            experiment_name=alloc.experiment_name,
                            experiment_version=alloc.experiment_version,
                            allocated_capital=new_capital,
                            allocation_fraction=alloc.allocation_fraction,  # Will be recomputed
                            robustness_score=alloc.robustness_score,
                            rank=0  # Rank not needed for adjusted allocation
                        )
                        
                        total_capped_capital -= additional_capital
                        if total_capped_capital <= 0:
                            break
            
            if total_capped_capital > 0:
                # Some capital couldn't be redistributed
                event = ControlEvent(
                    code="CAPITAL_RESIDUAL",
                    message=f"${total_capped_capital:,.2f} capital could not be redistributed "
                           f"(all strategies at position limits)",
                    severity=ControlEventSeverity.INFO,
                    metadata={
                        "residual_capital": total_capped_capital,
                    }
                )
                events.append(event)
    
    # Recompute allocation fractions and total allocated capital
    total_allocated = sum(a.allocated_capital for a in adjusted_allocations)
    
    # Update allocation fractions
    for alloc in adjusted_allocations:
        if allocation_result.total_capital > 0:
            alloc.allocation_fraction = alloc.allocated_capital / allocation_result.total_capital
        else:
            alloc.allocation_fraction = 0.0
    
    # Recompute metrics (simplified - preserve original metrics structure)
    adjusted_metrics = allocation_result.metrics.copy()
    adjusted_metrics["original_allocated_capital"] = allocation_result.allocated_capital
    adjusted_metrics["adjusted_allocated_capital"] = total_allocated
    adjusted_metrics["capped_capital"] = allocation_result.allocated_capital - total_allocated
    adjusted_metrics["survivability_controls_applied"] = len(events) > 0
    
    # Create adjusted allocation result
    adjusted_result = AllocationResult(
        allocation_id=allocation_result.allocation_id,
        allocation_timestamp=allocation_result.allocation_timestamp,
        config=allocation_result.config,
        total_capital=allocation_result.total_capital,
        allocated_capital=total_allocated,
        unallocated_capital=allocation_result.total_capital - total_allocated,
        allocations=adjusted_allocations,
        metrics=adjusted_metrics
    )
    
    return adjusted_result, events
