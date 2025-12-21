"""Base ruleset interface for broker-agnostic trading rules.

This module defines the abstract interface for rulesets that validate
rebalance plans and execution results.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class RulesViolationSeverity(str, Enum):
    """Severity levels for rules violations."""
    WARN = "warn"  # Warning, cycle can continue
    HALT = "halt"  # Hard stop, cycle must halt


@dataclass(frozen=True)
class RulesViolation:
    """Represents a rules violation.
    
    Attributes:
        code: Violation code (e.g., "TOPSTEP_MAX_DAILY_LOSS")
        message: Human-readable violation message
        severity: Violation severity ("warn" or "halt")
        metadata: Additional metadata about the violation
        
    Note:
        HALT violations must stop the cycle.
        WARN violations allow the cycle to continue but should be logged.
    """
    
    code: str
    message: str
    severity: RulesViolationSeverity
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize violation to dictionary."""
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RulesViolation':
        """Deserialize violation from dictionary."""
        return cls(
            code=data["code"],
            message=data["message"],
            severity=RulesViolationSeverity(data["severity"]),
            metadata=data.get("metadata", {}),
        )


class RulesetError(Exception):
    """Error raised when ruleset operations fail."""
    pass


class Ruleset(ABC):
    """Abstract interface for trading rulesets.
    
    A ruleset validates rebalance plans and execution results according to
    broker or prop firm rules. Rulesets are broker-agnostic and operate on
    abstract concepts (allocations, turnover, PnL) rather than broker-specific APIs.
    
    Determinism:
        Same inputs → same violations (no randomness, no external state)
    """
    
    @abstractmethod
    def validate_plan(
        self,
        rebalance_plan: Any,  # RebalancePlan from rebalance.planner
        current_state: Any  # CurrentPortfolioState from rebalance.planner
    ) -> List[RulesViolation]:
        """Validate a rebalance plan against rules.
        
        This is called before execution to catch rule violations early.
        
        Args:
            rebalance_plan: The rebalance plan to validate
            current_state: Current portfolio state
            
        Returns:
            List of violations (empty if plan is valid)
            
        Raises:
            RulesetError: If validation fails due to internal error
        """
        raise NotImplementedError
    
    @abstractmethod
    def validate_execution(
        self,
        execution_result: Any,  # RebalanceExecutionResult from rebalance.executor
        current_state: Any,  # CurrentPortfolioState
        execution_engine: Optional[Any] = None,  # ExecutionEngine (optional, for position checks)
        current_prices: Optional[Dict[str, float]] = None  # Optional current prices for equity calculation
    ) -> List[RulesViolation]:
        """Validate execution results against rules.
        
        This is called after execution to check if executed trades violated rules.
        
        Args:
            execution_result: The execution result to validate
            current_state: Portfolio state before execution
            execution_engine: Optional execution engine for position/state checks
            current_prices: Optional dictionary of instrument -> current price
            
        Returns:
            List of violations (empty if execution is valid)
            
        Raises:
            RulesetError: If validation fails due to internal error
        """
        raise NotImplementedError

