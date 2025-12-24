"""Unit tests for timeboxed_trend_v1 strategy."""

import unittest
from datetime import datetime, timedelta
from src.integration.timeboxed_trend_emitter import TimeboxedTrendEmitter
from src.engines.simple import RawReturns


class TestTimeboxedTrendStrategy(unittest.TestCase):
    """Test timeboxed trend strategy signal generation."""
    
    def test_entry_occurs(self):
        """Test that entry occurs when price > 20-day high."""
        # Create price series with upward trend
        # Start at 100, then increase to 110 over 25 days
        base_price = 100.0
        dates = []
        returns = []
        
        # Generate 25 days of data
        for i in range(25):
            dates.append((datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d"))
            if i < 20:
                # First 20 days: flat at 100
                returns.append(0.0)
            else:
                # Days 21-25: increase to 110
                returns.append(0.05)  # 5% per day
        
        raw_returns = RawReturns(
            dates=dates,
            returns=returns,
            initial_capital=50000.0,
            final_value=50000.0
        )
        
        emitter = TimeboxedTrendEmitter(lookback_days=20, hold_days=10)
        signals = list(emitter.emit_signals(raw_returns, instrument="ES"))
        
        # Should have signals starting from day 20 (after lookback period)
        self.assertGreater(len(signals), 0, "Should generate signals")
        
        # Find entry signal (first BUY)
        buy_signals = [s for s in signals if s.action == "buy"]
        self.assertGreater(len(buy_signals), 0, "Should generate at least one BUY signal")
    
    def test_exit_occurs_after_hold_days(self):
        """Test that exit occurs exactly hold_days after entry."""
        # Create price series: flat for 20 days, then spike, then hold
        dates = []
        returns = []
        
        # Generate 35 days: 20 flat, then spike on day 21, then flat for 14 more
        for i in range(35):
            dates.append((datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d"))
            if i == 20:
                # Day 21: spike up (triggers entry)
                returns.append(0.1)  # 10% spike
            else:
                returns.append(0.0)  # Flat
        
        raw_returns = RawReturns(
            dates=dates,
            returns=returns,
            initial_capital=50000.0,
            final_value=50000.0
        )
        
        emitter = TimeboxedTrendEmitter(lookback_days=20, hold_days=10)
        signals = list(emitter.emit_signals(raw_returns, instrument="ES"))
        
        # Find entry and exit signals
        buy_signals = [s for s in signals if s.action == "buy"]
        sell_signals = [s for s in signals if s.action == "sell"]
        
        self.assertGreater(len(buy_signals), 0, "Should have entry signal")
        self.assertGreater(len(sell_signals), 0, "Should have exit signal")
        
        # Verify exit occurs exactly hold_days after entry
        if buy_signals and sell_signals:
            entry_cycle = buy_signals[0].strategy_context["entry_cycle_index"]
            exit_signal = sell_signals[0]
            exit_cycle = exit_signal.strategy_context["cycle_index"]
            
            cycles_held = exit_cycle - entry_cycle
            self.assertEqual(cycles_held, 10, f"Exit should occur exactly 10 cycles after entry, got {cycles_held}")
    
    def test_trade_count_over_365_cycles(self):
        """Test that strategy generates multiple trades over 365 cycles."""
        # Generate 365 days of data with multiple trend opportunities
        dates = []
        returns = []
        
        # Create pattern: flat periods followed by spikes (multiple entry opportunities)
        for i in range(365):
            dates.append((datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d"))
            # Create spikes every 30 days
            if i % 30 == 20 and i >= 20:  # Day 21, 51, 81, etc. (after 20-day lookback)
                returns.append(0.1)  # 10% spike (triggers entry)
            else:
                returns.append(0.001)  # Small positive drift
        
        raw_returns = RawReturns(
            dates=dates,
            returns=returns,
            initial_capital=50000.0,
            final_value=50000.0
        )
        
        emitter = TimeboxedTrendEmitter(lookback_days=20, hold_days=10)
        signals = list(emitter.emit_signals(raw_returns, instrument="ES"))
        
        buy_signals = [s for s in signals if s.action == "buy"]
        sell_signals = [s for s in signals if s.action == "sell"]
        
        # Should have multiple trades (entry + exit pairs)
        # With spikes every 30 days and 10-day hold, we should get multiple round trips
        self.assertGreater(len(buy_signals), 1, "Should have multiple entry signals over 365 cycles")
        self.assertGreater(len(sell_signals), 1, "Should have multiple exit signals over 365 cycles")
        
        # Trade count = number of complete round trips (min of buys and sells)
        trade_count = min(len(buy_signals), len(sell_signals))
        self.assertGreater(trade_count, 1, f"Should have more than 1 trade over 365 cycles, got {trade_count}")


if __name__ == "__main__":
    unittest.main()

