"""Signal adapter for converting raw strategy outputs to execution-ready Signals.

This module provides the SignalAdapter interface and configuration for
transforming research-domain outputs into execution-domain Signals.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from abc import ABC, abstractmethod

from .emitter import RawStrategyOutput
from ..execution import Signal, SignalType, RiskLimits


class SignalAdapterError(Exception):
    """Error raised when signal adaptation fails."""
    pass


class InvalidSignalError(SignalAdapterError):
    """Error raised when raw output cannot be converted to valid Signal."""
    pass


class RiskCheckError(SignalAdapterError):
    """Error raised when signal fails pre-execution risk checks."""
    pass


@dataclass
class AdapterConfig:
    """Configuration for SignalAdapter.
    
    Attributes:
        position_sizing: Optional position sizing rule
                        (e.g., fixed_size, percentage_of_capital, etc.)
        signal_filters: Optional filters to exclude signals
                       (e.g., min_confidence, allowed_instruments)
        pre_execution_risk_limits: Optional risk limits to check before execution
        instrument_whitelist: Optional list of allowed instruments
        default_quantity: Default quantity if raw output doesn't specify
        
    Note:
        Configuration is separate from execution risk limits.
        This is pre-execution validation in the integration layer.
    """
    
    position_sizing: Optional[str] = None  # "fixed", "percentage", "target_vol", etc.
    position_size_value: Optional[float] = None  # Value for position sizing rule
    signal_filters: Optional[Dict[str, Any]] = None  # e.g., {"min_confidence": 0.7}
    pre_execution_risk_limits: Optional[RiskLimits] = None
    instrument_whitelist: Optional[List[str]] = None
    default_quantity: float = 100.0


class SignalAdapter(ABC):
    """Abstract interface for adapting raw strategy outputs to Signals.
    
    SignalAdapter transforms research-domain outputs (RawStrategyOutput)
    into execution-domain inputs (Signal). This is where integration
    happens while maintaining domain separation.
    
    Responsibilities:
    1. Validate raw outputs
    2. Map action → SignalType
    3. Apply position sizing (if configured)
    4. Apply pre-execution risk checks
    5. Create immutable Signal objects
    
    Safety:
    - Rejects invalid signals (doesn't throw, returns None or raises)
    - Logs all rejections with reasons
    - Maintains determinism (same input → same output)
    """
    
    def __init__(self, config: Optional[AdapterConfig] = None):
        """Initialize signal adapter.
        
        Args:
            config: Adapter configuration (default: minimal config)
        """
        self.config = config or AdapterConfig()
    
    @abstractmethod
    def adapt(self, raw_output: RawStrategyOutput) -> Optional[Signal]:
        """Adapt a raw strategy output to an execution-ready Signal.
        
        Process:
        1. Validate raw_output format
        2. Apply signal filters (if configured)
        3. Apply position sizing (if configured)
        4. Map action → SignalType
        5. Perform pre-execution risk checks
        6. Create Signal object
        
        Args:
            raw_output: Raw strategy output to adapt
            
        Returns:
            Signal object if adaptation succeeds, None if signal is filtered/ignored
            
        Raises:
            InvalidSignalError: If raw_output is invalid and cannot be adapted
            RiskCheckError: If signal fails pre-execution risk checks
            
        Note:
            - Returns None for filtered signals (not an error condition)
            - Raises exceptions only for invalid inputs or risk violations
            - Must be deterministic
        """
        raise NotImplementedError
    
    @abstractmethod
    def validate_raw_output(self, raw_output: RawStrategyOutput) -> bool:
        """Validate raw strategy output format.
        
        Args:
            raw_output: Raw output to validate
            
        Returns:
            True if valid, False otherwise
            
        Raises:
            InvalidSignalError: If validation fails with specific reason
        """
        raise NotImplementedError
    
    @abstractmethod
    def apply_filters(self, raw_output: RawStrategyOutput) -> bool:
        """Apply signal filters to determine if signal should be processed.
        
        Args:
            raw_output: Raw output to filter
            
        Returns:
            True if signal should be processed, False if it should be ignored
        """
        raise NotImplementedError
    
    @abstractmethod
    def apply_position_sizing(self, raw_output: RawStrategyOutput) -> float:
        """Apply position sizing rules to determine final quantity.
        
        Args:
            raw_output: Raw output with initial quantity
            
        Returns:
            Final quantity after position sizing rules
            
        Note:
            Default implementation returns raw_output.quantity
        """
        raise NotImplementedError
    
    @abstractmethod
    def check_pre_execution_risk(self, signal: Signal) -> None:
        """Perform pre-execution risk checks.
        
        Args:
            signal: Signal to check
            
        Raises:
            RiskCheckError: If risk checks fail
        """
        raise NotImplementedError

