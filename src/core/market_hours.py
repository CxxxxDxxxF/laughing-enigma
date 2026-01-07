"""Market hours and trading session logic.

This module provides trading session definitions and utilities to determine
if the market is currently open, supporting:
- CME Futures (5 PM - 4 PM CT, with breaks)
- US Equities (9:30 AM - 4 PM ET)
- Custom sessions
"""

from dataclasses import dataclass
from datetime import time, datetime, timedelta
from typing import Optional
import zoneinfo


@dataclass(frozen=True)
class TradingSession:
    """Definition of a trading session.
    
    Attributes:
        name: Human-readable name for the session
        start_time: Session start time (in session timezone)
        end_time: Session end time (in session timezone)
        timezone: Timezone string (e.g., "America/Chicago")
        crosses_midnight: True if session spans two calendar days
        weekdays: Tuple of weekdays when market is open (0=Mon, 6=Sun)
    """
    name: str
    start_time: time
    end_time: time
    timezone: str
    crosses_midnight: bool = False
    weekdays: tuple = (0, 1, 2, 3, 4)  # Mon-Fri by default


# === PRESETS ===

# CME Futures: Sunday 5 PM CT to Friday 4 PM CT
# Daily break: 4 PM - 5 PM CT
CME_FUTURES = TradingSession(
    name="CME Futures",
    start_time=time(17, 0),   # 5 PM
    end_time=time(16, 0),     # 4 PM (next day)
    timezone="America/Chicago",
    crosses_midnight=True,
    weekdays=(0, 1, 2, 3, 4, 6)  # Mon-Fri + Sunday evening
)

# US Equities: 9:30 AM - 4 PM ET, Monday-Friday
US_EQUITIES = TradingSession(
    name="US Equities",
    start_time=time(9, 30),
    end_time=time(16, 0),
    timezone="America/New_York",
    crosses_midnight=False,
    weekdays=(0, 1, 2, 3, 4)  # Mon-Fri
)

# Always open (for testing / 24/7 crypto)
ALWAYS_OPEN = TradingSession(
    name="Always Open",
    start_time=time(0, 0),
    end_time=time(23, 59, 59),
    timezone="UTC",
    crosses_midnight=False,
    weekdays=(0, 1, 2, 3, 4, 5, 6)  # Every day
)


def get_session(name: str) -> TradingSession:
    """Get a trading session by name.
    
    Args:
        name: Session name ("cme_futures", "us_equities", "always")
        
    Returns:
        TradingSession instance
        
    Raises:
        ValueError: If session name is not recognized
    """
    sessions = {
        "cme_futures": CME_FUTURES,
        "us_equities": US_EQUITIES,
        "always": ALWAYS_OPEN,
    }
    if name.lower() not in sessions:
        raise ValueError(f"Unknown session: {name}. Available: {list(sessions.keys())}")
    return sessions[name.lower()]


def is_market_open(timestamp: datetime, session: TradingSession) -> bool:
    """Check if the market is currently open.
    
    Args:
        timestamp: Current timestamp (timezone-aware or naive)
        session: Trading session definition
        
    Returns:
        True if market is open, False otherwise
    """
    # Convert to session timezone
    tz = zoneinfo.ZoneInfo(session.timezone)
    if timestamp.tzinfo is None:
        local_dt = timestamp.replace(tzinfo=tz)
    else:
        local_dt = timestamp.astimezone(tz)
    
    # Check weekday
    weekday = local_dt.weekday()
    if weekday not in session.weekdays:
        return False
    
    current_time = local_dt.time()
    
    if session.crosses_midnight:
        # Session spans midnight: open if time >= start OR time < end
        # Example: 5 PM - 4 PM → open from 17:00 to 23:59 OR 00:00 to 16:00
        return current_time >= session.start_time or current_time < session.end_time
    else:
        # Normal session: open if start <= time < end
        return session.start_time <= current_time < session.end_time


def time_until_open(timestamp: datetime, session: TradingSession) -> Optional[timedelta]:
    """Calculate time until market opens.
    
    Args:
        timestamp: Current timestamp
        session: Trading session definition
        
    Returns:
        Timedelta until market opens, or None if already open
    """
    if is_market_open(timestamp, session):
        return None
    
    tz = zoneinfo.ZoneInfo(session.timezone)
    if timestamp.tzinfo is None:
        local_dt = timestamp.replace(tzinfo=tz)
    else:
        local_dt = timestamp.astimezone(tz)
    
    # Find next open time
    # Start from today and look forward up to 7 days
    for days_ahead in range(8):
        candidate_date = (local_dt + timedelta(days=days_ahead)).date()
        candidate_weekday = candidate_date.weekday()
        
        if candidate_weekday not in session.weekdays:
            continue
        
        # Build candidate open datetime
        candidate_open = datetime.combine(candidate_date, session.start_time, tzinfo=tz)
        
        if candidate_open > local_dt:
            return candidate_open - local_dt
    
    # Fallback: shouldn't happen with valid session
    return timedelta(hours=1)


def time_until_close(timestamp: datetime, session: TradingSession) -> Optional[timedelta]:
    """Calculate time until market closes.
    
    Args:
        timestamp: Current timestamp
        session: Trading session definition
        
    Returns:
        Timedelta until market closes, or None if already closed
    """
    if not is_market_open(timestamp, session):
        return None
    
    tz = zoneinfo.ZoneInfo(session.timezone)
    if timestamp.tzinfo is None:
        local_dt = timestamp.replace(tzinfo=tz)
    else:
        local_dt = timestamp.astimezone(tz)
    
    current_time = local_dt.time()
    
    if session.crosses_midnight:
        # If before midnight, close is tomorrow; if after midnight, close is today
        if current_time >= session.start_time:
            # We're in the evening portion, close is tomorrow
            close_date = local_dt.date() + timedelta(days=1)
        else:
            # We're in the morning portion, close is today
            close_date = local_dt.date()
    else:
        close_date = local_dt.date()
    
    close_dt = datetime.combine(close_date, session.end_time, tzinfo=tz)
    return close_dt - local_dt
