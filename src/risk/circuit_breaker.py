#!/usr/bin/env python3
"""
CIRCUIT BREAKER MANAGER (Step C)

Manages:
1. Daily PnL tracking and limits
2. Timezone-aware daily resets (e.g. NY Midnight)
3. Crash-safe state enforcement
"""

import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

from ..core.state_store import StateStore, CircuitBreakerState, TradingState

logger = logging.getLogger("CircuitBreaker")

class CircuitBreakerManager:
    """
    Manages daily circuit breakers with timezone precision.
    """
    def __init__(self, state_store: StateStore, risk_limit_percent: float = 0.02, timezone_str: str = "America/New_York"):
        self.store = state_store
        self.risk_limit_pct = risk_limit_percent
        self.tz = ZoneInfo(timezone_str)
        self.timezone_str = timezone_str

    def initialize_if_needed(self, current_equity: float):
        """
        Bootstrap circuit breaker state if missing.
        """
        state = self.store.load_state()
        if state.circuit_breaker is None:
            now_utc = datetime.now(timezone.utc)
            next_reset = self._compute_next_reset(now_utc)
            
            cb = CircuitBreakerState(
                status="active",
                start_of_day_equity=current_equity,
                current_equity=current_equity,
                daily_pnl=0.0,
                trip_time=None,
                reset_time=next_reset.isoformat(),
                timezone=self.timezone_str
            )
            self.store.update_circuit_breaker(cb)
            logger.info(f"Initialized Circuit Breaker. Next reset: {cb.reset_time}")

    def check_and_update(self, current_equity: float) -> bool:
        """
        Main check loop.
        1. Check for Daily Reset (Time-based)
        2. Update Equity & PnL
        3. potentially Trip (Loss-based)
        
        Returns: True if trading allowed, False if TRIPPED.
        """
        state = self.store.load_state()
        if state.circuit_breaker is None:
            self.initialize_if_needed(current_equity)
            state = self.store.load_state() # Reload

        cb_dict = state.circuit_breaker
        cb_state = CircuitBreakerState.from_dict(cb_dict)
        
        now_utc = datetime.now(timezone.utc)
        
        # 1. Check for Daily Reset
        # Handle parsed reset_time (ISO string)
        reset_dt = datetime.fromisoformat(cb_state.reset_time)
        if now_utc >= reset_dt:
            logger.info(f"Daily Reset Triggered (Now: {now_utc} >= Reset: {reset_dt})")
            return self._perform_reset(state, current_equity, now_utc)

        # If already tripped, stay tripped
        if cb_state.status == "tripped":
            return False

        # 2. Update status
        start_equity = cb_state.start_of_day_equity
        daily_pnl = current_equity - start_equity
        pnl_pct = daily_pnl / start_equity if start_equity > 0 else 0.0
        
        cb_state.current_equity = current_equity
        cb_state.daily_pnl = daily_pnl
        
        # 3. Check logic
        if pnl_pct <= -self.risk_limit_pct:
            logger.warning(f"CIRCUIT BREAKER VISITED: Daily Loss {pnl_pct:.2%} exceeds limit {-self.risk_limit_pct:.2%}")
            cb_state.status = "tripped"
            cb_state.trip_time = now_utc.isoformat()
            self.store.update_circuit_breaker(cb_state)
            return False

        # Save updates (equity tracking) periodically? 
        # For now update every check to be safe, or optimize.
        # Given atomic writes, maybe only update if PnL changed significantly?
        # Let's update every time for correctness first.
        self.store.update_circuit_breaker(cb_state)
        return True

    def _perform_reset(self, state: TradingState, current_equity: float, now_utc: datetime) -> bool:
        """
        Reset counters for new day.
        """
        next_reset = self._compute_next_reset(now_utc)
        
        cb = CircuitBreakerState(
            status="active",
            start_of_day_equity=current_equity,
            current_equity=current_equity,
            daily_pnl=0.0,
            trip_time=None,
            reset_time=next_reset.isoformat(),
            timezone=self.timezone_str
        )
        self.store.update_circuit_breaker(cb)
        logger.info(f"Circuit Breaker RESET. New Start Equity: {current_equity}. Next Reset: {cb.reset_time}")
        return True

    def _compute_next_reset(self, now_utc: datetime) -> datetime:
        """
        Calculate next 00:00 in target timezone, returned as UTC.
        """
        now_local = now_utc.astimezone(self.tz)
        
        # Tomorrow 00:00 local
        tomorrow_local = (now_local + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        return tomorrow_local.astimezone(timezone.utc)
