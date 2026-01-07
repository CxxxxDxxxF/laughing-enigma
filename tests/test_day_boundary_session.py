"""Tests for session-aware trading day boundaries.

Critical for funded firm compliance:
- Daily loss resets at session start, not midnight
- Trading day = date of session that began most recently before timestamp
"""

import sys
from pathlib import Path
from datetime import datetime, date, time, timezone
from unittest import TestCase
import zoneinfo

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rules.day_boundary import TradingDayBoundary


class TestSessionBoundary(TestCase):
    """Test session-based trading day boundaries."""
    
    def test_session_start_5pm_ct(self):
        """Test that session start at 5 PM CT correctly determines trading date.
        
        Scenario: Session starts at 5 PM CT (17:00)
        - 2024-01-01 16:00 CT → trading date is 2023-12-31 (previous day's session)
        - 2024-01-01 17:00 CT → trading date is 2024-01-01 (new session started)
        - 2024-01-02 16:00 CT → trading date is 2024-01-01 (still in same session)
        """
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(
            timezone=ct_tz,
            session_start_time=time(17, 0, 0)  # 5 PM
        )
        
        # Just before session start (4 PM) → previous day's session
        ts_before = datetime(2024, 1, 1, 16, 0, 0, tzinfo=ct_tz)
        trading_date = boundary.get_trading_date(ts_before)
        self.assertEqual(trading_date, date(2023, 12, 31), 
                        "16:00 CT should belong to previous day's session")
        
        # Exactly at session start (5 PM) → current day's session
        ts_at_start = datetime(2024, 1, 1, 17, 0, 0, tzinfo=ct_tz)
        trading_date = boundary.get_trading_date(ts_at_start)
        self.assertEqual(trading_date, date(2024, 1, 1),
                        "17:00 CT should belong to current day's session")
        
        # After session start (6 PM) → current day's session
        ts_after = datetime(2024, 1, 1, 18, 0, 0, tzinfo=ct_tz)
        trading_date = boundary.get_trading_date(ts_after)
        self.assertEqual(trading_date, date(2024, 1, 1),
                        "18:00 CT should belong to current day's session")
        
        # Next day before session start (4 PM next day) → still previous day's session
        ts_next_before = datetime(2024, 1, 2, 16, 0, 0, tzinfo=ct_tz)
        trading_date = boundary.get_trading_date(ts_next_before)
        self.assertEqual(trading_date, date(2024, 1, 1),
                        "2024-01-02 16:00 CT should still be in 2024-01-01's session")
        
        # Next day at session start (5 PM next day) → new day's session
        ts_next_start = datetime(2024, 1, 2, 17, 0, 0, tzinfo=ct_tz)
        trading_date = boundary.get_trading_date(ts_next_start)
        self.assertEqual(trading_date, date(2024, 1, 2),
                        "2024-01-02 17:00 CT should start new session")
    
    def test_midnight_session_start(self):
        """Test that midnight session start behaves like calendar date."""
        utc_tz = timezone.utc
        boundary = TradingDayBoundary(
            timezone=utc_tz,
            session_start_time=time(0, 0, 0)  # Midnight
        )
        
        # Just before midnight
        ts_before = datetime(2024, 1, 1, 23, 59, 59, tzinfo=utc_tz)
        trading_date = boundary.get_trading_date(ts_before)
        # 23:59:59 >= 00:00:00 (Session Start), so it belongs to Jan 1 session
        self.assertEqual(trading_date, date(2024, 1, 1))
        
        # Exactly at midnight
        ts_at_start = datetime(2024, 1, 2, 0, 0, 0, tzinfo=utc_tz)
        trading_date = boundary.get_trading_date(ts_at_start)
        self.assertEqual(trading_date, date(2024, 1, 2))
    
    def test_midnight_session_end_boundary(self):
         """Test boundary conditions near midnight session end."""
         utc_tz = timezone.utc
         boundary = TradingDayBoundary(
             timezone=utc_tz,
             session_start_time=time(0, 0, 0)
         )
         # 1 second before midnight (end of Jan 1 session)
         ts_before = datetime(2024, 1, 1, 23, 59, 59, tzinfo=utc_tz)
         trading_date = boundary.get_trading_date(ts_before)
         # Should be Jan 1 because session is Jan 1 00:00 to Jan 1 23:59
         self.assertEqual(trading_date, date(2024, 1, 1))
    
    def test_has_day_rollover_session_boundary(self):
        """Test that has_day_rollover correctly detects session boundaries."""
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(
            timezone=ct_tz,
            session_start_time=time(17, 0, 0)
        )
        
        # Same session (both before session start)
        ts1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz)
        ts2 = datetime(2024, 1, 1, 16, 0, 0, tzinfo=ct_tz)
        self.assertFalse(boundary.has_day_rollover(ts1, ts2),
                         "Should not rollover within same session")
        
        # Rollover at session start (before → at session start)
        ts3 = datetime(2024, 1, 1, 16, 59, 59, tzinfo=ct_tz)
        ts4 = datetime(2024, 1, 1, 17, 0, 0, tzinfo=ct_tz)
        self.assertTrue(boundary.has_day_rollover(ts3, ts4),
                        "Should rollover at session start")
        
        # No rollover after session start (both after session start, same calendar day)
        ts5 = datetime(2024, 1, 1, 18, 0, 0, tzinfo=ct_tz)
        ts6 = datetime(2024, 1, 1, 22, 0, 0, tzinfo=ct_tz)
        self.assertFalse(boundary.has_day_rollover(ts5, ts6),
                         "Should not rollover within same session after start")
        
        # Rollover at next day's session start
        ts7 = datetime(2024, 1, 1, 22, 0, 0, tzinfo=ct_tz)
        ts8 = datetime(2024, 1, 2, 17, 0, 0, tzinfo=ct_tz)
        self.assertTrue(boundary.has_day_rollover(ts7, ts8),
                        "Should rollover at next day's session start")
        
        # No rollover across midnight if both before session start
        # To test this meaningfully, we need two timestamps that cross midnight 
        # but are still in the same session (i.e. between Session Start and Next Session Start)
        # Session starts at 17:00 (5 PM).
        # Session 1: Jan 1 17:00 to Jan 2 17:00.
        # Midnight is Jan 2 00:00.
        # Pick Jan 1 20:00 (8 PM) and Jan 2 04:00 (4 AM). Both are in Session 1.
        ts9 = datetime(2024, 1, 1, 20, 0, 0, tzinfo=ct_tz)
        ts10 = datetime(2024, 1, 2, 4, 0, 0, tzinfo=ct_tz)
        self.assertFalse(boundary.has_day_rollover(ts9, ts10),
                         "Should NOT rollover at midnight if session starts at 5 PM")
    
    def test_from_config_parsing(self):
        """Test that from_config correctly parses timezone and session_start_time."""
        config = {
            "timezone": "America/Chicago",
            "session_start_time": "17:00:00"
        }
        boundary = TradingDayBoundary.from_config(config)
        
        self.assertEqual(boundary.timezone, zoneinfo.ZoneInfo("America/Chicago"))
        self.assertEqual(boundary.session_start_time, time(17, 0, 0))
        
        # Test UTC
        config_utc = {
            "timezone": "UTC",
            "session_start_time": "00:00:00"
        }
        boundary_utc = TradingDayBoundary.from_config(config_utc)
        self.assertEqual(boundary_utc.timezone, timezone.utc)
        self.assertEqual(boundary_utc.session_start_time, time(0, 0, 0))
        
        # Test None config (defaults)
        boundary_default = TradingDayBoundary.from_config(None)
        self.assertEqual(boundary_default.timezone, timezone.utc)
        self.assertEqual(boundary_default.session_start_time, time(0, 0, 0))
    
    def test_same_trading_day_across_midnight(self):
        """Test that same trading day detection works across midnight.
        
        Critical: If session starts at 5 PM, then 1/1 16:00 and 1/2 16:00 
        are in the SAME trading day (both before next session start).
        """
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(
            timezone=ct_tz,
            session_start_time=time(17, 0, 0)
        )
        
        # Same session across midnight
        ts1 = datetime(2024, 1, 1, 22, 0, 0, tzinfo=ct_tz)  # 10 PM Jan 1
        ts2 = datetime(2024, 1, 2, 10, 0, 0, tzinfo=ct_tz)  # 10 AM Jan 2
        self.assertTrue(boundary.is_same_trading_day(ts1, ts2),
                       "Should be same trading day (both before 5 PM on Jan 2)")
        
        # Different sessions (cross session boundary)
        ts3 = datetime(2024, 1, 1, 22, 0, 0, tzinfo=ct_tz)  # 10 PM Jan 1
        ts4 = datetime(2024, 1, 2, 17, 0, 0, tzinfo=ct_tz)  # 5 PM Jan 2 (session start)
        self.assertFalse(boundary.is_same_trading_day(ts3, ts4),
                        "Should be different trading days (crossed session boundary)")

