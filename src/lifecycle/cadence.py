"""Cadence gating for portfolio cycles.

This module provides cadence controls to prevent cycles from running too frequently.
"""

from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class CadenceFrequency(str, Enum):
    """Cycle frequency options."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MANUAL = "manual"  # No automatic gating


@dataclass
class CycleCadenceConfig:
    """Configuration for cycle cadence gating.
    
    Attributes:
        frequency: Frequency of cycles ("daily", "weekly", or "manual")
        min_seconds_between_cycles: Minimum seconds between cycles (overrides frequency if set)
        timezone: Timezone string (for future use, kept simple for now)
        
    Note:
        - If frequency is "manual", no cadence check is performed
        - min_seconds_between_cycles takes precedence over frequency if both are set
    """
    
    frequency: str = "manual"
    min_seconds_between_cycles: Optional[int] = None
    timezone: str = "UTC"
    
    def __post_init__(self):
        """Validate cadence config."""
        if self.frequency not in ("daily", "weekly", "manual"):
            raise ValueError(
                f"frequency must be 'daily', 'weekly', or 'manual', got: {self.frequency}"
            )
        
        if self.min_seconds_between_cycles is not None and self.min_seconds_between_cycles < 0:
            raise ValueError(
                f"min_seconds_between_cycles must be non-negative, got: {self.min_seconds_between_cycles}"
            )
    
    def get_min_seconds(self) -> Optional[int]:
        """Get minimum seconds between cycles.
        
        Returns:
            Minimum seconds (None if no limit)
        """
        if self.min_seconds_between_cycles is not None:
            return self.min_seconds_between_cycles
        
        if self.frequency == "daily":
            return 24 * 60 * 60  # 1 day
        elif self.frequency == "weekly":
            return 7 * 24 * 60 * 60  # 1 week
        else:  # manual
            return None


def check_cadence(
    cadence_config: CycleCadenceConfig,
    last_cycle_timestamp: Optional[datetime],
    current_timestamp: datetime
) -> tuple[bool, Optional[str]]:
    """Check if cycle should run based on cadence.
    
    Args:
        cadence_config: Cadence configuration
        last_cycle_timestamp: Timestamp of last cycle (None if no previous cycle)
        current_timestamp: Current timestamp
        
    Returns:
        Tuple of (should_run: bool, skip_reason: Optional[str])
    """
    min_seconds = cadence_config.get_min_seconds()
    
    if min_seconds is None:
        # No cadence limit (manual or no limit set)
        return True, None
    
    if last_cycle_timestamp is None:
        # No previous cycle - always allow
        return True, None
    
    # Check time since last cycle
    time_since_last = (current_timestamp - last_cycle_timestamp).total_seconds()
    
    if time_since_last < min_seconds:
        seconds_remaining = min_seconds - time_since_last
        return False, f"Too soon since last cycle. {seconds_remaining:.0f} seconds remaining (min: {min_seconds} seconds)"
    
    return True, None

