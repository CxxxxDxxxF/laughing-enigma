"""Signal emission interface for research domain.

This module defines the interface for strategies/backtests to emit
raw outputs that will be converted to execution-ready Signals.
"""

from typing import Optional, Dict, Any, Iterator
from dataclasses import dataclass
from datetime import datetime
from abc import ABC, abstractmethod


@dataclass
class RawStrategyOutput:
    """Raw strategy output before conversion to Signal.
    
    This represents what a strategy "wants to do" without any
    execution-domain knowledge.
    
    Attributes:
        timestamp: When the decision was made
        instrument: Instrument identifier
        action: Desired action ("buy", "sell", "hold")
        quantity: Desired quantity (positive number)
        confidence: Optional confidence score (0.0 to 1.0)
        strategy_context: Optional context data (for debugging/auditing)
        
    Note:
        - Action must be one of: "buy", "sell", "hold"
        - Quantity must be positive
        - This is research-domain data, not execution-domain
    """
    
    timestamp: datetime
    instrument: str
    action: str  # "buy", "sell", "hold"
    quantity: float
    confidence: Optional[float] = None
    strategy_context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate raw output after initialization."""
        if self.action not in ("buy", "sell", "hold"):
            raise ValueError(f"action must be 'buy', 'sell', or 'hold', got: {self.action}")
        
        if self.quantity < 0:
            raise ValueError(f"quantity must be non-negative, got: {self.quantity}")
        
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got: {self.confidence}")


class SignalEmitter(ABC):
    """Abstract interface for emitting raw strategy outputs.
    
    Strategies and backtests implement this interface to emit
    raw outputs that will be converted to execution-ready Signals.
    
    This interface keeps research domain separate from execution domain.
    """
    
    @abstractmethod
    def emit_signals(self, *args, **kwargs) -> Iterator[RawStrategyOutput]:
        """Emit raw strategy outputs as an iterator.
        
        This method is called during backtest execution to yield
        strategy decisions at each timestep.
        
        Args:
            *args, **kwargs: Strategy-specific arguments (e.g., price data, dates)
            
        Yields:
            RawStrategyOutput objects representing strategy decisions
            
        Note:
            - Must be deterministic: same inputs → same outputs
            - May yield zero or more outputs
            - Should yield outputs in chronological order
        """
        raise NotImplementedError

