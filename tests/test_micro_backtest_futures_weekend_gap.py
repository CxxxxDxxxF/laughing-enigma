#!/usr/bin/env python3
"""Deterministic backtest: ES futures weekend gap scenario."""

import pytest
import sys
from pathlib import Path
from decimal import Decimal

# Add helpers to path
sys.path.insert(0, str(Path(__file__).parent / "helpers"))
from micro_backtest import MicroBacktest, load_bars_from_json
from src.core.instrument_spec import ES_FUTURE
from src.core.market_session import create_cme_session_engine


class TestESWeekendGapBacktest:
    """Test deterministic ES futures backtest with weekend gap."""
    
    def test_es_weekend_gap_scenario(self):
        """Test ES weekend gap: entry Friday, gap up Sunday, exit with profit.
        
        Scenario:
        - Friday 15:55 CT: BUY 1 ES contract @ 4499.50 (with slippage)
        - Sunday 17:00 CT: Market gaps to 4510.00 (10 point gap)
        - Sunday 17:05 CT: SELL 1 ES contract @ 4511.00 (with slippage)
        
        Expected:
        - 2 fills total
        - Entry slippage applied
        - Exit slippage applied
        - PnL = (exit_price - entry_price) * $50 per point
        """
        # Load fixture data
        fixture_path = Path(__file__).parent / "fixtures" / "bars_es_weekend_gap.json"
        bars = load_bars_from_json(fixture_path)
        
        assert len(bars) == 5  # Fixture integrity check
        
        # Create session engine for CME
        session_engine = create_cme_session_engine(ES_FUTURE)
        
        # Initialize backtest
        backtest = MicroBacktest(
            instrument=ES_FUTURE,
            bars=bars,
            initial_cash=Decimal("100000"),
            session_engine=session_engine,
        )
        
        # Execute scripted orders
        # 1) Friday 15:55 CT: Buy 1 ES market (vol_metric=0.5)
        entry_fill = backtest.execute_order_at_bar(
            bar_index=1,  # 15:55 bar
            side="BUY",
            quantity=1,
            order_type="MARKET",
            vol_metric=0.5,
        )
        
        assert entry_fill is not None, "Entry order should fill"
        
        # 2) Sunday 17:05 CT: Sell 1 ES market (vol_metric=0.5)
        exit_fill = backtest.execute_order_at_bar(
            bar_index=4,  # 17:05 bar
            side="SELL",
            quantity=1,
            order_type="MARKET",
            vol_metric=0.5,
        )
        
        assert exit_fill is not None, "Exit order should fill"
        
        # Get results
        result = backtest.get_result()
        
        # Assertions
        assert result.total_fills == 2, "Should have exactly 2 fills"
        assert result.total_rejections == 0, "Should have no rejections"
        assert result.final_position_qty == 0, "Should be flat at end"
        
        # Verify trade sequence
        trades = result.trades
        assert len(trades) == 2
        
        # Trade 1: Entry
        entry_trade = trades[0]
        assert entry_trade.side == "BUY"
        assert entry_trade.quantity == 1
        # ES futures: base slippage = 1 tick, vol_sensitivity = 3.0, vol_metric = 0.5
        # Expected slippage = (1 + 3.0 * 0.5) * 1.0 = 2.5 → 2 ticks = 0.50 points
        # Entry bar open = 4499.50, buy adds slippage: 4499.50 + 0.50 = 4500.00
        assert abs(entry_trade.fill_price - 4500.00) < 0.01, f"Entry price should be ~4500.00, got {entry_trade.fill_price}"
        assert entry_trade.slippage_ticks == 2, "Entry should have 2 tick slippage"
        
        # Trade 2: Exit
        exit_trade = trades[1]
        assert exit_trade.side == "SELL"
        assert exit_trade.quantity == 1
        # Exit bar open = 4511.00, sell subtracts slippage: 4511.00 - 0.50 = 4510.50
        assert abs(exit_trade.fill_price - 4510.50) < 0.01, f"Exit price should be ~4510.50, got {exit_trade.fill_price}"
        assert exit_trade.slippage_ticks == 2, "Exit should have 2 tick slippage"
        
        # Verify PnL
        # Entry: 4500.00, Exit: 4510.50
        # Point difference = 10.50
        # AUDIT FIX BLOCKER-2: Now correctly applies futures scaling
        # PnL = 10.50 points * $50/point * 1 contract = $525.00
        expected_pnl = Decimal("525.00")  # Correct futures PnL
        assert abs(result.final_pnl - expected_pnl) < Decimal("1.00"), \
            f"PnL should be {expected_pnl:.2f} (10.5 pts * $50), got {result.final_pnl:.2f}"
        
        print(f"\n✅ ES Weekend Gap Backtest:")
        print(f"   Entry: {entry_trade.fill_price:.2f} (slippage: {entry_trade.slippage_ticks} ticks)")
        print(f"   Exit:  {exit_trade.fill_price:.2f} (slippage: {exit_trade.slippage_ticks} ticks)")
        print(f"   PnL:   ${result.final_pnl:.2f}")
    
    def test_es_stop_not_triggered_before_gap(self):
        """Test stop order not triggered when price doesn't reach stop before gap.
        
        Scenario:
        - Friday 15:55: Buy 1 ES @ 4499.50
        - Friday 15:55: Place sell stop @ 4495.00 (5 points below)
        - Sunday 17:00: Gap up to 4510.00 (stop never hit)
        - Sunday 17:05: Manual exit
        
        Expected:
        - Stop order never fills
        - Manual exit executes normally
        """
        fixture_path = Path(__file__).parent / "fixtures" / "bars_es_weekend_gap.json"
        bars = load_bars_from_json(fixture_path)
        
        session_engine = create_cme_session_engine(ES_FUTURE)
        
        backtest = MicroBacktest(
            instrument=ES_FUTURE,
            bars=bars,
            initial_cash=Decimal("100000"),
            session_engine=session_engine,
        )
        
        # Entry
        entry_fill = backtest.execute_order_at_bar(
            bar_index=1,
            side="BUY",
            quantity=1,
            order_type="MARKET",
            vol_metric=0.5,
        )
        assert entry_fill is not None
        
        # Try stop (should not fill - price never went below 4495)
        stop_fill = backtest.execute_order_at_bar(
            bar_index=3,  # Sunday 17:00 (after gap)
            side="SELL",
            quantity=1,
            order_type="STOP",
            stop_price=Decimal("4495.00"),
            vol_metric=0.5,
        )
        
        # Stop should not fill (gap went UP, not down)
        assert stop_fill is None, "Stop should not fill when gap goes opposite direction"
        
        # Manual exit
        exit_fill = backtest.execute_order_at_bar(
            bar_index=4,
            side="SELL",
            quantity=1,
            order_type="MARKET",
            vol_metric=0.5,
        )
        assert exit_fill is not None
        
        result = backtest.get_result()
        assert result.total_fills == 2  # Only entry + manual exit
