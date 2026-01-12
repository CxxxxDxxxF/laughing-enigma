#!/usr/bin/env python3
"""MarketSessionEngine for session-aware trading gates.

Provides sophisticated session logic for futures and equities:
- Entry/exit windows based on market hours
- Blackout periods (e.g., CME 4-5 PM CT break, pre-earnings for equities)
- Forced-flat windows (e.g., before Friday close, before major events)
- Daily loss stop integration
- Session state tracking

This engine enforces that no trades occur outside authorized windows,
ensuring compliance with session rules and risk limits.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional, Callable
from enum import Enum
import zoneinfo

from .market_hours import TradingSession, is_market_open, time_until_open, time_until_close
from .instrument_spec import InstrumentSpec, AssetClass


class SessionDecision(str, Enum):
    """Trading decision from session checks."""
    ALLOWED = "allowed"
    MARKET_CLOSED = "market_closed"
    ENTRY_BLACKOUT = "entry_blackout"
    FORCED_FLAT = "forced_flat"
    LOSS_LIMIT_HIT = "loss_limit_hit"


@dataclass
class SessionCheckResult:
    """Result of session validation.
    
    Attributes:
        decision: SessionDecision enum
        allowed: Quick boolean check
        reason: Human-readable explanation
        time_until_allowed: Timedelta until trading allowed (if blocked)
    """
    decision: SessionDecision
    allowed: bool
    reason: str
    time_until_allowed: Optional[timedelta] = None


class MarketSessionEngine:
    """Session-aware trading gate engine.
    
    Enforces:
    - Market open/close hours
    - CME daily breaks (4-5 PM CT for futures)
    - Entry blackouts (configurable periods)
    - Forced-flat windows (before weekends, etc.)
    - Daily loss stops
    
    Usage:
        engine = MarketSessionEngine(session, instrument)
        result = engine.is_trading_allowed(timestamp)
        if result.allowed:
            # Execute trade
        else:
            logger.info(f"Trading blocked: {result.reason}")
    """
    
    def __init__(
        self,
        session: TradingSession,
        instrument: Optional[InstrumentSpec] = None,
        daily_loss_stop: Optional[Callable[[datetime], bool]] = None,
    ):
        """Initialize session engine.
        
        Args:
            session: TradingSession definition
            instrument: Optional InstrumentSpec for asset-specific rules
            daily_loss_stop: Optional callable that returns True if loss limit hit
        """
        self.session = session
        self.instrument = instrument
        self.daily_loss_stop = daily_loss_stop
        
        # CME break: 4:00 PM - 5:00 PM CT (daily maintenance)
        self.cme_break_start = time(16, 0)  # 4 PM CT
        self.cme_break_end = time(17, 0)    # 5 PM CT
    
    def is_trading_allowed(
        self,
        timestamp: datetime,
        allow_entry: bool = True,
        allow_exit: bool = True,
    ) -> SessionCheckResult:
        """Check if trading is allowed at given timestamp.
        
        Args:
            timestamp: Current time
            allow_entry: If False, only allow closing trades
            allow_exit: If False, block all trades (for forced flat)
            
        Returns:
            SessionCheckResult with decision and reasoning
        """
        # 1. Check daily loss stop (highest priority)
        if self.daily_loss_stop and self.daily_loss_stop(timestamp):
            return SessionCheckResult(
                decision=SessionDecision.LOSS_LIMIT_HIT,
                allowed=False,
                reason="Daily loss limit exceeded - no trading allowed until reset",
            )
        
        # 2. Check if market is open
        if not is_market_open(timestamp, self.session):
            return SessionCheckResult(
                decision=SessionDecision.MARKET_CLOSED,
                allowed=False,
                reason=f"{self.session.name} is closed",
                time_until_allowed=time_until_open(timestamp, self.session),
            )
        
        # 3. Check CME break (futures only)
        if self.instrument and self.instrument.asset_class == AssetClass.FUTURES:
            if self._is_cme_break(timestamp):
                return SessionCheckResult(
                    decision=SessionDecision.ENTRY_BLACKOUT,
                    allowed=not allow_entry,  # Allow exits, block entries
                    reason="CME daily break (4-5 PM CT) - entries blocked",
                )
        
        # 4. Check entry blackout periods
        if allow_entry and self._is_entry_blackout(timestamp):
            return SessionCheckResult(
                decision=SessionDecision.ENTRY_BLACKOUT,
                allowed=not allow_entry,  # Allow exits only
                reason="Entry blackout period active",
            )
        
        # 5. Check forced-flat window (e.g., before weekend)
        if self._is_forced_flat_window(timestamp):
            return SessionCheckResult(
                decision=SessionDecision.FORCED_FLAT,
                allowed=False,
                reason="Forced-flat window - all positions must be closed",
            )
        
        # All checks passed
        return SessionCheckResult(
            decision=SessionDecision.ALLOWED,
            allowed=True,
            reason="Trading allowed",
        )
    
    def _is_cme_break(self, timestamp: datetime) -> bool:
        """Check if timestamp falls in CME daily break (4-5 PM CT).
        
        Args:
            timestamp: Timestamp to check
            
        Returns:
            True if in CME break window
        """
        tz = zoneinfo.ZoneInfo("America/Chicago")
        if timestamp.tzinfo is None:
            local_dt = timestamp.replace(tzinfo=tz)
        else:
            local_dt = timestamp.astimezone(tz)
        
        current_time = local_dt.time()
        
        # Check if between 4 PM and 5 PM CT
        return self.cme_break_start <= current_time < self.cme_break_end
    
    def _is_entry_blackout(self, timestamp: datetime) -> bool:
        """Check if timestamp falls in entry blackout period.
        
        Override this method to add custom blackout logic:
        - Pre-earnings for equities
        - FOMC announcements
        - Major economic data releases
        
        Args:
            timestamp: Timestamp to check
            
        Returns:
            True if entries should be blocked
        """
        # Default: no additional blackouts
        # Subclasses can override this
        return False
    
    def _is_forced_flat_window(self, timestamp: datetime) -> bool:
        """Check if timestamp falls in forced-flat window.
        
        Forced flat before:
        - Weekend close (Friday 4 PM for CME futures)
        - End of trading day for equities
        
        Args:
            timestamp: Timestamp to check
            
        Returns:
            True if all positions should be closed
        """
        # Check if close to market close
        time_left = time_until_close(timestamp, self.session)
        if time_left is None:
            return False  # Market closed
        
        # Forced flat in last 15 minutes before close
        if time_left < timedelta(minutes=15):
            return True
        
        # Additional: Force flat on Fridays for futures (before weekend gap)
        if self.instrument and self.instrument.asset_class == AssetClass.FUTURES:
            tz = zoneinfo.ZoneInfo(self.session.timezone)
            if timestamp.tzinfo is None:
                local_dt = timestamp.replace(tzinfo=tz)
            else:
                local_dt = timestamp.astimezone(tz)
            
            # If Friday and less than 30 minutes to close
            if local_dt.weekday() == 4 and time_left < timedelta(minutes=30):
                return True
        
        return False
    
    def time_until_next_session(self, timestamp: datetime) -> Optional[timedelta]:
        """Calculate time until next trading session.
        
        Args:
            timestamp: Current time
            
        Returns:
            Timedelta until trading allowed, or None if currently allowed
        """
        result = self.is_trading_allowed(timestamp)
        if result.allowed:
            return None
        return result.time_until_allowed


# ============================================================
# CONVENIENCE FACTORIES
# ============================================================

def create_cme_session_engine(
    instrument: InstrumentSpec,
    daily_loss_stop: Optional[Callable[[datetime], bool]] = None,
) -> MarketSessionEngine:
    """Factory for CME futures session engine.
    
    Args:
        instrument: Futures InstrumentSpec
        daily_loss_stop: Optional loss stop callback
        
    Returns:
        MarketSessionEngine configured for CME
    """
    from .market_hours import CME_FUTURES
    
    if instrument.asset_class != AssetClass.FUTURES:
        raise ValueError(f"Expected futures instrument, got {instrument.asset_class}")
    
    return MarketSessionEngine(
        session=CME_FUTURES,
        instrument=instrument,
        daily_loss_stop=daily_loss_stop,
    )


def create_equity_session_engine(
    instrument: InstrumentSpec,
    daily_loss_stop: Optional[Callable[[datetime], bool]] = None,
) -> MarketSessionEngine:
    """Factory for US equity session engine.
    
    Args:
        instrument: Equity InstrumentSpec
        daily_loss_stop: Optional loss stop callback
        
    Returns:
        MarketSessionEngine configured for US equities
    """
    from .market_hours import US_EQUITIES
    
    if instrument.asset_class != AssetClass.EQUITY:
        raise ValueError(f"Expected equity instrument, got {instrument.asset_class}")
    
    return MarketSessionEngine(
        session=US_EQUITIES,
        instrument=instrument,
        daily_loss_stop=daily_loss_stop,
    )
