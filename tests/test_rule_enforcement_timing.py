"""Tests for rule enforcement timing accuracy.

Critical: Daily loss and trailing drawdown must halt at or before firm thresholds.
These tests verify that enforcement matches funded firm behavior exactly.
"""

import sys
from pathlib import Path
from datetime import datetime, date, time, timezone
from unittest import TestCase
import zoneinfo

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rules.drawdown import DrawdownTracker, DrawdownState
from src.rules.day_boundary import TradingDayBoundary
from src.rules.topstep import TopstepRulesConfig, TopstepRuleset
from src.rules.base import RulesViolationSeverity


class TestDailyLossEnforcement(TestCase):
    """Test that daily loss halts at exact threshold."""
    
    def test_daily_loss_exact_threshold_breach(self):
        """Test that daily loss halts exactly at threshold, not before or after."""
        # Topstep 50k: Daily loss limit = -$1,000
        config = TopstepRulesConfig(
            max_daily_loss=-1000.0,
            account_size=50000.0
        )
        ruleset = TopstepRuleset(config)
        
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(
            timezone=ct_tz,
            session_start_time=time(17, 0, 0)
        )
        
        initial_balance = 50000.0
        
        # Start of day
        tracker = DrawdownTracker(
            initial_balance=initial_balance,
            trading_date=date(2024, 1, 1)
        )
        
        # At threshold exactly (-$1,000)
        equity_at_limit = initial_balance - 1000.0  # $49,000
        snapshot = tracker.update(
            equity=equity_at_limit,
            realized_pnl=-500.0,
            unrealized_pnl=-500.0,
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz),
            day_boundary=boundary
        )
        
        daily_loss = snapshot.equity - snapshot.initial_balance  # Should be -$1,000
        
        # Check violation using ruleset validation
        from src.rebalance.executor import RebalanceExecutionResult
        from src.rebalance.planner import CurrentPortfolioState
        
        # Create dummy execution result and state for validation
        dummy_execution = RebalanceExecutionResult(
            execution_id="test",
            execution_timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz),
            plan_id="test",
            intent_results=[],
            execution_summary={},
            mapping={}
        )
        
        current_state = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=initial_balance,
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz),
            positions_by_instrument={},
            drawdown_tracker=tracker  # Set tracker directly
        )
        
        # Validate execution - ruleset will check daily loss
        # Use skip_equity_recalculation=True since we've already updated the tracker with the correct equity
        violations = ruleset.validate_execution(
            dummy_execution,
            current_state,
            execution_engine=None,
            current_prices=None,
            day_boundary=boundary,
            skip_equity_recalculation=True
        )
        
        # Should have violation at exact threshold
        self.assertTrue(len(violations) > 0, "Should halt at exact threshold")
        daily_loss_violations = [v for v in violations if "DAILY_LOSS" in v.code]
        self.assertTrue(len(daily_loss_violations) > 0, "Should have daily loss violation")
        self.assertEqual(daily_loss_violations[0].severity, RulesViolationSeverity.HALT)
    
    def test_daily_loss_reset_at_session_start(self):
        """Test that daily loss resets at session start, not midnight."""
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(
            timezone=ct_tz,
            session_start_time=time(17, 0, 0)
        )
        
        initial_balance = 50000.0
        tracker = DrawdownTracker(
            initial_balance=initial_balance,
            trading_date=date(2024, 1, 1)
        )
        
        # Day 1: -$500 loss (within limit)
        ts_day1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz)
        snapshot1 = tracker.update(
            equity=initial_balance - 500.0,
            realized_pnl=-500.0,
            unrealized_pnl=0.0,
            timestamp=ts_day1,
            day_boundary=boundary
        )
        
        daily_loss_day1 = snapshot1.equity - snapshot1.initial_balance
        self.assertEqual(daily_loss_day1, -500.0, "Day 1 daily loss should be -$500")
        
        # Cross session boundary (5 PM Jan 1 → new session starts)
        ts_day2_start = datetime(2024, 1, 1, 17, 0, 0, tzinfo=ct_tz)  # Session start
        snapshot2 = tracker.update(
            equity=initial_balance - 500.0,  # Same equity (no change)
            realized_pnl=-500.0,
            unrealized_pnl=0.0,
            timestamp=ts_day2_start,
            day_boundary=boundary
        )
        
        # Daily loss should reset: new initial_balance should be current equity
        # So daily_loss = equity - new_initial_balance = 0
        daily_loss_day2 = snapshot2.equity - snapshot2.initial_balance
        self.assertEqual(daily_loss_day2, 0.0, 
                        "Daily loss should reset at session start (new initial_balance = current equity)")


class TestTrailingDrawdownLockIn(TestCase):
    """Test that trailing drawdown lock-in state never reverses."""
    
    def test_lock_in_never_reverses(self):
        """Test that once is_locked=True, it never becomes False."""
        tracker = DrawdownTracker(
            initial_balance=100000.0,
            trading_date=date(2024, 1, 1)
        )
        
        # Equity rises above initial → lock in
        snapshot1 = tracker.update(
            equity=105000.0,  # +$5,000
            realized_pnl=5000.0,
            unrealized_pnl=0.0,
            timestamp=datetime(2024, 1, 1, 10, 0, 0)
        )
        self.assertTrue(tracker.is_locked, "Should lock in when equity > initial balance")
        
        # Equity drops below initial → still locked
        snapshot2 = tracker.update(
            equity=95000.0,  # -$5,000 from initial
            realized_pnl=0.0,
            unrealized_pnl=-5000.0,
            timestamp=datetime(2024, 1, 1, 11, 0, 0)
        )
        self.assertTrue(tracker.is_locked, "Lock state should never reverse")
        
        # Trailing drawdown should be calculated from high-water mark
        self.assertEqual(snapshot2.trailing_drawdown, 10000.0,  # 105k - 95k
                        "Trailing drawdown should be from high-water mark")

