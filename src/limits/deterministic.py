"""Deterministic limits provider for LIVE_DRY mode.

Provides fixed, predictable limits for testing and validation.
All limits are deterministic and do not change between calls.
"""

from datetime import datetime, date, time
from typing import Optional
import zoneinfo

from .provider import LimitsProvider, TradingSession, LimitsProviderError
from ..rules.day_boundary import TradingDayBoundary


class DeterministicLimitsProvider(LimitsProvider):
    """Deterministic limits provider for LIVE_DRY mode.
    
    Provides fixed limits that are predictable and deterministic.
    Used for testing, validation, and rehearsal runs.
    
    Attributes:
        daily_loss_limit: Fixed daily loss limit (negative value)
        day_boundary: Trading day boundary configuration
        timezone: Timezone for session calculations
    """
    
    def __init__(
        self,
        daily_loss_limit: float,
        day_boundary: Optional[TradingDayBoundary] = None,
        timezone_str: str = "America/Chicago"
    ):
        """Initialize deterministic limits provider.
        
        Args:
            daily_loss_limit: Fixed daily loss limit (negative value, e.g., -1000.0)
            day_boundary: Optional trading day boundary (defaults to 5 PM CT)
            timezone_str: Timezone string (default: "America/Chicago")
        """
        if daily_loss_limit >= 0:
            raise ValueError(f"daily_loss_limit must be negative, got {daily_loss_limit}")
        
        self.daily_loss_limit = daily_loss_limit
        self.timezone = zoneinfo.ZoneInfo(timezone_str)
        
        if day_boundary is None:
            # Default: Topstep-style 5 PM CT session start
            self.day_boundary = TradingDayBoundary(
                timezone=self.timezone,
                session_start_time=time(17, 0, 0)  # 5:00 PM
            )
        else:
            self.day_boundary = day_boundary
    
    def get_daily_loss_limit(self, timestamp: datetime) -> float:
        """Get fixed daily loss limit.
        
        Args:
            timestamp: Current timestamp (ignored for deterministic provider)
            
        Returns:
            Fixed daily loss limit
        """
        return self.daily_loss_limit
    
    def get_trading_session(self, timestamp: datetime) -> TradingSession:
        """Get trading session for the given timestamp.
        
        Uses day_boundary to determine trading date and session times.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            TradingSession with date and session boundaries
        """
        # Use day_boundary to get trading date
        trading_date = self.day_boundary.get_trading_date(timestamp)
        
        # Calculate session start (5 PM CT on trading_date)
        session_start = datetime.combine(
            trading_date,
            self.day_boundary.session_start_time,
            tzinfo=self.day_boundary.timezone
        )
        
        # Session ends at 3:10 PM CT the next day (Topstep rule)
        # TODO: Make this configurable per firm
        session_end_date = trading_date
        session_end = datetime.combine(
            session_end_date,
            time(15, 10, 0),  # 3:10 PM CT
            tzinfo=self.day_boundary.timezone
        )
        # If timestamp is before session end, session hasn't ended yet
        if timestamp < session_end:
            session_end = None
        
        return TradingSession(
            date=trading_date,
            start_time=session_start,
            end_time=session_end,
            is_holiday=False  # TODO: Add holiday calendar
        )

