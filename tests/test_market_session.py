#!/usr/bin/env python3
"""Tests for MarketSessionEngine."""

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from src.core.market_session import (
    MarketSessionEngine,
    SessionDecision,
    create_cme_session_engine,
    create_equity_session_engine,
)
from src.core.market_hours import CME_FUTURES, US_EQUITIES
from src.core.instrument_spec import ES_FUTURE, AAPL_EQUITY


class TestCMESessionEngine:
    """Test CME futures session engine."""
    
    def test_trading_allowed_during_session(self):
        """Test trading is allowed during normal CME hours."""
        engine = MarketSessionEngine(CME_FUTURES, ES_FUTURE)
        
        # Tuesday, 10 AM CT (normal trading hours)
        timestamp = datetime(2026, 1, 13, 10, 0, 0, tzinfo=ZoneInfo("America/Chicago"))
        
        result = engine.is_trading_allowed(timestamp)
        assert result.allowed
        assert result.decision == SessionDecision.ALLOWED
        assert result.reason == "Trading allowed"
    
    def test_cme_break_is_market_closed(self):
        """Test CME 4-5 PM CT break registers as market closed."""
        engine = MarketSessionEngine(CME_FUTURES, ES_FUTURE)
        
        # Tuesday, 4:30 PM CT (during break - market technically closed)
        timestamp = datetime(2026, 1, 13, 16, 30, 0, tzinfo=ZoneInfo("America/Chicago"))
        
        result = engine.is_trading_allowed(timestamp)
        assert not result.allowed
        assert result.decision == SessionDecision.MARKET_CLOSED
    
    def test_market_closed_saturday(self):
        """Test market is closed on Saturday."""
        engine = MarketSessionEngine(CME_FUTURES, ES_FUTURE)
        
        # Saturday, 10 AM CT (weekend closed)
        timestamp = datetime(2026, 1, 10, 10, 0, 0, tzinfo=ZoneInfo("America/Chicago"))
        
        result = engine.is_trading_allowed(timestamp)
        assert not result.allowed
        assert result.decision == SessionDecision.MARKET_CLOSED
        assert result.time_until_allowed is not None
    
    def test_forced_flat_friday_afternoon(self):
        """Test forced flat window before Friday close."""
        engine = MarketSessionEngine(CME_FUTURES, ES_FUTURE)
        
        # Friday, 3:45 PM CT (15 minutes before close)
        timestamp = datetime(2026, 1, 16, 15, 45, 0, tzinfo=ZoneInfo("America/Chicago"))
        
        result = engine.is_trading_allowed(timestamp)
        assert not result.allowed
        assert result.decision == SessionDecision.FORCED_FLAT
        assert "Forced-flat" in result.reason
    
    def test_daily_loss_stop_blocks_all_trading(self):
        """Test daily loss stop blocks all trading."""
        # Mock loss stop that always returns True
        def loss_stop(ts):
            return True
        
        engine = MarketSessionEngine(CME_FUTURES, ES_FUTURE, daily_loss_stop=loss_stop)
        
        # Tuesday, 10 AM CT (normal trading hours)
        timestamp = datetime(2026, 1, 13, 10, 0, 0, tzinfo=ZoneInfo("America/Chicago"))
        
        result = engine.is_trading_allowed(timestamp)
        assert not result.allowed
        assert result.decision == SessionDecision.LOSS_LIMIT_HIT
        assert "Daily loss limit" in result.reason


class TestEquitySessionEngine:
    """Test US equity session engine."""
    
    def test_trading_allowed_during_market_hours(self):
        """Test trading is allowed during market hours."""
        engine = MarketSessionEngine(US_EQUITIES, AAPL_EQUITY)
        
        # Tuesday, 2 PM ET (normal trading hours)
        timestamp = datetime(2026, 1, 13, 14, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        
        result = engine.is_trading_allowed(timestamp)
        assert result.allowed
        assert result.decision == SessionDecision.ALLOWED
    
    def test_market_closed_before_open(self):
        """Test market is closed before 9:30 AM ET."""
        engine = MarketSessionEngine(US_EQUITIES, AAPL_EQUITY)
        
        # Tuesday, 9:00 AM ET (before open)
        timestamp = datetime(2026, 1, 13, 9, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        
        result = engine.is_trading_allowed(timestamp)
        assert not result.allowed
        assert result.decision == SessionDecision.MARKET_CLOSED
    
    def test_market_closed_after_close(self):
        """Test market is closed after 4 PM ET."""
        engine = MarketSessionEngine(US_EQUITIES, AAPL_EQUITY)
        
        # Tuesday, 4:30 PM ET (after close)
        timestamp = datetime(2026, 1, 13, 16, 30, 0, tzinfo=ZoneInfo("America/New_York"))
        
        result = engine.is_trading_allowed(timestamp)
        assert not result.allowed
        assert result.decision == SessionDecision.MARKET_CLOSED
    
    def test_forced_flat_near_close(self):
        """Test forced flat in last 15 minutes."""
        engine = MarketSessionEngine(US_EQUITIES, AAPL_EQUITY)
        
        # Tuesday, 3:50 PM ET (10 minutes before close)
        timestamp = datetime(2026, 1, 13, 15, 50, 0, tzinfo=ZoneInfo("America/New_York"))
        
        result = engine.is_trading_allowed(timestamp)
        assert not result.allowed
        assert result.decision == SessionDecision.FORCED_FLAT


class TestFactories:
    """Test factory methods."""
    
    def test_create_cme_session_engine(self):
        """Test CME factory creates valid engine."""
        engine = create_cme_session_engine(ES_FUTURE)
        
        assert engine.session.name == "CME Futures"
        assert engine.instrument == ES_FUTURE
    
    def test_create_cme_with_wrong_asset_raises(self):
        """Test CME factory rejects non-futures."""
        with pytest.raises(ValueError, match="Expected futures"):
            create_cme_session_engine(AAPL_EQUITY)
    
    def test_create_equity_session_engine(self):
        """Test equity factory creates valid engine."""
        engine = create_equity_session_engine(AAPL_EQUITY)
        
        assert engine.session.name == "US Equities"
        assert engine.instrument == AAPL_EQUITY
    
    def test_create_equity_with_wrong_asset_raises(self):
        """Test equity factory rejects non-equities."""
        with pytest.raises(ValueError, match="Expected equity"):
            create_equity_session_engine(ES_FUTURE)


class TestTimeUntilNextSession:
    """Test time_until_next_session method."""
    
    def test_returns_none_when_allowed(self):
        """Test returns None when trading is currently allowed."""
        engine = MarketSessionEngine(US_EQUITIES, AAPL_EQUITY)
        
        # Tuesday, 2 PM ET (market open)
        timestamp = datetime(2026, 1, 13, 14, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        
        result = engine.time_until_next_session(timestamp)
        assert result is None
    
    def test_returns_timedelta_when_closed(self):
        """Test returns timedelta when market is closed."""
        engine = MarketSessionEngine(US_EQUITIES, AAPL_EQUITY)
        
        # Tuesday, 9:00 AM ET (before open)
        timestamp = datetime(2026, 1, 13, 9, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        
        result = engine.time_until_next_session(timestamp)
        assert result is not None
        assert isinstance(result, timedelta)
        # Should be 30 minutes until 9:30 AM open
        assert result.total_seconds() == 30 * 60


class TestSessionBoundaries:
    """Test session boundary edge cases."""
    
    def test_cme_active_midday(self):
        """Test CME trading active during midday."""
        engine = MarketSessionEngine(CME_FUTURES, ES_FUTURE)
        
        # Tuesday, 2 PM CT (well within session)
        timestamp = datetime(2026, 1, 13, 14, 0, 0, tzinfo=ZoneInfo("America/Chicago"))
        
        result = engine.is_trading_allowed(timestamp)
        assert result.allowed
        assert result.decision == SessionDecision.ALLOWED
    
    def test_cme_after_break_reopens(self):
        """Test CME reopens after 5 PM break."""
        engine = MarketSessionEngine(CME_FUTURES, ES_FUTURE)
        
        # Tuesday, 5:00 PM CT (break just ended)
        timestamp = datetime(2026, 1, 13, 17, 0, 0, tzinfo=ZoneInfo("America/Chicago"))
        
        result = engine.is_trading_allowed(timestamp)
        # Should be allowed - break ended
        assert result.allowed
        assert result.decision == SessionDecision.ALLOWED
    
    def test_equity_boundary_at_open(self):
        """Test equity market at exact open time."""
        engine = MarketSessionEngine(US_EQUITIES, AAPL_EQUITY)
        
        # Tuesday, 9:30 AM ET (exact open)
        timestamp = datetime(2026, 1, 13, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))
        
        result = engine.is_trading_allowed(timestamp)
        assert result.allowed
        assert result.decision == SessionDecision.ALLOWED
