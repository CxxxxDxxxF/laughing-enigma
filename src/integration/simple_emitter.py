"""Simple signal emitter implementation.

This module provides a minimal SignalEmitter that emits signals based on
backtest return data using a simple momentum strategy.
"""

from typing import Iterator, Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime

from .emitter import SignalEmitter, RawStrategyOutput

if TYPE_CHECKING:
    from ..engines.simple import RawReturns


class SimpleSignalEmitter(SignalEmitter):
    """Simple signal emitter based on return momentum.
    
    This emitter implements a minimal strategy that generates signals
    based on recent return momentum:
    - If return > threshold: BUY
    - If return < -threshold: SELL  
    - Otherwise: HOLD
    
    This is a minimal implementation for testing the signal pipeline.
    
    Attributes:
        lookback_days: Number of days to look back for momentum calculation
        buy_threshold: Minimum return to trigger BUY signal (as decimal)
        sell_threshold: Maximum return to trigger SELL signal (as decimal)
        default_quantity: Default quantity for signals
    """
    
    def __init__(
        self,
        lookback_days: int = 5,
        buy_threshold: float = 0.001,  # 0.1% return
        sell_threshold: float = -0.001,  # -0.1% return
        default_quantity: float = 100.0
    ):
        """Initialize simple signal emitter.
        
        Args:
            lookback_days: Days to look back for momentum (default: 5)
            buy_threshold: Minimum return for BUY signal (default: 0.1%)
            sell_threshold: Maximum return for SELL signal (default: -0.1%)
            default_quantity: Default quantity for signals (default: 100)
        """
        if lookback_days < 1:
            raise ValueError(f"lookback_days must be at least 1, got: {lookback_days}")
        
        if sell_threshold >= buy_threshold:
            raise ValueError(f"sell_threshold ({sell_threshold}) must be less than buy_threshold ({buy_threshold})")
        
        self.lookback_days = lookback_days
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.default_quantity = default_quantity
    
    def emit_signals(self, raw_returns: 'RawReturns', instrument: Optional[str] = None, **kwargs) -> Iterator[RawStrategyOutput]:
        """Emit signals based on return momentum.
        
        Process:
        1. Calculate cumulative return over lookback period
        2. If return > buy_threshold: emit BUY
        3. If return < sell_threshold: emit SELL
        4. Otherwise: emit HOLD
        
        Args:
            raw_returns: RawReturns from backtest
            instrument: Instrument identifier (required)
            **kwargs: Additional arguments (ignored)
            
        Yields:
            RawStrategyOutput objects in chronological order
            
        Note:
            - Deterministic: same raw_returns → same signals
            - May yield HOLD signals (these will be filtered by adapter)
        """
        if instrument is None:
            raise ValueError("instrument parameter is required")
        
        dates = raw_returns.dates
        returns = raw_returns.returns
        
        if len(dates) != len(returns):
            raise ValueError("dates and returns must have same length")
        
        if len(returns) < self.lookback_days:
            # Not enough data to calculate momentum
            return
        
        # Calculate cumulative return over lookback period for each day
        for i in range(self.lookback_days - 1, len(returns)):
            # Calculate cumulative return over lookback period
            cumulative_return = 0.0
            for j in range(i - self.lookback_days + 1, i + 1):
                cumulative_return += returns[j]
            
            # Determine action based on momentum
            if cumulative_return > self.buy_threshold:
                action = "buy"
            elif cumulative_return < self.sell_threshold:
                action = "sell"
            else:
                action = "hold"
            
            # Parse date
            try:
                timestamp = datetime.strptime(dates[i], "%Y-%m-%d")
            except ValueError:
                # If date parsing fails, use a default timestamp
                timestamp = datetime.now()
            
            # Emit signal
            yield RawStrategyOutput(
                timestamp=timestamp,
                instrument=instrument,
                action=action,
                quantity=self.default_quantity if action != "hold" else 0.0,
                strategy_context={
                    "cumulative_return": cumulative_return,
                    "lookback_days": self.lookback_days,
                    "day_index": i,
                }
            )

