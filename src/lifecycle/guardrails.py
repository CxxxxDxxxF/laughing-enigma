"""Guardrails for portfolio cycle safety.

This module provides hard-stop guardrails to prevent unsafe operations.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


class GuardrailViolationError(Exception):
    """Error raised when a guardrail is violated."""
    pass


@dataclass
class GuardrailsConfig:
    """Configuration for portfolio guardrails.
    
    Attributes:
        max_turnover_pct_per_cycle: Maximum turnover as % of total capital per cycle (default: 1.0 = 100%)
        max_failed_intents: Maximum number of failed intents allowed (default: None = no limit)
        min_execution_success_rate: Minimum execution success rate (0.0 to 1.0, default: 0.0 = no limit)
        max_single_strategy_allocation_fraction: Maximum allocation to single strategy (0.0 to 1.0, default: 1.0 = no limit)
        halt_on_any_error: If True, halt on any error (default: False)
        
    Note:
        Guardrails are checked at multiple stages:
        - After allocation: concentration limits
        - After rebalance plan: turnover limits
        - After execution: success rate, failed intents
    """
    
    max_turnover_pct_per_cycle: float = 1.0
    max_failed_intents: Optional[int] = None
    min_execution_success_rate: float = 0.0
    max_single_strategy_allocation_fraction: float = 1.0
    halt_on_any_error: bool = False
    
    def __post_init__(self):
        """Validate guardrails config."""
        if self.max_turnover_pct_per_cycle <= 0:
            raise ValueError(
                f"max_turnover_pct_per_cycle must be positive, got: {self.max_turnover_pct_per_cycle}"
            )
        
        if not (0.0 <= self.min_execution_success_rate <= 1.0):
            raise ValueError(
                f"min_execution_success_rate must be between 0.0 and 1.0, "
                f"got: {self.min_execution_success_rate}"
            )
        
        if not (0.0 <= self.max_single_strategy_allocation_fraction <= 1.0):
            raise ValueError(
                f"max_single_strategy_allocation_fraction must be between 0.0 and 1.0, "
                f"got: {self.max_single_strategy_allocation_fraction}"
            )
        
        if self.max_failed_intents is not None and self.max_failed_intents < 0:
            raise ValueError(
                f"max_failed_intents must be non-negative, got: {self.max_failed_intents}"
            )


def check_allocation_guardrails(
    config: GuardrailsConfig,
    allocations: List[Dict[str, Any]],
    total_capital: float
) -> tuple[bool, Optional[str]]:
    """Check guardrails after allocation.
    
    Args:
        config: Guardrails configuration
        allocations: List of allocation dicts with 'allocation_fraction' key
        total_capital: Total capital
        
    Returns:
        Tuple of (passes: bool, violation_reason: Optional[str])
    """
    if not allocations:
        return True, None
    
    # Check concentration limit
    max_allocation = max(alloc.get('allocation_fraction', 0.0) for alloc in allocations)
    if max_allocation > config.max_single_strategy_allocation_fraction:
        return False, (
            f"Single strategy allocation {max_allocation:.1%} exceeds maximum "
            f"{config.max_single_strategy_allocation_fraction:.1%}"
        )
    
    return True, None


def check_rebalance_guardrails(
    config: GuardrailsConfig,
    total_turnover: float,
    total_capital: float
) -> tuple[bool, Optional[str]]:
    """Check guardrails after rebalance planning.
    
    Args:
        config: Guardrails configuration
        total_turnover: Total turnover amount
        total_capital: Total capital
        
    Returns:
        Tuple of (passes: bool, violation_reason: Optional[str])
    """
    turnover_pct = (total_turnover / total_capital) if total_capital > 0 else 0.0
    
    if turnover_pct > config.max_turnover_pct_per_cycle:
        return False, (
            f"Turnover {turnover_pct:.1%} exceeds maximum "
            f"{config.max_turnover_pct_per_cycle:.1%} per cycle"
        )
    
    return True, None


def check_execution_guardrails(
    config: GuardrailsConfig,
    successful_intents: int,
    failed_intents: int,
    total_intents: int
) -> tuple[bool, Optional[str]]:
    """Check guardrails after execution.
    
    Args:
        config: Guardrails configuration
        successful_intents: Number of successful intents
        failed_intents: Number of failed intents
        total_intents: Total number of intents
        
    Returns:
        Tuple of (passes: bool, violation_reason: Optional[str])
    """
    # Check max failed intents
    if config.max_failed_intents is not None and failed_intents > config.max_failed_intents:
        return False, (
            f"Failed intents {failed_intents} exceeds maximum {config.max_failed_intents}"
        )
    
    # Check min success rate
    if total_intents > 0:
        success_rate = successful_intents / total_intents
        if success_rate < config.min_execution_success_rate:
            return False, (
                f"Execution success rate {success_rate:.1%} below minimum "
                f"{config.min_execution_success_rate:.1%}"
            )
    
    return True, None

