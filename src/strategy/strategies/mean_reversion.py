"""Mean Reversion Strategy Implementation (RSI).

This strategy implements a Mean Reversion approach using the Relative Strength Index (RSI):
1. Calculates RSI for the asset over a specified period (default 14 days).
2. Buys when RSI is below a threshold (Oversold, e.g., 30).
3. Sells when RSI is above a threshold (Overbought, e.g., 70).

This complements momentum strategies by buying dips in sideways or choppy markets.
"""

from typing import Dict, Any, Optional, List
import numpy as np
import pandas as pd
from ..factory import Strategy
from ...execution.signal import Signal, SignalType
from datetime import datetime

class MeanReversionStrategy(Strategy):
    """Mean Reversion Strategy (RSI) implementation."""
    
    def __init__(self,
                 rsi_period: int = 14,
                 buy_threshold: float = 30.0,
                 sell_threshold: float = 70.0,
                 tickers: List[str] = None,
                 strategy_id: str = "mean_reversion_v1",
                 **kwargs):
        """Initialize strategy parameters.

        Args:
            rsi_period: Lookback period for RSI calculation.
            buy_threshold: RSI level to trigger a BUY (Oversold).
            sell_threshold: RSI level to trigger a SELL (Overbought).
            tickers: List of ticker symbols to trade.
            strategy_id: Unique identifier for this strategy instance.
        """
        self.rsi_period = rsi_period
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.tickers = tickers if tickers is not None else ["SPY"]
        self.strategy_id = strategy_id

    def generate_signals(self, 
                        market_data: Dict[str, Any], 
                        current_positions: Dict[str, float]) -> List[Signal]:
        """Generate trading signals based on RSI logic.
        
        Args:
            market_data: Dictionary mapping ticker -> price history (list/array)
            current_positions: Dictionary mapping ticker -> quantity owned
            
        Returns:
            List of Signal objects.
        """
        signals = []
        timestamp = datetime.now() 

        for ticker in self.tickers:
            if ticker not in market_data:
                continue
                
            prices = market_data[ticker]
            
            # Need at least rsi_period + 1 data points
            if len(prices) < self.rsi_period + 1:
                continue
                
            # Calculate RSI
            rsi = self._calculate_rsi(prices, self.rsi_period)
            
            # Use latest RSI value
            current_rsi = rsi[-1]
            
            # Generate Signal
            current_qty = current_positions.get(ticker, 0.0)
            
            metadata = {
                "rsi": float(current_rsi),
                "threshold_buy": self.buy_threshold,
                "threshold_sell": self.sell_threshold
            }

            if current_rsi < self.buy_threshold:
                # Oversold -> BUY
                signals.append(
                    Signal(
                        timestamp=timestamp,
                        instrument=ticker,
                        signal_type=SignalType.BUY,
                        quantity=1.0, # Placeholder, Allocator will size it
                        strategy_id=self.strategy_id,
                        metadata=metadata
                    )
                )
            elif current_rsi > self.sell_threshold:
                # Overbought -> SELL
                if current_qty > 0:
                    signals.append(
                        Signal(
                            timestamp=timestamp,
                            instrument=ticker,
                            signal_type=SignalType.SELL,
                            quantity=1.0, # Close position
                            strategy_id=self.strategy_id,
                            metadata=metadata
                        )
                    )
            # Else: Hold (No signal)
            
        return signals

    def _calculate_rsi(self, prices: List[float], period: int = 14) -> np.ndarray:
        """Calculate Relative Strength Index (RSI)."""
        prices = np.array(prices)
        deltas = np.diff(prices)
        
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        rs = up / down
        rsi = np.zeros_like(prices)
        rsi[:period] = 100. - 100. / (1. + rs)

        for i in range(period, len(prices)):
            delta = deltas[i - 1] 
            
            if delta > 0:
                upval = delta
                downval = 0.
            else:
                upval = 0.
                downval = -delta
            
            up = (up * (period - 1) + upval) / period
            down = (down * (period - 1) + downval) / period
            
            rs = up / down if down != 0 else 0
            rsi[i] = 100. - 100. / (1. + rs)
            
        return rsi
