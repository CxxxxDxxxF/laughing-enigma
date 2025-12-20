"""Signal definition for strategy output.

A Signal represents the intent/output from a trading strategy.
Signals are converted into Orders by the execution engine.
"""

from typing import Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SignalType(Enum):
    """Type of trading signal."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"  # No action required


@dataclass(frozen=True)
class Signal:
    """Immutable signal from strategy to execution engine.
    
    A Signal represents what the strategy wants to do. It is
    the bridge between research/backtesting and execution.
    
    Attributes:
        timestamp: When the signal was generated
        instrument: Instrument identifier (e.g., ticker symbol)
        signal_type: Type of signal (BUY, SELL, HOLD)
        quantity: Desired quantity (positive number)
        price_limit: Optional limit price for order (None = market order)
        strategy_id: Identifier for the strategy that generated this signal
        metadata: Optional additional data (for debugging/auditing)
        
    Note:
        - Quantity must be positive
        - For SELL signals, quantity represents shares to sell
        - For BUY signals, quantity represents shares to buy
        - HOLD signals may have quantity=0 or None
    """
    
    timestamp: datetime
    instrument: str
    signal_type: SignalType
    quantity: float
    price_limit: Optional[float] = None
    strategy_id: Optional[str] = None
    metadata: Optional[dict] = None
    
    def __post_init__(self):
        """Validate signal after initialization."""
        if self.quantity < 0:
            raise ValueError(f"Signal quantity must be non-negative, got: {self.quantity}")
        
        if self.signal_type != SignalType.HOLD and self.quantity == 0:
            raise ValueError(f"Signal quantity must be positive for {self.signal_type.value} signals")
        
        if self.price_limit is not None and self.price_limit <= 0:
            raise ValueError(f"Price limit must be positive, got: {self.price_limit}")
    
    def is_actionable(self) -> bool:
        """Check if signal requires action (not HOLD).
        
        Returns:
            True if signal is BUY or SELL, False if HOLD
        """
        return self.signal_type != SignalType.HOLD

