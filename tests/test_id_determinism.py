"""Tests for ID determinism in LIVE/LIVE_DRY mode."""

import sys
from pathlib import Path
from datetime import datetime
from unittest import TestCase, mock
from typing import List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.execution.paper_engine import PaperExecutionEngine
from src.execution.signal import Signal, SignalType
from src.execution.clock import FixedClock
from src.execution.id_provider import DeterministicIDProvider, SimulationIDProvider
from src.lifecycle.runner import ExecutionMode


class TestIDDeterminism(TestCase):
    """Test ID determinism in LIVE/LIVE_DRY mode."""
    
    def test_same_inputs_same_order_ids(self):
        """Test that same cycle_id + same inputs = same order IDs."""
        cycle_id = "cycle_20240101_120000"
        clock = FixedClock(datetime(2024, 1, 1, 12, 0, 0))
        id_provider = DeterministicIDProvider(seed=cycle_id)
        
        engine1 = PaperExecutionEngine(
            instrument="AAPL",
            clock=clock,
            id_provider=id_provider
        )
        engine2 = PaperExecutionEngine(
            instrument="AAPL",
            clock=clock,
            id_provider=DeterministicIDProvider(seed=cycle_id)  # New instance, same seed
        )
        
        # Create identical signals
        signal1 = Signal(
            instrument="AAPL",
            signal_type=SignalType.BUY,
            quantity=100.0,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            strategy_id="test_strategy"
        )
        signal2 = Signal(
            instrument="AAPL",
            signal_type=SignalType.BUY,
            quantity=100.0,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            strategy_id="test_strategy"
        )
        
        # Submit orders - should get same IDs
        order1 = engine1.submit_order(signal1)
        order2 = engine2.submit_order(signal2)
        
        self.assertEqual(order1.id, order2.id, "Order IDs should be identical for same seed and inputs")
    
    def test_same_inputs_same_fill_ids(self):
        """Test that same cycle_id + same inputs = same fill IDs."""
        cycle_id = "cycle_20240101_120000"
        clock = FixedClock(datetime(2024, 1, 1, 12, 0, 0))
        id_provider = DeterministicIDProvider(seed=cycle_id)
        
        engine = PaperExecutionEngine(
            instrument="AAPL",
            clock=clock,
            id_provider=id_provider
        )
        
        signal = Signal(
            instrument="AAPL",
            signal_type=SignalType.BUY,
            quantity=100.0,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            strategy_id="test_strategy"
        )
        
        # Submit and execute order
        order = engine.submit_order(signal)
        fills1 = engine.execute_order(order, current_price=150.0, timestamp=datetime(2024, 1, 1, 12, 0, 0))
        
        # Create new engine with same seed (should produce same IDs)
        engine2 = PaperExecutionEngine(
            instrument="AAPL",
            clock=clock,
            id_provider=DeterministicIDProvider(seed=cycle_id)
        )
        order2 = engine2.submit_order(signal)
        fills2 = engine2.execute_order(order2, current_price=150.0, timestamp=datetime(2024, 1, 1, 12, 0, 0))
        
        self.assertEqual(len(fills1), 1)
        self.assertEqual(len(fills2), 1)
        self.assertEqual(fills1[0].id, fills2[0].id, "Fill IDs should be identical for same seed and inputs")
    
    def test_different_cycle_id_different_ids(self):
        """Test that different cycle_id = different IDs."""
        clock = FixedClock(datetime(2024, 1, 1, 12, 0, 0))
        
        engine1 = PaperExecutionEngine(
            instrument="AAPL",
            clock=clock,
            id_provider=DeterministicIDProvider(seed="cycle_20240101_120000")
        )
        engine2 = PaperExecutionEngine(
            instrument="AAPL",
            clock=clock,
            id_provider=DeterministicIDProvider(seed="cycle_20240102_120000")  # Different seed
        )
        
        signal = Signal(
            instrument="AAPL",
            signal_type=SignalType.BUY,
            quantity=100.0,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            strategy_id="test_strategy"
        )
        
        order1 = engine1.submit_order(signal)
        order2 = engine2.submit_order(signal)
        
        self.assertNotEqual(order1.id, order2.id, "Order IDs should differ for different seeds")
    
    def test_live_mode_no_uuid_calls(self):
        """Test that LIVE mode does not call uuid.uuid4()."""
        cycle_id = "cycle_20240101_120000"
        clock = FixedClock(datetime(2024, 1, 1, 12, 0, 0))
        id_provider = DeterministicIDProvider(seed=cycle_id)
        
        engine = PaperExecutionEngine(
            instrument="AAPL",
            clock=clock,
            id_provider=id_provider
        )
        
        signal = Signal(
            instrument="AAPL",
            signal_type=SignalType.BUY,
            quantity=100.0,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            strategy_id="test_strategy"
        )
        
        # Monkey-patch uuid.uuid4 to track calls
        with mock.patch('uuid.uuid4') as mock_uuid:
            order = engine.submit_order(signal)
            fills = engine.execute_order(order, current_price=150.0, timestamp=datetime(2024, 1, 1, 12, 0, 0))
            
            # uuid4 should never be called when using DeterministicIDProvider
            mock_uuid.assert_not_called()
            
            # Verify IDs are deterministic (not UUIDs)
            self.assertNotIn('-', order.id, "Order ID should not be a UUID format")
            self.assertIn(cycle_id, order.id, "Order ID should contain seed")
            
            if fills:
                self.assertNotIn('-', fills[0].id, "Fill ID should not be a UUID format")
                self.assertIn(order.id, fills[0].id, "Fill ID should contain order ID")
    
    def test_simulation_mode_can_use_uuid(self):
        """Test that SIMULATION mode can use UUIDs (no restriction)."""
        engine = PaperExecutionEngine(
            instrument="AAPL",
            id_provider=SimulationIDProvider()  # Default uses UUIDs
        )
        
        signal = Signal(
            instrument="AAPL",
            signal_type=SignalType.BUY,
            quantity=100.0,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            strategy_id="test_strategy"
        )
        
        order = engine.submit_order(signal)
        
        # In simulation mode, UUIDs are allowed
        # Just verify order ID was generated (format doesn't matter)
        self.assertIsNotNone(order.id)
        self.assertIsInstance(order.id, str)
        self.assertTrue(len(order.id) > 0)

