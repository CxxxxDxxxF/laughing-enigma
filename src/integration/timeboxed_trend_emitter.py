"""Timeboxed trend strategy signal emitter.

This emitter implements a timeboxed trend-following strategy:
- Entry: Current close > 20-day high AND no position exists
- Exit: Exactly 10 cycles after entry (timeboxed)
- No stop loss
- Single position only (no pyramiding)
"""

from typing import Iterator, Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime

from .emitter import SignalEmitter, RawStrategyOutput

if TYPE_CHECKING:
    from ..engines.simple import RawReturns


class TimeboxedTrendEmitter(SignalEmitter):
    """Timeboxed trend strategy signal emitter.
    
    Strategy logic:
    - Entry: Current close > highest close of previous 20 cycles AND no position exists
    - Exit: Exactly 10 cycles after entry (timeboxed exit)
    - Position sizing: Uses default quantity (same as buy-and-hold)
    - No stop loss
    - Single position only (no pyramiding)
    
    Attributes:
        lookback_days: Number of days to look back for high (default: 20)
        hold_days: Number of days to hold position (default: 10)
        default_quantity: Default quantity for signals
    """
    
    def __init__(
        self,
        lookback_days: int = 20,
        hold_days: int = 10,
        default_quantity: float = 100.0
    ):
        """Initialize timeboxed trend emitter.
        
        Args:
            lookback_days: Days to look back for high calculation (default: 20)
            hold_days: Days to hold position before exit (default: 10)
            default_quantity: Default quantity for signals (default: 100)
        """
        if lookback_days < 1:
            raise ValueError(f"lookback_days must be at least 1, got: {lookback_days}")
        if hold_days < 1:
            raise ValueError(f"hold_days must be at least 1, got: {hold_days}")
        if default_quantity <= 0:
            raise ValueError(f"default_quantity must be positive, got: {default_quantity}")
        
        self.lookback_days = lookback_days
        self.hold_days = hold_days
        self.default_quantity = default_quantity
    
    def emit_signals(self, raw_returns: 'RawReturns', instrument: Optional[str] = None, **kwargs) -> Iterator[RawStrategyOutput]:
        """Emit signals based on timeboxed trend strategy.
        
        Process:
        1. Reconstruct price series from returns
        2. Track entry cycle index when position is opened
        3. Entry: If current close > 20-day high AND no position → BUY
        4. Exit: If position exists AND (current_cycle - entry_cycle) >= hold_days → SELL
        5. Otherwise: HOLD
        
        Args:
            raw_returns: RawReturns from backtest
            instrument: Instrument identifier (required)
            **kwargs: Additional arguments (ignored)
            
        Yields:
            RawStrategyOutput objects in chronological order
            
        Note:
            - Deterministic: same raw_returns → same signals
            - Tracks entry cycle internally to enforce timeboxed exit
        """
        if instrument is None:
            raise ValueError("instrument parameter is required")
        
        dates = raw_returns.dates
        returns = raw_returns.returns
        
        if len(dates) != len(returns):
            raise ValueError("dates and returns must have same length")
        
        if len(returns) < self.lookback_days:
            # Not enough data to calculate 20-day high
            return
        
        # Reconstruct price series from returns
        # Start with arbitrary base price (100.0) - actual price doesn't matter for signal logic
        prices = [100.0]
        for ret in returns:
            prices.append(prices[-1] * (1 + ret))
        
        # Track position state
        entry_cycle_index: Optional[int] = None  # Cycle index when position was entered
        in_position = False
        
        # Process each cycle
        for i in range(self.lookback_days, len(returns)):
            current_price = prices[i]
            
            # Calculate 20-day high (lookback from previous cycle, not including current)
            lookback_start = max(0, i - self.lookback_days)
            lookback_prices = prices[lookback_start:i]  # Previous 20 days, excluding current
            if not lookback_prices:
                # Not enough history
                highest_close = current_price  # Dummy value
            else:
                highest_close = max(lookback_prices)
            
            # Check exit condition first (timeboxed exit)
            if in_position and entry_cycle_index is not None:
                cycles_held = i - entry_cycle_index
                if cycles_held >= self.hold_days:
                    # Timeboxed exit: SELL
                    action = "sell"
                    in_position = False
                    entry_cycle_index = None
                else:
                    # Still holding: HOLD
                    action = "hold"
            # Check entry condition (only if not in position)
            elif not in_position and lookback_prices and current_price > highest_close:
                # Entry signal: BUY
                action = "buy"
                in_position = True
                entry_cycle_index = i
            else:
                # No signal: HOLD
                action = "hold"
            
            # Parse date
            try:
                timestamp = datetime.strptime(dates[i], "%Y-%m-%d")
            except ValueError:
                # If date parsing fails, use a default timestamp
                timestamp = datetime(2024, 1, 1)  # Deterministic default
            
            # Emit signal
            yield RawStrategyOutput(
                timestamp=timestamp,
                instrument=instrument,
                action=action,
                quantity=self.default_quantity if action != "hold" else 0.0,
                strategy_context={
                    "cycle_index": i,
                    "current_price": current_price,
                    "highest_close": highest_close if not lookback_prices else max(lookback_prices),
                    "in_position": in_position,
                    "entry_cycle_index": entry_cycle_index,
                    "lookback_days": self.lookback_days,
                    "hold_days": self.hold_days,
                }
            )

