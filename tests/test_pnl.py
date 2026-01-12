#!/usr/bin/env python3
"""Tests for centralized PnL calculation with futures scaling.

AUDIT REMEDIATION: BLOCKER-2
Regression tests proving futures PnL includes point_value * contract_multiplier.
"""

import pytest
from decimal import Decimal

from src.core.pnl import calculate_realized_pnl_usd
from src.core.instrument_spec import ES_FUTURE, NQ_FUTURE, AAPL_EQUITY, AssetClass, InstrumentSpec


class TestFuturesPnLScaling:
    """Test that futures PnL correctly includes 50x multiplier for ES."""
    
    def test_es_long_10_points_yields_500_usd(self):
        """BLOCKER-2 REGRESSION: ES 10-point move = $500, not $10."""
        # ES: $50 per point, 1 contract multiplier
        # 10 points * $50/point * 1 contract = $500
        
        pnl = calculate_realized_pnl_usd(
            instrument=ES_FUTURE,
            entry_price=4500.00,
            exit_price=4510.00,
            qty=1,  # 1 contract long
        )
        
        expected = 10.0 * 50.0 * 1  #  $500.00
        assert abs(pnl - expected) < 0.01, f"Expected ${expected:.2f}, got ${pnl:.2f}"
    
    def test_nq_long_1_point_yields_20_usd(self):
        """NQ: $20 per point."""
        # NQ: $20 per point, 1 contract multiplier
        # 1 point * $20/point * 1 contract = $20
        
        pnl = calculate_realized_pnl_usd(
            instrument=NQ_FUTURE,
            entry_price=20000.00,
            exit_price=20001.00,
            qty=1,
        )
        
        expected = 1.0 * 20.0 * 1  # $20.00
        assert abs(pnl - expected) < 0.01, f"Expected ${expected:.2f}, got ${pnl:.2f}"
    
    def test_es_short_10_points_profit(self):
        """ES short: sell high, buy low = profit."""
        # Short 1 contract @ 4500, cover @ 4490
        # Profit = 10 points * $50 = $500
        
        pnl = calculate_realized_pnl_usd(
            instrument=ES_FUTURE,
            entry_price=4500.00,
            exit_price=4490.00,
            qty=-1,  # 1 contract short
        )
        
        expected = -10.0 * 50.0 * (-1)  # $500 profit
        assert abs(pnl - expected) < 0.01, f"Expected ${expected:.2f}, got ${pnl:.2f}"
    
    def test_es_long_5_contracts(self):
        """Multiple contracts scale correctly."""
        pnl = calculate_realized_pnl_usd(
            instrument=ES_FUTURE,
            entry_price=4500.00,
            exit_price=4502.00,
            qty=5,  # 5 contracts
        )
        
        expected = 2.0 * 50.0 * 5  # $500
        assert abs(pnl - expected) < 0.01, f"Expected $500.00, got ${pnl:.2f}"
    
    def test_equity_sanity_100_shares(self):
        """Equities remain simple price-diff * shares."""
        pnl = calculate_realized_pnl_usd(
            instrument=AAPL_EQUITY,
            entry_price=150.00,
            exit_price=151.00,
            qty=100,
        )
        
        expected = 1.0 * 100  # $100
        assert abs(pnl - expected) < 0.01, f"Expected $100.00, got ${pnl:.2f}"
    
    def test_equity_short_loss(self):
        """Equity short with loss."""
        pnl = calculate_realized_pnl_usd(
            instrument=AAPL_EQUITY,
            entry_price=150.00,
            exit_price=152.00,
            qty=-100,  # Short 100 shares
        )
        
        expected = 2.0 * (-100)  # -$200 loss
        assert abs(pnl - expected) < 0.01, f"Expected -$200.00, got ${pnl:.2f}"
    
    def test_invalid_prices_return_zero(self):
        """Invalid prices don't crash, return 0."""
        pnl = calculate_realized_pnl_usd(
            instrument=ES_FUTURE,
            entry_price=0.0,  # Invalid
            exit_price=4510.00,
            qty=1,
        )
        
        assert pnl == 0.0
    
    def test_nan_prices_return_zero(self):
        """NaN prices safely return 0."""
        pnl = calculate_realized_pnl_usd(
            instrument=ES_FUTURE,
            entry_price=float('nan'),
            exit_price=4510.00,
            qty=1,
        )
        
        assert pnl == 0.0


class TestPositionPnLIntegration:
    """Integration tests for Position.apply_fill with instrument spec."""
    
    def test_position_es_close_uses_futures_scaling(self):
        """Closing ES position calculates PnL with 50x scaling."""
        from src.execution.position import Position
        from src.execution.fill import Fill
        from datetime import datetime
        
        # Create ES position: long 1 @ 4500
        pos = Position(
            instrument="ES",
            quantity=1,
            cost_basis=4500.00,
            realized_pnl=0.0,
        )
        
        # Close at 4510
        fill = Fill(
            id="fill1",
            order_id="order1",
            instrument="ES",
            side="sell",
            quantity=1,
            price=4510.00,
            fee=0.0,
            filled_at=datetime(2026, 1, 11, 10, 0),
        )
        
        # Apply fill WITH instrument spec
        new_pos = pos.apply_fill(fill, instrument=ES_FUTURE)
        
        # Should have realized $500 PnL (not $10)
        expected_pnl = 500.00
        assert abs(new_pos.realized_pnl - expected_pnl) < 0.01, \
            f"Expected ${expected_pnl:.2f} PnL, got ${new_pos.realized_pnl:.2f}"
        assert new_pos.quantity == 0
    
    def test_position_equity_close_remains_simple(self):
        """Closing equity position uses simple price-diff."""
        from src.execution.position import Position
        from src.execution.fill import Fill
        from datetime import datetime
        
        # Create AAPL position: long 100 @ 150
        pos = Position(
            instrument="AAPL",
            quantity=100,
            cost_basis=150.00,
            realized_pnl=0.0,
        )
        
        # Close at 151
        fill = Fill(
            id="fill1",
            order_id="order1",
            instrument="AAPL",
            side="sell",
            quantity=100,
            price=151.00,
            fee=0.0,
            filled_at=datetime(2026, 1, 11, 10, 0),
        )
        
        new_pos = pos.apply_fill(fill, instrument=AAPL_EQUITY)
        
        # Should have $100 PnL
        expected_pnl = 100.00
        assert abs(new_pos.realized_pnl - expected_pnl) < 0.01, \
            f"Expected ${expected_pnl:.2f} PnL, got ${new_pos.realized_pnl:.2f}"
    
    def test_position_reduce_es_calculates_partial_futures_pnl(self):
        """Reducing ES position by 1 contract calculates correct partial PnL."""
        from src.execution.position import Position
        from src.execution.fill import Fill
        from datetime import datetime
        
        # Long 2 ES @ 4500
        pos = Position(
            instrument="ES",
            quantity=2,
            cost_basis=4500.00,
            realized_pnl=0.0,
        )
        
        # Sell 1 @ 4510 (reduce by half)
        fill = Fill(
            id="fill1",
            order_id="order1",
            instrument="ES",
            side="sell",
            quantity=1,
            price=4510.00,
            fee=0.0,
            filled_at=datetime(2026, 1, 11, 10, 0),
        )
        
        new_pos = pos.apply_fill(fill, instrument=ES_FUTURE)
        
        # Closed 1 contract: 10 points * $50 = $500
        expected_pnl = 500.00
        assert abs(new_pos.realized_pnl - expected_pnl) < 0.01, \
            f"Expected ${expected_pnl:.2f} PnL, got ${new_pos.realized_pnl:.2f}"
        assert new_pos.quantity == 1  # Still holding 1
