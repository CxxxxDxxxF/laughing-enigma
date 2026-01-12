#!/usr/bin/env python3
"""
TEST CIRCUIT BREAKER LOGIC (Step C+D)

Validates:
1. Risk limit enforcement (Trip)
2. Timezone-aware daily resets (NY Midnight)
3. State persistence of breaker status
"""

import sys
import shutil
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.state_store import StateStore, CircuitBreakerState
from src.risk.circuit_breaker import CircuitBreakerManager

def test_circuit_breaker():
    print("\n[TEST] Circuit Breaker Logic")
    print("-" * 60)
    
    test_dir = Path("./test_cb_state")
    if test_dir.exists():
        shutil.rmtree(test_dir)
        
    store = StateStore(state_dir=str(test_dir))
    
    # 1. Initialize
    # Assume 2% limit
    manager = CircuitBreakerManager(store, risk_limit_percent=0.02, timezone_str="America/New_York")
    
    start_equity = 100000.0
    
    # Mock time: 10:00 AM NY (15:00 UTC)
    # NY is UTC-5 in winter (Jan)
    fake_now = datetime(2026, 1, 9, 15, 0, 0, tzinfo=timezone.utc)
    
    with patch('src.risk.circuit_breaker.datetime') as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromisoformat = datetime.fromisoformat
        
        # Initial check - should initialize
        allowed = manager.check_and_update(start_equity)
        assert allowed is True
        
        state = store.load_state()
        cb = CircuitBreakerState.from_dict(state.circuit_breaker)
        assert cb.start_of_day_equity == start_equity
        assert cb.status == "active"
        print("[OK] Initialized successfully")
        
        # 2. Normal fluctuation (Down 1%)
        allowed = manager.check_and_update(99000.0)
        assert allowed is True
        
        state = store.load_state()
        cb = CircuitBreakerState.from_dict(state.circuit_breaker)
        assert cb.daily_pnl == -1000.0
        assert cb.status == "active"
        print("[OK] Normal loss (1%) allowed")
        
        # 3. Trip trigger (Down 2.1%)
        allowed = manager.check_and_update(97900.0)
        assert allowed is False
        
        state = store.load_state()
        cb = CircuitBreakerState.from_dict(state.circuit_breaker)
        assert cb.status == "tripped"
        assert cb.trip_time is not None
        print("[OK] Tripped on 2.1% loss")
        
        # 4. Stay tripped even if equity recovers slightly (intra-day)
        allowed = manager.check_and_update(99000.0)
        assert allowed is False
        print("[OK] Remained tripped despite recovery")

    # 5. Daily Reset (Time Travel)
    # Advance to next day 00:01 NY time
    # Jan 10 00:01 NY = Jan 10 05:01 UTC
    fake_tomorrow = datetime(2026, 1, 10, 5, 1, 0, tzinfo=timezone.utc)
    
    with patch('src.risk.circuit_breaker.datetime') as mock_dt:
        mock_dt.now.return_value = fake_tomorrow
        mock_dt.fromisoformat = datetime.fromisoformat
        
        # Should perform reset (and use current equity as new start)
        current_equity = 99000.0
        allowed = manager.check_and_update(current_equity)
        assert allowed is True
        
        state = store.load_state()
        cb = CircuitBreakerState.from_dict(state.circuit_breaker)
        assert cb.status == "active"
        assert cb.start_of_day_equity == current_equity
        assert cb.trip_time is None
        
        # Verify next reset is Jan 11 NY
        next_reset = datetime.fromisoformat(cb.reset_time)
        print(f"Next reset: {next_reset}")
        assert next_reset.day == 11
        print("[OK] Reset at midnight confirmed")
    
    print("\n[SUCCESS] Circuit Breaker verified.")
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_circuit_breaker()
