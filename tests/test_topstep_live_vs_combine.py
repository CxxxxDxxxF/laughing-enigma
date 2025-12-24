"""Tests for Topstep LIVE_FUNDED vs COMBINE account type branching.

Critical: LIVE accounts must NOT have trailing drawdown and must enforce equity > 0.
COMBINE accounts must have static daily loss and trailing drawdown.
"""

import sys
from pathlib import Path
from datetime import datetime, date, time
from unittest import TestCase
import zoneinfo

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rules.topstep import TopstepRulesConfig, TopstepRuleset
from src.rules.drawdown import DrawdownTracker
from src.rules.day_boundary import TradingDayBoundary
from src.rules.base import RulesViolationSeverity, RulesetError
from src.rebalance.executor import RebalanceExecutionResult
from src.rebalance.planner import CurrentPortfolioState
from src.execution import PaperExecutionEngine
from src.execution.position import Position


class TestTopstepLiveVsCombine(TestCase):
    """Test that LIVE and COMBINE accounts enforce different rules."""
    
    def test_live_account_has_no_trailing_drawdown_and_equity_floor(self):
        """Test that LIVE accounts:
        - Do not enforce trailing drawdown
        - Enforce equity > 0 (hard floor)
        - Do not crash when max_daily_loss is None
        """
        # Create LIVE config (no static loss limits)
        live_config = TopstepRulesConfig.for_live_funded(
            max_turnover_pct=None,  # LIVE may not have static limits
            max_position_size=None,
            max_daily_loss=None,  # Ignored for LIVE (uses live_daily_loss_limit from broker)
            account_size=None
        )
        
        ruleset = TopstepRuleset(live_config)
        
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(
            timezone=ct_tz,
            session_start_time=time(17, 0, 0)
        )
        
        # Create state with equity > 0
        tracker = DrawdownTracker(
            initial_balance=50000.0,
            trading_date=date(2024, 1, 1)
        )
        
        snapshot = tracker.update(
            equity=51000.0,  # Equity above initial (positive)
            realized_pnl=1000.0,
            unrealized_pnl=0.0,
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz),
            day_boundary=boundary
        )
        
        current_state = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=50000.0,
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz),
            positions_by_instrument={},
            drawdown_tracker=tracker
        )
        
        dummy_execution = RebalanceExecutionResult(
            execution_id="test",
            execution_timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz),
            plan_id="test",
            intent_results=[],
            execution_summary={},
            mapping={}
        )
        
        # Test 1: Equity > 0 should have no violation
        violations = ruleset.validate_execution(
            dummy_execution,
            current_state,
            execution_engine=None,
            current_prices=None,
            day_boundary=boundary,
            skip_equity_recalculation=True,
            live_daily_loss_limit=-1000.0  # Inject limit for LIVE
        )
        
        # Should have no violations for equity > 0
        equity_violations = [v for v in violations if "MAXIMUM_LOSS_LIMIT" in v.code]
        self.assertEqual(len(equity_violations), 0, "Equity > 0 should not violate LIVE floor")
        
        # Test 2: Equity <= 0 should HALT
        # Need execution_engine to calculate equity from positions
        execution_engine2 = PaperExecutionEngine(instrument="AAPL")
        execution_engine2.last_price_by_instrument["AAPL"] = 100.0
        
        tracker2 = DrawdownTracker(
            initial_balance=50000.0,
            trading_date=date(2024, 1, 1)
        )
        
        snapshot2 = tracker2.update(
            equity=-100.0,  # Equity below zero
            realized_pnl=-50100.0,
            unrealized_pnl=0.0,
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz),
            day_boundary=boundary
        )
        
        current_state2 = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=50000.0,
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz),
            positions_by_instrument={},
            drawdown_tracker=tracker2
        )
        
        violations2 = ruleset.validate_execution(
            dummy_execution,
            current_state2,
            execution_engine=execution_engine2,
            current_prices={"AAPL": 100.0},
            day_boundary=boundary,
            skip_equity_recalculation=True,  # Use precomputed equity from tracker
            live_daily_loss_limit=-1000.0  # Inject limit for LIVE
        )
        
        # Should have HALT violation for equity <= 0
        equity_violations2 = [v for v in violations2 if "MAXIMUM_LOSS_LIMIT" in v.code]
        self.assertGreater(len(equity_violations2), 0, "Equity <= 0 should HALT for LIVE")
        self.assertEqual(equity_violations2[0].severity, RulesViolationSeverity.HALT)
        
        # Test 3: No trailing drawdown check for LIVE (even if locked)
        tracker3 = DrawdownTracker(
            initial_balance=50000.0,
            trading_date=date(2024, 1, 1)
        )
        
        # Lock in trailing drawdown (equity > initial)
        snapshot3 = tracker3.update(
            equity=55000.0,  # Above initial, should lock
            realized_pnl=5000.0,
            unrealized_pnl=0.0,
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz),
            day_boundary=boundary
        )
        self.assertTrue(tracker3.is_locked, "Tracker should be locked")
        
        # Drop equity but stay above zero
        snapshot4 = tracker3.update(
            equity=40000.0,  # Below initial but above zero
            realized_pnl=0.0,
            unrealized_pnl=-15000.0,
            timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=ct_tz),
            day_boundary=boundary
        )
        
        current_state3 = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=50000.0,
            timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=ct_tz),
            positions_by_instrument={},
            drawdown_tracker=tracker3
        )
        
        violations3 = ruleset.validate_execution(
            dummy_execution,
            current_state3,
            execution_engine=None,
            current_prices=None,
            day_boundary=boundary,
            skip_equity_recalculation=True,
            live_daily_loss_limit=-1000.0  # Inject limit for LIVE
        )
        
        # Should have NO trailing drawdown violations (LIVE doesn't check this)
        trailing_violations = [v for v in violations3 if "TRAILING_DRAWDOWN" in v.code]
        self.assertEqual(len(trailing_violations), 0, "LIVE should not check trailing drawdown")
        
        # Should have NO violation because equity > 0
        equity_violations3 = [v for v in violations3 if "MAXIMUM_LOSS_LIMIT" in v.code]
        self.assertEqual(len(equity_violations3), 0, "Equity > 0 should not violate LIVE floor")
    
    def test_combine_account_requires_static_limits(self):
        """Test that COMBINE accounts require static daily loss and trailing drawdown."""
        # COMBINE config with required limits
        combine_config = TopstepRulesConfig.for_combine(
            max_turnover_pct=100.0,
            max_position_size=None,
            max_daily_loss=-1000.0,  # Required for COMBINE
            max_trailing_drawdown_pct=5.0,  # Required for COMBINE
            account_size=50000.0
        )
        
        ruleset = TopstepRuleset(combine_config)
        
        # Verify config is valid (COMBINE has trailing drawdown, LIVE_FUNDED does not)
        self.assertIsNotNone(combine_config.max_trailing_drawdown_pct, "COMBINE must have trailing drawdown")
        self.assertEqual(combine_config.max_daily_loss, -1000.0)
        self.assertEqual(combine_config.max_trailing_drawdown_pct, 5.0)
    
    def test_live_config_rejects_static_limits(self):
        """Test that LIVE config accepts max_daily_loss but ignores it (uses live_daily_loss_limit from broker)."""
        # LIVE_FUNDED accepts max_daily_loss in constructor but ignores it
        # (uses live_daily_loss_limit from broker instead)
        # This test verifies that LIVE_FUNDED factory accepts max_daily_loss for API compatibility
        live_config = TopstepRulesConfig.for_live_funded(
            max_daily_loss=-1000.0,  # Accepted but ignored (uses live_daily_loss_limit from broker)
            account_size=None
        )
        # Verify it was created (no error)
        self.assertIsNotNone(live_config)
        # Verify trailing drawdown is None (LIVE_FUNDED doesn't enforce it)
        self.assertIsNone(live_config.max_trailing_drawdown_pct, "LIVE_FUNDED should not have trailing drawdown")
    
    def test_account_type_required(self):
        """Test that factory methods are required for account type configuration."""
        # Factory methods are now required - direct constructor no longer accepts account_type
        # Verify factory methods work:
        combine_config = TopstepRulesConfig.for_combine(max_daily_loss=-1000.0)
        live_config = TopstepRulesConfig.for_live_funded()
        self.assertIsNotNone(combine_config)
        self.assertIsNotNone(live_config)
        
        # Verify COMBINE allows trailing drawdown, LIVE_FUNDED does not
        # COMBINE can have trailing drawdown set (it's optional in factory, but required for validation)
        combine_config_with_td = TopstepRulesConfig.for_combine(
            max_daily_loss=-1000.0,
            max_trailing_drawdown_pct=5.0
        )
        self.assertIsNotNone(combine_config_with_td.max_trailing_drawdown_pct, "COMBINE should allow trailing drawdown")
        self.assertIsNone(live_config.max_trailing_drawdown_pct, "LIVE_FUNDED should not have trailing drawdown")
    
    def test_live_daily_loss_limit_injection_required_and_enforced(self):
        """
        Test that LIVE_FUNDED accounts:
        1. Require live_daily_loss_limit to be injected (RuntimeError if missing)
        2. Enforce the injected limit when present (HALT if breached)
        """
        # Setup
        live_config = TopstepRulesConfig.for_live_funded(
            max_turnover_pct=None,
            max_position_size=None,
            max_daily_loss=None,  # Ignored for LIVE (uses live_daily_loss_limit from broker)
            account_size=None
        )
        ruleset = TopstepRuleset(live_config)
        
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(
            timezone=ct_tz,
            session_start_time=time(17, 0, 0)
        )
        
        initial_balance = 50000.0
        timestamp = datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz)
        
        # Create execution engine with a position
        execution_engine = PaperExecutionEngine(instrument="AAPL")
        execution_engine.positions["AAPL"] = Position(
            instrument="AAPL",
            quantity=100.0,
            cost_basis=100.0,
            realized_pnl=0.0,
            updated_at=timestamp
        )
        execution_engine.last_price_by_instrument["AAPL"] = 100.0
        
        # Create execution result
        execution_result = RebalanceExecutionResult(
            execution_id="test",
            execution_timestamp=timestamp,
            plan_id="test",
            intent_results=[],
            execution_summary={},
            mapping={}
        )
        
        # Test 1: Missing live_daily_loss_limit → RuntimeError
        tracker_missing = DrawdownTracker(
            initial_balance=initial_balance,
            trading_date=timestamp.date()
        )
        tracker_missing.update(
            equity=initial_balance - 500.0,
            realized_pnl=-500.0,
            unrealized_pnl=0.0,
            timestamp=timestamp,
            day_boundary=boundary
        )
        current_state_missing = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=initial_balance,
            timestamp=timestamp,
            positions_by_instrument=execution_engine.positions,
            drawdown_tracker=tracker_missing
        )
        
        with self.assertRaises(RulesetError) as context:
            ruleset.validate_execution(
                execution_result,
                current_state_missing,
                execution_engine=execution_engine,
                current_prices={"AAPL": 100.0},
                day_boundary=boundary,
                live_daily_loss_limit=None  # Missing - should raise
            )
        
        self.assertIn("LIVE_FUNDED account requires live_daily_loss_limit", str(context.exception))
        
        # Test 2: live_daily_loss_limit present, daily_loss above limit → no violation
        tracker_above = DrawdownTracker(
            initial_balance=initial_balance,
            trading_date=timestamp.date()
        )
        tracker_above.update(
            equity=initial_balance - 500.0,  # -$500 loss
            realized_pnl=-500.0,
            unrealized_pnl=0.0,
            timestamp=timestamp,
            day_boundary=boundary
        )
        current_state_above = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=initial_balance,
            timestamp=timestamp,
            positions_by_instrument=execution_engine.positions,
            drawdown_tracker=tracker_above
        )
        
        violations_above = ruleset.validate_execution(
            execution_result,
            current_state_above,
            execution_engine=execution_engine,
            current_prices={"AAPL": 100.0},
            day_boundary=boundary,
            live_daily_loss_limit=-1000.0  # Limit is -$1000, loss is -$500, so no breach
        )
        
        self.assertFalse(
            any("DAILY_LOSS" in v.code for v in violations_above),
            "Should not halt if daily loss is above limit"
        )
        
        # Test 3: live_daily_loss_limit present, daily_loss ≤ limit → HALT
        # Set up positions to match the equity we want to test
        execution_engine_breach = PaperExecutionEngine(instrument="AAPL")
        execution_engine_breach.positions["AAPL"] = Position(
            instrument="AAPL",
            quantity=100.0,
            cost_basis=100.0,
            realized_pnl=-1000.0,  # Realized loss of $1000
            updated_at=timestamp
        )
        execution_engine_breach.last_price_by_instrument["AAPL"] = 100.0
        
        tracker_breach = DrawdownTracker(
            initial_balance=initial_balance,
            trading_date=timestamp.date()
        )
        # Note: validate_execution will recalculate equity from positions
        # So we don't need to pre-update the tracker
        
        current_state_breach = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=initial_balance,
            timestamp=timestamp,
            positions_by_instrument=execution_engine_breach.positions,
            drawdown_tracker=tracker_breach
        )
        
        violations_breach = ruleset.validate_execution(
            execution_result,
            current_state_breach,
            execution_engine=execution_engine_breach,
            current_prices={"AAPL": 100.0},
            day_boundary=boundary,
            live_daily_loss_limit=-1000.0  # Limit is -$1000, loss is -$1000, so breach (inclusive)
        )
        
        self.assertTrue(
            any(
                "DAILY_LOSS" in v.code and v.severity == RulesViolationSeverity.HALT
                for v in violations_breach
            ),
            "Should halt if daily loss equals or exceeds limit"
        )
        
        # Test 4: live_daily_loss_limit present, daily_loss exceeds limit → HALT
        # Set up positions to match the equity we want to test
        execution_engine_exceed = PaperExecutionEngine(instrument="AAPL")
        execution_engine_exceed.positions["AAPL"] = Position(
            instrument="AAPL",
            quantity=100.0,
            cost_basis=100.0,
            realized_pnl=-1500.0,  # Realized loss of $1500
            updated_at=timestamp
        )
        execution_engine_exceed.last_price_by_instrument["AAPL"] = 100.0
        
        tracker_exceed = DrawdownTracker(
            initial_balance=initial_balance,
            trading_date=timestamp.date()
        )
        # Note: validate_execution will recalculate equity from positions
        
        current_state_exceed = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=initial_balance,
            timestamp=timestamp,
            positions_by_instrument=execution_engine_exceed.positions,
            drawdown_tracker=tracker_exceed
        )
        
        violations_exceed = ruleset.validate_execution(
            execution_result,
            current_state_exceed,
            execution_engine=execution_engine_exceed,
            current_prices={"AAPL": 100.0},
            day_boundary=boundary,
            live_daily_loss_limit=-1000.0  # Limit is -$1000, loss is -$1500, so breach
        )
        
        self.assertTrue(
            any(
                "DAILY_LOSS" in v.code and v.severity == RulesViolationSeverity.HALT
                for v in violations_exceed
            ),
            "Should halt if daily loss exceeds limit"
        )

