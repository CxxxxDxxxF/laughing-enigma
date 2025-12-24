"""Limits provider interface for broker-agnostic limit management.

This abstraction enables:
- LIVE_DRY: Deterministic limits for testing
- LIVE: Broker API integration
- Multi-firm support without hardcoding limits in rulesets
"""

from abc import ABC, abstractmethod
from datetime import datetime, date
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TradingSession:
    """Trading session information.
    
    Attributes:
        date: Trading date for this session
        start_time: Session start timestamp
        end_time: Session end timestamp (or None if ongoing)
        is_holiday: Whether this is a holiday (no trading)
    """
    date: date
    start_time: datetime
    end_time: Optional[datetime]
    is_holiday: bool = False


class LimitsProvider(ABC):
    """Abstract interface for retrieving trading limits.
    
    This abstraction separates limit retrieval from rule enforcement,
    enabling:
    - Deterministic testing (LIVE_DRY)
    - Broker API integration (LIVE)
    - Multi-firm support
    
    All limits are retrieved at runtime, never hardcoded in rulesets.
    """
    
    @abstractmethod
    def get_daily_loss_limit(self, timestamp: datetime) -> float:
        """Get daily loss limit for the given timestamp.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            Daily loss limit (negative value, e.g., -1000.0 for $1,000 limit)
            
        Raises:
            LimitsProviderError: If limit cannot be retrieved
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_trading_session(self, timestamp: datetime) -> TradingSession:
        """Get trading session information for the given timestamp.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            TradingSession with date, start/end times, holiday status
            
        Raises:
            LimitsProviderError: If session info cannot be retrieved
        """
        raise NotImplementedError
    
    def is_trading_allowed(self, timestamp: datetime) -> bool:
        """Check if trading is allowed at the given timestamp.
        
        Default implementation checks:
        - Not a holiday
        - Within session hours (if end_time is set)
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            True if trading is allowed, False otherwise
        """
        session = self.get_trading_session(timestamp)
        if session.is_holiday:
            return False
        
        if session.end_time is not None:
            return session.start_time <= timestamp <= session.end_time
        
        return timestamp >= session.start_time


class LimitsProviderError(Exception):
    """Error raised when limits provider operations fail."""
    pass

