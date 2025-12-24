"""Tests for Phase 0 equity movement invariants.

Critical: Positions must be marked to market every cycle, even when no trades occur.
This test locks the mark-to-market behavior to prevent regression.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest import TestCase
import zoneinfo

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.execution import PaperExecutionEngine
from src.execution.position import Position
from src.execution.fill import Fill
from src.core.artifacts import LocalArtifactStore
from src.execution.clock import SimulationClock
from src.execution.id_provider import SimulationIDProvider
from src.rules.drawdown import calculate_portfolio_equity


class TestPhase0EquityMovement(TestCase):
    """Test that equity moves when positions exist and prices change, even without new trades."""
    
    def test_mark_to_market_without_new_trades(self):
        """Test that existing positions are marked to market when prices change, even with zero trades.
        
        This test locks the Phase 0 fix: positions must be marked to market every cycle
        using current cycle prices, not just when fills occur.
        
        Scenario:
        - Cycle 1: Position opened at $100.00
        - Cycle 2: No trades, price becomes $110.00
        - Expected: Unrealized PnL ≠ 0, equity changes
        """
        # Create artifact store and execution engine
        artifact_store = LocalArtifactStore(Path("./artifacts_test_phase0_equity"))
        engine = PaperExecutionEngine(
            instrument="AAPL",
            artifact_store=artifact_store,
            clock=SimulationClock(),
            id_provider=SimulationIDProvider()
        )
        
        # Cycle 1: Create position at $100.00
        cycle1_timestamp = datetime(2024, 1, 1, 10, 0, 0)
        cycle1_price = 100.0
        
        # Create a position by simulating a fill
        from src.execution.order import Order, OrderStatus, OrderType
        from src.execution.signal import Signal, SignalType
        
        # Create order and fill manually to establish position
        order = Order(
            id="test_order_1",
            signal_id=None,
            instrument="AAPL",
            order_type=OrderType.MARKET,
            side="buy",
            quantity=100.0,
            status=OrderStatus.ACCEPTED,
            created_at=cycle1_timestamp,
            accepted_at=cycle1_timestamp
        )
        
        fill = Fill(
            id="test_fill_1",
            order_id="test_order_1",
            instrument="AAPL",
            side="buy",
            quantity=100.0,
            price=cycle1_price,
            fee=0.0,
            filled_at=cycle1_timestamp
        )
        
        # Execute the fill to create position
        engine.orders[order.id] = order
        engine.fills[order.id] = [fill]
        engine.last_price_by_instrument["AAPL"] = cycle1_price
        
        # Apply fill to position
        position = Position(
            instrument="AAPL",
            quantity=100.0,
            cost_basis=cycle1_price,
            realized_pnl=0.0,
            updated_at=cycle1_timestamp
        )
        engine.positions["AAPL"] = position
        
        # Verify cycle 1 state
        self.assertIn("AAPL", engine.positions)
        self.assertEqual(engine.positions["AAPL"].quantity, 100.0)
        self.assertEqual(engine.positions["AAPL"].cost_basis, 100.0)
        self.assertIn("AAPL", engine.last_price_by_instrument)
        self.assertEqual(engine.last_price_by_instrument["AAPL"], 100.0)
        
        # Cycle 1 equity calculation
        initial_cash = 10000.0
        cycle1_prices = {"AAPL": cycle1_price}
        cycle1_equity, cycle1_unrealized = calculate_portfolio_equity(
            initial_cash=initial_cash,
            positions=engine.positions,
            current_prices=cycle1_prices,
            realized_pnl=0.0
        )
        
        # Cycle 1: No unrealized PnL (price = cost basis)
        self.assertEqual(cycle1_unrealized, 0.0, "Cycle 1: No unrealized PnL when price = cost basis")
        self.assertEqual(cycle1_equity, 10000.0 + 0.0 + 0.0, "Cycle 1: Equity = cash (no PnL)")
        
        # Cycle 2: No new trades, but price changes to $110.00
        cycle2_timestamp = datetime(2024, 1, 2, 10, 0, 0)
        cycle2_price = 110.0
        
        # Update market prices (this is what the fix does)
        engine.update_market_prices(
            current_prices={"AAPL": cycle2_price},
            timestamp=cycle2_timestamp
        )
        
        # Verify price was updated
        self.assertEqual(engine.last_price_by_instrument["AAPL"], 110.0, 
                        "Cycle 2: Price should be updated to $110.00")
        
        # Cycle 2 equity calculation (using updated prices)
        cycle2_prices = {"AAPL": cycle2_price}
        cycle2_equity, cycle2_unrealized = calculate_portfolio_equity(
            initial_cash=initial_cash,
            positions=engine.positions,  # Same positions, no new trades
            current_prices=cycle2_prices,
            realized_pnl=0.0  # No realized PnL (no trades)
        )
        
        # Cycle 2: Must have unrealized PnL (price > cost basis)
        expected_unrealized = (110.0 - 100.0) * 100.0  # $1,000
        self.assertNotEqual(cycle2_unrealized, 0.0, 
                          "Cycle 2: Unrealized PnL must be non-zero when price changes")
        self.assertEqual(cycle2_unrealized, expected_unrealized,
                        f"Cycle 2: Unrealized PnL should be ${expected_unrealized:.2f}")
        
        # Cycle 2: Equity must change
        self.assertNotEqual(cycle2_equity, cycle1_equity,
                          "Cycle 2: Equity must change when price changes")
        self.assertEqual(cycle2_equity, initial_cash + 0.0 + expected_unrealized,
                        f"Cycle 2: Equity should be ${initial_cash + expected_unrealized:.2f}")
        
        # Verify no dependency on new fills
        # (Position was created in cycle 1, no fills in cycle 2)
        self.assertEqual(len(engine.fills), 1, "Should only have cycle 1 fill")
        self.assertEqual(len([f for f_list in engine.fills.values() for f in f_list]), 1,
                        "Should only have one fill total")
        
        # Cycle 3: Price drops to $95.00, still no trades
        cycle3_timestamp = datetime(2024, 1, 3, 10, 0, 0)
        cycle3_price = 95.0
        
        engine.update_market_prices(
            current_prices={"AAPL": cycle3_price},
            timestamp=cycle3_timestamp
        )
        
        cycle3_prices = {"AAPL": cycle3_price}
        cycle3_equity, cycle3_unrealized = calculate_portfolio_equity(
            initial_cash=initial_cash,
            positions=engine.positions,
            current_prices=cycle3_prices,
            realized_pnl=0.0
        )
        
        # Cycle 3: Unrealized PnL should be negative (price < cost basis)
        expected_unrealized_3 = (95.0 - 100.0) * 100.0  # -$500
        self.assertEqual(cycle3_unrealized, expected_unrealized_3,
                        f"Cycle 3: Unrealized PnL should be ${expected_unrealized_3:.2f}")
        self.assertLess(cycle3_equity, cycle2_equity,
                       "Cycle 3: Equity should decrease when price drops")
        
        # Still no new fills
        self.assertEqual(len(engine.fills), 1, "Should still only have cycle 1 fill")

