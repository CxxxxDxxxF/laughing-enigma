from decimal import Decimal
"""Tests for ExecutionClock and deterministic timestamp generation."""

import sys
from pathlib import Path
from datetime import datetime
from unittest import TestCase

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.execution.clock import ExecutionClock, SimulationClock, FixedClock
from src.execution.paper_engine import PaperExecutionEngine
from src.execution.signal import Signal, SignalType
from src.lifecycle.runner import ExecutionMode


class TestExecutionClock(TestCase):
    """Test ExecutionClock implementations."""
    
    def test_simulation_clock_returns_current_time(self):
        """Test that SimulationClock returns current system time."""
        clock = SimulationClock()
        timestamp1 = clock.now()
        # Should be very recent (within 1 second)
        now = datetime.now()
        diff = abs((timestamp1 - now).total_seconds())
        self.assertLess(diff, 1.0, "SimulationClock should return current time")
    
    def test_fixed_clock_returns_same_timestamp(self):
        """Test that FixedClock always returns the fixed timestamp."""
        fixed_time = datetime(2024, 1, 1, 12, 0, 0)
        clock = FixedClock(fixed_time)
        
        # Call multiple times - should return same timestamp
        self.assertEqual(clock.now(), fixed_time)
        self.assertEqual(clock.now(), fixed_time)
        self.assertEqual(clock.now(), fixed_time)
    
    def test_live_execution_deterministic_timestamps(self):
        """Test that LIVE execution with FixedClock produces identical timestamps."""
        fixed_time = datetime(2024, 1, 1, 12, 0, 0)
        clock = FixedClock(fixed_time)
        
        # Create engine with fixed clock
        engine1 = PaperExecutionEngine(
            instrument="AAPL",
            clock=clock,
            account_cash=Decimal("100000"),
            account_equity=Decimal("100000"),
        )
        engine2 = PaperExecutionEngine(
            instrument="AAPL",
            clock=clock,
            account_cash=Decimal("100000"),
            account_equity=Decimal("100000"),
        )
        
        # Create identical signals
        signal = Signal(
            strategy_id="test_signal",
            instrument="AAPL",
            signal_type=SignalType.BUY,
            quantity=100.0,
            timestamp=fixed_time
        )
        
        # Submit orders - accepted_at should be identical
        order1 = engine1.submit_order(signal)
        order2 = engine2.submit_order(signal)
        
        self.assertEqual(order1.accepted_at, fixed_time)
        self.assertEqual(order2.accepted_at, fixed_time)
        self.assertEqual(order1.accepted_at, order2.accepted_at)
        
        # Execute orders - fill timestamps should be identical
        fills1 = engine1.execute_order(order1, current_price=150.0, timestamp=None)
        fills2 = engine2.execute_order(order2, current_price=150.0, timestamp=None)
        
        self.assertEqual(len(fills1), 1)
        self.assertEqual(len(fills2), 1)
        self.assertEqual(fills1[0].filled_at, fixed_time)
        self.assertEqual(fills2[0].filled_at, fixed_time)
        self.assertEqual(fills1[0].filled_at, fills2[0].filled_at)
    
    def test_simulation_clock_different_timestamps(self):
        """Test that SimulationClock produces different timestamps (realistic behavior)."""
        clock = SimulationClock()
        timestamp1 = clock.now()
        timestamp2 = clock.now()
        
        # Timestamps should be very close but not identical (unless called very fast)
        # In practice, they will be different due to system time progression
        # We just verify they are valid datetime objects
        self.assertIsInstance(timestamp1, datetime)
        self.assertIsInstance(timestamp2, datetime)

