"""Dual Momentum Strategy Implementation.

This strategy implements a simplified Dual Momentum approach:
1. Absolute Momentum: Checks if the asset is in a positive trend (return > threshold).
2. Relative Momentum: (Placeholder) Could compare against other assets.

For this single-asset implementation, it acts as a Trend Following strategy.
"""

from typing import Dict, Any, Optional
import numpy as np
from ..factory import Strategy
from ...execution.signal import Signal, SignalType
from datetime import datetime

class DualMomentumStrategy(Strategy):
    """Dual Momentum Strategy implementation."""
    
    def __init__(self, 
                 lookback_days: int = 126, 
                 threshold: float = 0.0,
                 instrument: str = "AAPL",
                 strategy_id: str = "dual_momentum_v1",
                 **kwargs):
        """Initialize strategy parameters.
        
        Args:
            lookback_days: Number of days to calculate momentum (default 126 ~ 6 months)
            threshold: Minimum return required to generate BUY signal (default 0.0)
            instrument: Target instrument identifier
            strategy_id: Unique identifier for this strategy instance
            **kwargs: Ignored extra arguments
        """
        self.lookback_days = lookback_days
        self.threshold = threshold
        self.instrument = instrument
        self.strategy_id = strategy_id
        
    def generate_signals(self, market_data: Any) -> Optional[Signal]:
        """Generate signals based on market data.
        
        Args:
            market_data: Object providing prices. Must support get_history(instrument, days).
                         Structure expected: {instrument: [p1, p2, ..., pn]} (list of floats)
                         OR a Mock/Real provider with a get_history method.
                         
                         For MVP, we assume market_data is a dict-like interface 
                         returning a list of closing prices.
        
        Returns:
            Signal object (BUY/SELL) or None if insufficient data.
        """
        # 1. Get Historical Data
        # Handling different potential market_data interfaces
        prices = []
        if hasattr(market_data, "get_history"):
            prices = market_data.get_history(self.instrument, self.lookback_days + 1)
        elif isinstance(market_data, dict) and self.instrument in market_data:
            prices = market_data[self.instrument]
        
        # Check if we have enough data
        if len(prices) <= self.lookback_days:
            # Not enough data for momentum calculation
            return None
            
        # 2. Calculate Momentum
        # Simple return: (Current Price / Price N days ago) - 1
        current_price = prices[-1]
        past_price = prices[-(self.lookback_days + 1)] # Indexing logic
        
        momentum = (current_price / past_price) - 1.0
        
        # 3. Generate Signal
        timestamp = datetime.now() # In live execution this should come from context
        
        if momentum > self.threshold:
            # Positive trend -> BUY
            return Signal(
                timestamp=timestamp,
                instrument=self.instrument,
                signal_type=SignalType.BUY,
                quantity=1.0, # Placeholder quantity logic
                strategy_id=self.strategy_id,
                metadata={"momentum": momentum, "threshold": self.threshold}
            )
        else:
            # Negative/Weak trend -> SELL (to Cash)
            return Signal(
                timestamp=timestamp,
                instrument=self.instrument,
                signal_type=SignalType.SELL,
                quantity=1.0, # Placeholder: Close position
                strategy_id=self.strategy_id,
                metadata={"momentum": momentum, "threshold": self.threshold}
            )
