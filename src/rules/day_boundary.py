"""Trading day boundary logic for Topstep-style rules.

This module handles day rollover semantics:
- Daily loss resets at session rollover
- Trailing drawdown persists across days (never resets)
- Locking logic persists across days (once locked, stays locked)

Key invariant:
- Daily loss resets on day boundary
- Trailing drawdown and high-water mark never reset (unless portfolio resets)
"""

from typing import Optional
from datetime import datetime, date, time, timezone
from dataclasses import dataclass


@dataclass(frozen=True)
class TradingDayBoundary:
    """Trading day boundary configuration.
    
    Attributes:
        timezone: Timezone for trading day boundaries (default: UTC)
        session_start_time: Start time of trading session (default: 00:00 UTC)
    """
    
    timezone: timezone = timezone.utc
    session_start_time: time = time(0, 0, 0)  # Midnight
    
    def get_trading_date(self, timestamp: datetime) -> date:
        """Get trading date for a timestamp.
        
        Args:
            timestamp: Datetime (will be converted to self.timezone)
            
        Returns:
            Trading date for this timestamp
        """
        # Convert to configured timezone
        if timestamp.tzinfo is None:
            # Naive timestamp - assume it's in self.timezone
            timestamp = timestamp.replace(tzinfo=self.timezone)
        else:
            # Aware timestamp - convert to self.timezone
            timestamp = timestamp.astimezone(self.timezone)
        
        # Return date (trading day is determined by date in configured timezone)
        return timestamp.date()
    
    def is_same_trading_day(self, timestamp1: datetime, timestamp2: datetime) -> bool:
        """Check if two timestamps are on the same trading day.
        
        Args:
            timestamp1: First timestamp
            timestamp2: Second timestamp
            
        Returns:
            True if same trading day, False otherwise
        """
        return self.get_trading_date(timestamp1) == self.get_trading_date(timestamp2)
    
    def has_day_rollover(
        self,
        previous_timestamp: Optional[datetime],
        current_timestamp: datetime
    ) -> bool:
        """Check if a day rollover occurred between two timestamps.
        
        Args:
            previous_timestamp: Previous timestamp (None if first update)
            current_timestamp: Current timestamp
            
        Returns:
            True if rollover occurred, False otherwise
        """
        if previous_timestamp is None:
            return False
        
        return not self.is_same_trading_day(previous_timestamp, current_timestamp)


def reset_daily_loss_for_new_day(
    tracker: 'DrawdownTracker',
    new_trading_date: date,
    new_initial_balance: Optional[float] = None
) -> 'DrawdownTracker':
    """Reset daily loss tracking for a new trading day.
    
    This function creates a new tracker with:
    - New trading date
    - New initial balance (for daily loss calculation)
    - Preserved high-water mark (trailing drawdown persists)
    - Preserved lock state (once locked, stays locked)
    - Preserved snapshot history (for audit trail)
    
    Args:
        tracker: Current drawdown tracker
        new_trading_date: New trading date
        new_initial_balance: New initial balance for the day (default: current equity)
        
    Returns:
        New DrawdownTracker with daily loss reset but trailing drawdown preserved
        
    Note:
        This does NOT reset trailing drawdown or high-water mark.
        Those persist across days.
    """
    from .drawdown import DrawdownTracker
    
    # Get current equity from latest snapshot if available
    if tracker.snapshots:
        latest_snapshot = tracker.snapshots[-1]
        current_equity = latest_snapshot.equity
    else:
        current_equity = tracker.initial_balance
    
    # Use provided initial balance or current equity as new day's starting balance
    if new_initial_balance is None:
        new_initial_balance = current_equity
    
    # Create new tracker preserving:
    # - High-water mark (trailing drawdown persists)
    # - Lock state (once locked, stays locked)
    # - Snapshot history (for audit trail)
    new_tracker = DrawdownTracker(
        initial_balance=new_initial_balance,  # New day's starting balance
        trading_date=new_trading_date,  # New trading date
        high_water_mark=tracker.high_water_mark,  # Preserve high-water mark
        is_locked=tracker.is_locked,  # Preserve lock state
        snapshots=list(tracker.snapshots)  # Preserve snapshot history (create new list)
    )
    
    return new_tracker

