#!/usr/bin/env python3
"""Tests for gap-aware fill simulation."""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.execution.gap_fills import (
    simulate_gap_fill,
    detect_gap,
    BarData,
    OrderType,
    FillReason,
    GapFillResult,
)
from src.core.instrument_spec import ES_FUTURE, AAPL_EQUITY, InstrumentSpec
from src.core.market_session import MarketSessionEngine, create_cme_session_engine, create_equity_session_engine
from src.core.market_hours import CME_FUTURES, US_EQUITIES


class TestGapDetection:
    """Test gap detection logic."""
    
    def test_no_gap_detected(self):
        """Test no gap when price moves within threshold."""
        # ES tick = 0.25, gap < 2 ticks (< 0.50)
        previous_close = Decimal("4500.00")
        current_open = Decimal("4500.25")  # 1 tick move
        
        gap_detected, gap_ticks = detect_gap(
            previous_close, current_open, ES_FUTURE.tick_size
        )
        
        assert not gap_detected
        assert gap_ticks == 1
    
    def test_gap_detected_up(self):
        """Test gap detection on gap up."""
        # ES gap up 10 ticks (2.50 points)
        previous_close = Decimal("4500.00")
        current_open = Decimal("4502.50")
        
        gap_detected, gap_ticks = detect_gap(
            previous_close, current_open, ES_FUTURE.tick_size
        )
        
        assert gap_detected
        assert gap_ticks == 10
    
    def test_gap_detected_down(self):
        """Test gap detection on gap down."""
        # AAPL gap down 50 cents (50 ticks)
        previous_close = Decimal("150.00")
        current_open = Decimal("149.50")
        
        gap_detected, gap_ticks = detect_gap(
            previous_close, current_open, AAPL_EQUITY.tick_size
        )
        
        assert gap_detected
        assert gap_ticks == 50


class TestMarketOrders:
    """Test market order fills."""
    
    def test_market_order_fills_at_open(self):
        """Test market order fills at current bar open with slippage."""
        current_bar = BarData(
            timestamp=datetime(2026, 1, 13, 9, 30, tzinfo=ZoneInfo("America/New_York")),
            open=Decimal("150.00"),
            high=Decimal("151.00"),
            low=Decimal("149.50"),
            close=Decimal("150.50"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.MARKET,
            side="buy",
            quantity=100,
            current_bar=current_bar,
            instrument=AAPL_EQUITY,
        )
        
        assert result.filled
        # Equity base slippage = 2 ticks, so buy at 150.00 + 0.02 = 150.02
        assert result.fill_price == Decimal("150.02")
        assert result.fill_timestamp == current_bar.timestamp
        assert result.fill_reason == FillReason.MARKET_OPEN
        assert result.slippage_ticks == 2
    
    def test_market_order_with_gap(self):
        """Test market order fills at open even with gap."""
        previous_bar = BarData(
            timestamp=datetime(2026, 1, 13, 15, 59, tzinfo=ZoneInfo("America/New_York")),
            open=Decimal("150.00"),
            high=Decimal("151.00"),
            low=Decimal("149.50"),
            close=Decimal("150.00"),
        )
        
        current_bar = BarData(
            timestamp=datetime(2026, 1, 14, 9, 30, tzinfo=ZoneInfo("America/New_York")),
            open=Decimal("152.00"),  # Gap up $2
            high=Decimal("152.50"),
            low=Decimal("151.50"),
            close=Decimal("152.00"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.MARKET,
            side="buy",
            quantity=100,
            current_bar=current_bar,
            previous_bar=previous_bar,
            instrument=AAPL_EQUITY,
        )
        
        assert result.filled
        # Gap up $2, slippage = 2 ticks, so fill at 152.02
        assert result.fill_price == Decimal("152.02")
        assert result.gap_detected
        assert result.gap_size_ticks == 200  # $2 / $0.01
        assert result.slippage_ticks == 2


class TestStopOrders:
    """Test stop order fills."""
    
    def test_buy_stop_triggered_no_gap(self):
        """Test buy stop triggered during bar (no gap)."""
        current_bar = BarData(
            timestamp=datetime(2026, 1, 13, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
            open=Decimal("4500.00"),
            high=Decimal("4505.00"),
            low=Decimal("4498.00"),
            close=Decimal("4503.00"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.STOP,
            side="buy",
            quantity=1,
            stop_price=Decimal("4502.00"),
            current_bar=current_bar,
            instrument=ES_FUTURE,
        )
        
        assert result.filled
        assert result.fill_price == Decimal("4502.00")  # Fills at stop
        assert result.fill_reason == FillReason.STOP_TRIGGERED
        assert result.slippage_ticks == 0
    
    def test_sell_stop_triggered_no_gap(self):
        """Test sell stop triggered during bar (no gap)."""
        current_bar = BarData(
            timestamp=datetime(2026, 1, 13, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
            open=Decimal("4500.00"),
            high=Decimal("4505.00"),
            low=Decimal("4498.00"),
            close=Decimal("4503.00"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.STOP,
            side="sell",
            quantity=1,
            stop_price=Decimal("4499.00"),
            current_bar=current_bar,
            instrument=ES_FUTURE,
        )
        
        assert result.filled
        assert result.fill_price == Decimal("4499.00")  # Fills at stop
        assert result.fill_reason == FillReason.STOP_TRIGGERED
    
    def test_buy_stop_gap_through(self):
        """Test buy stop gapped through - fills at open with slippage."""
        previous_bar = BarData(
            timestamp=datetime(2026, 1, 10, 16, 0, tzinfo=ZoneInfo("America/Chicago")),  # Friday close
            open=Decimal("4500.00"),
            high=Decimal("4502.00"),
            low=Decimal("4498.00"),
            close=Decimal("4500.00"),
        )
        
        current_bar = BarData(
            timestamp=datetime(2026, 1, 12, 17, 0, tzinfo=ZoneInfo("America/Chicago")),  # Sunday open
            open=Decimal("4510.00"),  # Gap up 10 points
            high=Decimal("4512.00"),
            low=Decimal("4508.00"),
            close=Decimal("4511.00"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.STOP,
            side="buy",
            quantity=1,
            stop_price=Decimal("4505.00"),  # Stop below gap open
            current_bar=current_bar,
            previous_bar=previous_bar,
            instrument=ES_FUTURE,
        )
        
        assert result.filled
        assert result.fill_price == Decimal("4510.00")  # Fills at open (worst case)
        assert result.fill_reason == FillReason.GAP_THROUGH_STOP
        assert result.gap_detected
        assert result.gap_size_ticks == 40  # 10 points / 0.25 tick
        assert result.slippage_ticks == 20  # (4510 - 4505) / 0.25 = 20 ticks
    
    def test_sell_stop_gap_through(self):
        """Test sell stop gapped through - fills at open with slippage."""
        previous_bar = BarData(
            timestamp=datetime(2026, 1, 13, 15, 59, tzinfo=ZoneInfo("America/New_York")),
            open=Decimal("150.00"),
            high=Decimal("151.00"),
            low=Decimal("149.50"),
            close=Decimal("150.00"),
        )
        
        current_bar = BarData(
            timestamp=datetime(2026, 1, 14, 9, 30, tzinfo=ZoneInfo("America/New_York")),
            open=Decimal("148.00"),  # Gap down $2
            high=Decimal("148.50"),
            low=Decimal("147.50"),
            close=Decimal("148.00"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.STOP,
            side="sell",
            quantity=100,
            stop_price=Decimal("149.00"),  # Stop above gap open
            current_bar=current_bar,
            previous_bar=previous_bar,
            instrument=AAPL_EQUITY,
        )
        
        assert result.filled
        assert result.fill_price == Decimal("148.00")  # Fills at open (worst case)
        assert result.fill_reason == FillReason.GAP_THROUGH_STOP
        assert result.slippage_ticks == 100  # (149 - 148) / 0.01 = 100 ticks
    
    def test_stop_not_triggered(self):
        """Test stop not triggered when price doesn't reach stop."""
        current_bar = BarData(
            timestamp=datetime(2026, 1, 13, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
            open=Decimal("4500.00"),
            high=Decimal("4505.00"),
            low=Decimal("4498.00"),
            close=Decimal("4503.00"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.STOP,
            side="buy",
            quantity=1,
            stop_price=Decimal("4506.00"),  # Above high
            current_bar=current_bar,
            instrument=ES_FUTURE,
        )
        
        assert not result.filled
        assert result.fill_price is None
        assert result.fill_reason == FillReason.PRICE_NOT_REACHED


class TestLimitOrders:
    """Test limit order fills."""
    
    def test_buy_limit_hit(self):
        """Test buy limit hit during bar."""
        current_bar = BarData(
            timestamp=datetime(2026, 1, 13, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
            open=Decimal("4500.00"),
            high=Decimal("4505.00"),
            low=Decimal("4498.00"),
            close=Decimal("4503.00"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.LIMIT,
            side="buy",
            quantity=1,
            limit_price=Decimal("4499.00"),
            current_bar=current_bar,
            instrument=ES_FUTURE,
        )
        
        assert result.filled
        assert result.fill_price == Decimal("4499.00")  # Fills at limit
        assert result.fill_reason == FillReason.LIMIT_HIT
    
    def test_sell_limit_hit(self):
        """Test sell limit hit during bar."""
        current_bar = BarData(
            timestamp=datetime(2026, 1, 13, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
            open=Decimal("4500.00"),
            high=Decimal("4505.00"),
            low=Decimal("4498.00"),
            close=Decimal("4503.00"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.LIMIT,
            side="sell",
            quantity=1,
            limit_price=Decimal("4504.00"),
            current_bar=current_bar,
            instrument=ES_FUTURE,
        )
        
        assert result.filled
        assert result.fill_price == Decimal("4504.00")  # Fills at limit
        assert result.fill_reason == FillReason.LIMIT_HIT
    
    def test_buy_limit_gap_through(self):
        """Test buy limit gapped through favorably - fills at limit."""
        previous_bar = BarData(
            timestamp=datetime(2026, 1, 13, 15, 59, tzinfo=ZoneInfo("America/New_York")),
            open=Decimal("150.00"),
            high=Decimal("151.00"),
            low=Decimal("149.50"),
            close=Decimal("150.00"),
        )
        
        current_bar = BarData(
            timestamp=datetime(2026, 1, 14, 9, 30, tzinfo=ZoneInfo("America/New_York")),
            open=Decimal("148.00"),  # Gap down through limit
            high=Decimal("148.50"),
            low=Decimal("147.50"),
            close=Decimal("148.00"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.LIMIT,
            side="buy",
            quantity=100,
            limit_price=Decimal("149.00"),  # Limit above gap open
            current_bar=current_bar,
            previous_bar=previous_bar,
            instrument=AAPL_EQUITY,
        )
        
        assert result.filled
        assert result.fill_price == Decimal("149.00")  # Fills at limit (best case)
        assert result.fill_reason == FillReason.GAP_THROUGH_LIMIT
        assert result.gap_detected
    
    def test_limit_not_reached(self):
        """Test limit not reached."""
        current_bar = BarData(
            timestamp=datetime(2026, 1, 13, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
            open=Decimal("4500.00"),
            high=Decimal("4505.00"),
            low=Decimal("4498.00"),
            close=Decimal("4503.00"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.LIMIT,
            side="buy",
            quantity=1,
            limit_price=Decimal("4497.00"),  # Below low
            current_bar=current_bar,
            instrument=ES_FUTURE,
        )
        
        assert not result.filled
        assert result.fill_price is None
        assert result.fill_reason == FillReason.PRICE_NOT_REACHED


class TestSessionAwareness:
    """Test session-aware fill logic."""
    
    def test_market_closed_blocks_fill(self):
        """Test fill blocked when market is closed."""
        session_engine = create_equity_session_engine(AAPL_EQUITY)
        
        # Saturday morning - market closed
        current_bar = BarData(
            timestamp=datetime(2026, 1, 10, 10, 0, tzinfo=ZoneInfo("America/New_York")),
            open=Decimal("150.00"),
            high=Decimal("151.00"),
            low=Decimal("149.50"),
            close=Decimal("150.50"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.MARKET,
            side="buy",
            quantity=100,
            current_bar=current_bar,
            instrument=AAPL_EQUITY,
            session_engine=session_engine,
        )
        
        assert not result.filled
        assert result.fill_reason == FillReason.SESSION_CLOSED
    
    def test_cme_break_blocks_fill(self):
        """Test fill blocked during CME 4-5 PM break."""
        session_engine = create_cme_session_engine(ES_FUTURE)
        
        # Tuesday 4:30 PM CT - during break
        current_bar = BarData(
            timestamp=datetime(2026, 1, 13, 16, 30, tzinfo=ZoneInfo("America/Chicago")),
            open=Decimal("4500.00"),
            high=Decimal("4505.00"),
            low=Decimal("4498.00"),
            close=Decimal("4503.00"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.MARKET,
            side="buy",
            quantity=1,
            current_bar=current_bar,
            instrument=ES_FUTURE,
            session_engine=session_engine,
        )
        
        assert not result.filled
        assert result.fill_reason == FillReason.SESSION_CLOSED
    
    def test_fill_allowed_during_normal_hours(self):
        """Test fill allowed during normal market hours."""
        session_engine = create_equity_session_engine(AAPL_EQUITY)
        
        # Tuesday 2 PM ET - normal hours
        current_bar = BarData(
            timestamp=datetime(2026, 1, 13, 14, 0, tzinfo=ZoneInfo("America/New_York")),
            open=Decimal("150.00"),
            high=Decimal("151.00"),
            low=Decimal("149.50"),
            close=Decimal("150.50"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.MARKET,
            side="buy",
            quantity=100,
            current_bar=current_bar,
            instrument=AAPL_EQUITY,
            session_engine=session_engine,
        )
        
        assert result.filled
        assert result.fill_price == Decimal("150.02")


class TestTickRounding:
    """Test all fills are tick-rounded."""
    
    def test_stop_fill_tick_rounded(self):
        """Test stop fill price is tick-rounded."""
        current_bar = BarData(
            timestamp=datetime(2026, 1, 13, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
            open=Decimal("4500.00"),
            high=Decimal("4505.00"),
            low=Decimal("4498.00"),
            close=Decimal("4503.00"),
        )
        
        # Stop price not on tick boundary
        result = simulate_gap_fill(
            order_type=OrderType.STOP,
            side="buy",
            quantity=1,
            stop_price=Decimal("4502.13"),  # Not on 0.25 tick
            current_bar=current_bar,
            instrument=ES_FUTURE,
        )
        
        assert result.filled
        # Rounded to nearest tick (4502.00 or 4502.25)
        assert result.fill_price % ES_FUTURE.tick_size == 0
    
    def test_gap_fill_tick_rounded(self):
        """Test gap fill price is tick-rounded."""
        previous_bar = BarData(
            timestamp=datetime(2026, 1, 13, 15, 59, tzinfo=ZoneInfo("America/New_York")),
            open=Decimal("150.00"),
            high=Decimal("151.00"),
            low=Decimal("149.50"),
            close=Decimal("150.00"),
        )
        
        current_bar = BarData(
            timestamp=datetime(2026, 1, 14, 9, 30, tzinfo=ZoneInfo("America/New_York")),
            open=Decimal("152.00"),
            high=Decimal("152.50"),
            low=Decimal("151.50"),
            close=Decimal("152.00"),
        )
        
        result = simulate_gap_fill(
            order_type=OrderType.MARKET,
            side="buy",
            quantity=100,
            current_bar=current_bar,
            previous_bar=previous_bar,
            instrument=AAPL_EQUITY,
        )
        
        assert result.filled
        assert result.fill_price % AAPL_EQUITY.tick_size == 0
