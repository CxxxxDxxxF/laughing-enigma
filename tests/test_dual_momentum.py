"""Unit tests for Dual Momentum Strategy."""
import unittest
from datetime import datetime, timedelta
from src.strategy.strategies.dual_momentum import DualMomentumStrategy
from src.execution.signal import SignalType

class TestDualMomentumStrategy(unittest.TestCase):
    """Test Dual Momentum Strategy logic."""
    
    def setUp(self):
        self.strategy = DualMomentumStrategy(
            tickers=["TEST_ASSET"],
            threshold=0.0,
            lookback_days=10
        )
        
    def test_insufficient_data(self):
        """Test returns None when not enough data."""
        # 5 days of data, need 10+1
        market_data = {"TEST_ASSET": [100.0] * 5}
        signals = self.strategy.generate_signals(market_data)
        self.assertEqual(len(signals), 0)
        
    def test_positive_momentum(self):
        """Test BUY signal on positive momentum."""
        # Price goes 100 -> 110 (10% up)
        # Need 11 data points (past + 10 days)
        # Index 0 is past_price (10 days ago), Index -1 is current
        prices = [100.0] * 11
        prices[-1] = 110.0 # Jump to 110 today
        
        market_data = {"TEST_ASSET": prices}
        signals = self.strategy.generate_signals(market_data)
        
        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.signal_type, SignalType.BUY)
        self.assertEqual(signal.instrument, "TEST_ASSET")
        self.assertAlmostEqual(signal.metadata["momentum"], 0.10)
        
    def test_negative_momentum(self):
        """Test SELL signal on negative momentum."""
        # Price goes 100 -> 90 (10% down)
        prices = [100.0] * 11
        prices[-1] = 90.0
        
        market_data = {"TEST_ASSET": prices}
        signals = self.strategy.generate_signals(market_data)
        
        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.signal_type, SignalType.SELL)
        self.assertAlmostEqual(signal.metadata["momentum"], -0.10)
        
    def test_threshold_logic(self):
        """Test threshold parameter."""
        # Threshold 5%
        custom_strategy = DualMomentumStrategy(lookback_days=10, threshold=0.05, tickers=["TEST"])
        
        # 4% gain (below threshold) -> Should SELL/Exit
        prices = [100.0] * 10 + [104.0] 
        signals = custom_strategy.generate_signals({"TEST": prices})
        self.assertEqual(signals[0].signal_type, SignalType.SELL)
        
        # 6% gain (above threshold) -> Should BUY
        prices = [100.0] * 10 + [106.0] 
        signals = custom_strategy.generate_signals({"TEST": prices})
        self.assertEqual(signals[0].signal_type, SignalType.BUY)
