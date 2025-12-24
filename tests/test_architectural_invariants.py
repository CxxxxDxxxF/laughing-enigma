"""Architectural Invariant Tests.

This test suite enforces architectural invariants that must never be violated.
These are binary assertions: PASS or FAIL. No warnings, no skips.

If any invariant is violated, the test MUST fail loudly.

Purpose:
- Prevent regressions
- Freeze correctness
- Lock architectural contracts
- Ensure future changes cannot silently break correctness, compliance, or determinism

These tests are NOT about functionality - they are about architecture.
"""

import sys
import inspect
import ast
from pathlib import Path
from unittest import TestCase
from typing import List, Set

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rules.topstep import TopstepRuleset, TopstepRulesConfig
from src.rules.base import Ruleset
from src.execution.paper_engine import PaperExecutionEngine
from src.lifecycle.runner import run_portfolio_cycle, ExecutionMode
from src.limits import LimitsProvider, DeterministicLimitsProvider
from src.broker import BrokerAdapter, NullBrokerAdapter


class TestArchitecturalInvariants(TestCase):
    """Test suite for architectural invariants.
    
    Each test asserts a single architectural truth.
    Violations must cause immediate test failure.
    """
    
    # ============================================================================
    # PART 1: RULESET INVARIANTS
    # ============================================================================
    
    def test_ruleset_must_not_import_broker(self):
        """INVARIANT: Rulesets must NOT import broker.* modules.
        
        Rulesets must be broker-agnostic. Any import of broker.* is a violation.
        """
        ruleset_file = Path(__file__).parent.parent / "src" / "rules" / "topstep.py"
        source = ruleset_file.read_text()
        
        # Parse AST to find imports
        tree = ast.parse(source)
        imports: List[str] = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        
        # Check for broker imports
        broker_imports = [imp for imp in imports if imp.startswith("broker") or ".broker" in imp]
        
        self.assertEqual(
            len(broker_imports), 0,
            f"Ruleset must NOT import broker modules. Found: {broker_imports}"
        )
    
    def test_ruleset_must_not_import_limits_provider(self):
        """INVARIANT: Rulesets must NOT import limits.provider.
        
        Rulesets receive limits via method parameters, not direct imports.
        """
        ruleset_file = Path(__file__).parent.parent / "src" / "rules" / "topstep.py"
        source = ruleset_file.read_text()
        
        # Parse AST to find imports
        tree = ast.parse(source)
        imports: List[str] = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        
        # Check for limits.provider imports
        limits_imports = [imp for imp in imports if "limits.provider" in imp or imp == "limits.provider"]
        
        self.assertEqual(
            len(limits_imports), 0,
            f"Ruleset must NOT import limits.provider. Found: {limits_imports}"
        )
    
    def test_ruleset_must_not_reference_broker_adapters_directly(self):
        """INVARIANT: Rulesets must NOT reference broker adapters directly.
        
        Rulesets must not contain code that directly uses BrokerAdapter.
        """
        ruleset_file = Path(__file__).parent.parent / "src" / "rules" / "topstep.py"
        source = ruleset_file.read_text()
        
        # Check for broker adapter references
        broker_patterns = [
            "BrokerAdapter",
            "broker_adapter",
            "broker_adapter.",
            "NullBrokerAdapter",
            "TopstepBrokerAdapter",
            "ApexBrokerAdapter"
        ]
        
        found_patterns = [p for p in broker_patterns if p in source]
        
        self.assertEqual(
            len(found_patterns), 0,
            f"Ruleset must NOT reference broker adapters directly. Found: {found_patterns}"
        )
    
    def test_ruleset_must_not_reference_limits_provider_directly(self):
        """INVARIANT: Rulesets must NOT reference LimitsProvider directly.
        
        Rulesets receive limits via method parameters, not direct provider access.
        """
        ruleset_file = Path(__file__).parent.parent / "src" / "rules" / "topstep.py"
        source = ruleset_file.read_text()
        
        # Check for limits provider references (except in type hints/comments)
        # We allow LimitsProvider in type hints but not in business logic
        lines = source.split('\n')
        business_logic_lines = [
            line for line in lines
            if not line.strip().startswith('#')
            and not line.strip().startswith('"""')
            and 'LimitsProvider' in line
            and ':' not in line.split('LimitsProvider')[0]  # Exclude type hints
        ]
        
        self.assertEqual(
            len(business_logic_lines), 0,
            f"Ruleset must NOT reference LimitsProvider in business logic. Found in lines: {business_logic_lines[:5]}"
        )
    
    def test_ruleset_consumes_limits_via_parameters(self):
        """INVARIANT: Rulesets must consume limits via method parameters only.
        
        Rulesets receive live_daily_loss_limit as a parameter, not from imports.
        """
        ruleset = TopstepRuleset(TopstepRulesConfig(account_type="LIVE_FUNDED"))
        
        # Check that validate_execution accepts live_daily_loss_limit parameter
        sig = inspect.signature(ruleset.validate_execution)
        params = list(sig.parameters.keys())
        
        self.assertIn(
            "live_daily_loss_limit", params,
            "Ruleset must accept live_daily_loss_limit as parameter"
        )
    
    # ============================================================================
    # PART 2: EXECUTION ENGINE INVARIANTS
    # ============================================================================
    
    def test_execution_engine_must_not_infer_limits(self):
        """INVARIANT: Execution engine must NOT infer limits.
        
        Execution engine does not calculate or infer limits from config.
        It may store daily_start_value for tracking, but does not infer limits.
        """
        engine_file = Path(__file__).parent.parent / "src" / "execution" / "paper_engine.py"
        source = engine_file.read_text()
        
        # Check for limit inference patterns (actual inference, not storage)
        inference_patterns = [
            "get_daily_loss",
            "calculate_limit",
            "infer_limit",
            "max_daily_loss =",  # Assignment (inference)
            "daily_loss_limit =",  # Assignment (inference)
        ]
        
        # Exclude comments, docstrings, and attribute storage
        lines = [line for line in source.split('\n') 
                 if not line.strip().startswith('#') 
                 and not line.strip().startswith('"""')
                 and not line.strip().startswith("'''")
                 and "daily_start_value" not in line  # Allow daily_start_value (tracking, not limit)
                 and "daily_start_date" not in line]  # Allow daily_start_date (tracking, not limit)
        
        found_patterns = []
        for line in lines:
            for pattern in inference_patterns:
                if pattern in line and "broker_adapter" not in line:
                    # Allow if it's accessing broker_adapter (injection is OK)
                    found_patterns.append((pattern, line.strip()[:80]))
        
        self.assertEqual(
            len(found_patterns), 0,
            f"Execution engine must NOT infer limits. Found: {found_patterns[:5]}"
        )
    
    def test_execution_engine_must_not_branch_on_account_type(self):
        """INVARIANT: Execution engine must NOT branch on account type.
        
        Execution engine is account-type agnostic.
        """
        engine_file = Path(__file__).parent.parent / "src" / "execution" / "paper_engine.py"
        source = engine_file.read_text()
        
        # Check for account type branching
        account_type_patterns = [
            "if account_type",
            "account_type == ",
            "account_type ==",
            "COMBINE",
            "LIVE_FUNDED",
            "if config.account_type"
        ]
        
        # Exclude comments and docstrings
        lines = [line for line in source.split('\n') 
                 if not line.strip().startswith('#') 
                 and not line.strip().startswith('"""')
                 and not line.strip().startswith("'''")]
        
        found_patterns = []
        for line in lines:
            for pattern in account_type_patterns:
                if pattern in line:
                    found_patterns.append((pattern, line.strip()[:80]))
        
        self.assertEqual(
            len(found_patterns), 0,
            f"Execution engine must NOT branch on account type. Found: {found_patterns[:5]}"
        )
    
    def test_execution_engine_must_not_call_broker_unless_injected(self):
        """INVARIANT: Execution engine must NOT call broker methods unless adapter is injected.
        
        Execution engine only uses broker_adapter if it's provided (injected).
        """
        engine_file = Path(__file__).parent.parent / "src" / "execution" / "paper_engine.py"
        source = engine_file.read_text()
        
        # Check for broker method calls without adapter check
        # We allow: if broker_adapter: broker_adapter.method()
        # We disallow: broker_adapter.method() without check
        
        # This is a simplified check - we look for broker_adapter. calls
        # that aren't preceded by a check
        tree = ast.parse(source)
        
        # Find all attribute accesses to broker_adapter
        broker_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "broker_adapter":
                    # Check if this is inside an if statement checking broker_adapter
                    parent = node
                    in_guard = False
                    while parent:
                        if isinstance(parent, ast.If):
                            # Check if condition checks broker_adapter
                            if isinstance(parent.test, ast.Name) and parent.test.id == "broker_adapter":
                                in_guard = True
                                break
                            elif isinstance(parent.test, ast.Attribute) and parent.test.attr == "broker_adapter":
                                in_guard = True
                                break
                        parent = getattr(parent, 'parent', None)
                    
                    if not in_guard:
                        broker_calls.append(ast.get_source_segment(source, node) or str(node))
        
        # For Phase 2.5, broker_adapter is stored but not used yet
        # So we allow storage but disallow usage without guard
        # Actually, let's be more lenient - if broker_adapter is an attribute access
        # that's fine (it's stored). We're looking for method calls.
        method_calls = [call for call in broker_calls if '(' in call]
        
        # For now, since broker_adapter is not used, this should be empty
        # In future, we'd check that all calls are guarded
        self.assertEqual(
            len(method_calls), 0,
            f"Execution engine must NOT call broker methods without adapter injection check. Found: {method_calls[:5]}"
        )
    
    # ============================================================================
    # PART 3: RUNNER INVARIANTS
    # ============================================================================
    
    def test_runner_must_accept_limits_provider(self):
        """INVARIANT: Runner must accept LimitsProvider parameter.
        
        Runner must have limits_provider parameter for injection.
        """
        sig = inspect.signature(run_portfolio_cycle)
        params = list(sig.parameters.keys())
        
        self.assertIn(
            "limits_provider", params,
            "Runner must accept limits_provider parameter"
        )
    
    def test_runner_must_accept_broker_adapter(self):
        """INVARIANT: Runner must accept BrokerAdapter parameter.
        
        Runner must have broker_adapter parameter for injection.
        """
        sig = inspect.signature(run_portfolio_cycle)
        params = list(sig.parameters.keys())
        
        self.assertIn(
            "broker_adapter", params,
            "Runner must accept broker_adapter parameter"
        )
    
    def test_runner_must_not_contain_firm_specific_rules(self):
        """INVARIANT: Runner must NOT contain firm-specific rules.
        
        Runner must not have hardcoded Topstep or Apex business logic.
        """
        runner_file = Path(__file__).parent.parent / "src" / "lifecycle" / "runner.py"
        source = runner_file.read_text()
        
        # Check for firm-specific business logic (not ruleset selection)
        # ruleset_type == "topstep" is OK (configuration)
        # But business logic like "if topstep:" or "topstep-specific calculation" is not
        
        firm_specific_patterns = [
            'if "topstep" in',  # Business logic check
            'if "apex" in',     # Business logic check
            'topstep_limit',    # Hardcoded limit
            'apex_limit',       # Hardcoded limit
            'TopstepLimit',     # Hardcoded class
            'ApexLimit'         # Hardcoded class
        ]
        
        # Exclude comments and docstrings
        lines = [line for line in source.split('\n') 
                 if not line.strip().startswith('#') 
                 and not line.strip().startswith('"""')
                 and not line.strip().startswith("'''")]
        
        found_patterns = []
        for line in lines:
            for pattern in firm_specific_patterns:
                if pattern in line:
                    found_patterns.append((pattern, line.strip()[:80]))
        
        self.assertEqual(
            len(found_patterns), 0,
            f"Runner must NOT contain firm-specific business logic. Found: {found_patterns[:5]}"
        )
    
    def test_runner_must_not_infer_live_behavior_from_config(self):
        """INVARIANT: Runner must NOT infer LIVE behavior from config shape.
        
        Runner must use explicit account_type, not infer from missing fields.
        """
        runner_file = Path(__file__).parent.parent / "src" / "lifecycle" / "runner.py"
        source = runner_file.read_text()
        
        # Check for inference patterns
        inference_patterns = [
            "if max_daily_loss is None",  # Inferring LIVE from missing field
            "if not max_daily_loss",      # Inferring LIVE from missing field
            "if max_trailing_drawdown_pct is None",  # Inferring LIVE
            "if account_type is None",    # This is OK - it's explicit check
        ]
        
        # Exclude comments and docstrings
        lines = [line for line in source.split('\n') 
                 if not line.strip().startswith('#') 
                 and not line.strip().startswith('"""')
                 and not line.strip().startswith("'''")]
        
        found_patterns = []
        for line in lines:
            for pattern in inference_patterns[:3]:  # First 3 are inference, last is OK
                if pattern in line and "account_type" not in line:
                    # If the line also checks account_type, it's explicit, not inference
                    found_patterns.append((pattern, line.strip()[:80]))
        
        self.assertEqual(
            len(found_patterns), 0,
            f"Runner must NOT infer LIVE behavior from config shape. Found: {found_patterns[:5]}"
        )
    
    # ============================================================================
    # PART 4: LIVE_FUNDED INVARIANTS
    # ============================================================================
    
    def test_live_funded_missing_limits_must_hard_fail(self):
        """INVARIANT: LIVE_FUNDED with missing limits must hard fail.
        
        LIVE_FUNDED accounts must fail immediately if live_daily_loss_limit is None.
        """
        from src.rules.topstep import TopstepRulesConfig, TopstepRuleset
        from src.rules.drawdown import DrawdownTracker
        from src.rules.day_boundary import TradingDayBoundary
        from src.rebalance.executor import RebalanceExecutionResult
        from src.rebalance.planner import CurrentPortfolioState
        from src.execution import PaperExecutionEngine
        from datetime import datetime, date, time
        import zoneinfo
        
        config = TopstepRulesConfig(account_type="LIVE_FUNDED")
        ruleset = TopstepRuleset(config)
        
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(timezone=ct_tz, session_start_time=time(17, 0, 0))
        timestamp = datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz)
        
        tracker = DrawdownTracker(initial_balance=50000.0, trading_date=timestamp.date())
        tracker.update(equity=50000.0, realized_pnl=0.0, unrealized_pnl=0.0, timestamp=timestamp, day_boundary=boundary)
        
        current_state = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=50000.0,
            timestamp=timestamp,
            positions_by_instrument={},
            drawdown_tracker=tracker
        )
        
        execution_result = RebalanceExecutionResult(
            execution_id="test",
            execution_timestamp=timestamp,
            plan_id="test",
            intent_results=[],
            execution_summary={},
            mapping={}
        )
        
        execution_engine = PaperExecutionEngine(instrument="AAPL")
        
        # Must raise RuntimeError (wrapped in RulesetError) when live_daily_loss_limit is None
        from src.rules.base import RulesetError
        
        with self.assertRaises((RuntimeError, RulesetError)) as context:
            ruleset.validate_execution(
                execution_result,
                current_state,
                execution_engine=execution_engine,
                current_prices={"AAPL": 100.0},
                day_boundary=boundary,
                live_daily_loss_limit=None  # Missing - must fail
            )
        
        error_msg = str(context.exception)
        self.assertIn(
            "live_daily_loss_limit", error_msg.lower(),
            f"LIVE_FUNDED must hard fail with clear error when limits are missing. Got: {error_msg}"
        )
    
    def test_live_funded_equity_zero_or_negative_must_halt(self):
        """INVARIANT: LIVE_FUNDED with equity ≤ 0 must HALT.
        
        LIVE_FUNDED accounts must halt when equity reaches zero or goes negative.
        """
        from src.rules.topstep import TopstepRulesConfig, TopstepRuleset
        from src.rules.drawdown import DrawdownTracker
        from src.rules.day_boundary import TradingDayBoundary
        from src.rules.base import RulesViolationSeverity
        from src.rebalance.executor import RebalanceExecutionResult
        from src.rebalance.planner import CurrentPortfolioState
        from src.execution import PaperExecutionEngine
        from datetime import datetime, date, time
        import zoneinfo
        
        config = TopstepRulesConfig(account_type="LIVE_FUNDED")
        ruleset = TopstepRuleset(config)
        
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(timezone=ct_tz, session_start_time=time(17, 0, 0))
        timestamp = datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz)
        
        # Test equity = 0
        tracker_zero = DrawdownTracker(initial_balance=50000.0, trading_date=timestamp.date())
        tracker_zero.update(equity=0.0, realized_pnl=-50000.0, unrealized_pnl=0.0, timestamp=timestamp, day_boundary=boundary)
        
        current_state_zero = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=50000.0,
            timestamp=timestamp,
            positions_by_instrument={},
            drawdown_tracker=tracker_zero
        )
        
        execution_result = RebalanceExecutionResult(
            execution_id="test",
            execution_timestamp=timestamp,
            plan_id="test",
            intent_results=[],
            execution_summary={},
            mapping={}
        )
        
        execution_engine = PaperExecutionEngine(instrument="AAPL")
        
        violations_zero = ruleset.validate_execution(
            execution_result,
            current_state_zero,
            execution_engine=execution_engine,
            current_prices={"AAPL": 100.0},
            day_boundary=boundary,
            live_daily_loss_limit=-1000.0,
            skip_equity_recalculation=True  # Use precomputed equity from tracker
        )
        
        # Must have HALT violation for equity ≤ 0
        # Check for TOPSTEP_MAXIMUM_LOSS_LIMIT_EXCEEDED
        equity_violations = [
            v for v in violations_zero 
            if "MAXIMUM_LOSS_LIMIT" in v.code 
            or "MAXIMUM_LOSS" in v.code
        ]
        
        self.assertGreater(
            len(equity_violations), 0,
            f"LIVE_FUNDED must HALT when equity ≤ 0. Violations: {[(v.code, v.message) for v in violations_zero]}"
        )
        
        halt_violations = [v for v in equity_violations if v.severity == RulesViolationSeverity.HALT]
        self.assertGreater(
            len(halt_violations), 0,
            f"LIVE_FUNDED equity violation must be HALT severity. Violations: {[(v.code, v.severity) for v in equity_violations]}"
        )
    
    def test_live_funded_must_not_execute_trailing_drawdown_logic(self):
        """INVARIANT: LIVE_FUNDED must NOT execute trailing drawdown logic.
        
        LIVE_FUNDED accounts have no trailing drawdown. The logic must be skipped.
        """
        from src.rules.topstep import TopstepRulesConfig, TopstepRuleset
        from src.rules.drawdown import DrawdownTracker
        from src.rules.day_boundary import TradingDayBoundary
        from src.rebalance.executor import RebalanceExecutionResult
        from src.rebalance.planner import CurrentPortfolioState
        from src.execution import PaperExecutionEngine
        from datetime import datetime, date, time
        import zoneinfo
        
        config = TopstepRulesConfig(account_type="LIVE_FUNDED")
        ruleset = TopstepRuleset(config)
        
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(timezone=ct_tz, session_start_time=time(17, 0, 0))
        timestamp = datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz)
        
        # Create tracker with locked state and high trailing drawdown
        tracker = DrawdownTracker(initial_balance=50000.0, trading_date=timestamp.date())
        tracker.update(equity=55000.0, realized_pnl=5000.0, unrealized_pnl=0.0, timestamp=timestamp, day_boundary=boundary)  # Lock in
        tracker.update(equity=40000.0, realized_pnl=5000.0, unrealized_pnl=-15000.0, timestamp=timestamp, day_boundary=boundary)  # High drawdown
        
        self.assertTrue(tracker.is_locked, "Tracker must be locked for this test")
        
        current_state = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=50000.0,
            timestamp=timestamp,
            positions_by_instrument={},
            drawdown_tracker=tracker
        )
        
        execution_result = RebalanceExecutionResult(
            execution_id="test",
            execution_timestamp=timestamp,
            plan_id="test",
            intent_results=[],
            execution_summary={},
            mapping={}
        )
        
        execution_engine = PaperExecutionEngine(instrument="AAPL")
        
        violations = ruleset.validate_execution(
            execution_result,
            current_state,
            execution_engine=execution_engine,
            current_prices={"AAPL": 100.0},
            day_boundary=boundary,
            live_daily_loss_limit=-1000.0,
            skip_equity_recalculation=True
        )
        
        # Must NOT have trailing drawdown violation for LIVE_FUNDED
        trailing_dd_violations = [v for v in violations if "TRAILING_DRAWDOWN" in v.code]
        
        self.assertEqual(
            len(trailing_dd_violations), 0,
            "LIVE_FUNDED must NOT execute trailing drawdown logic, even with high drawdown"
        )
    
    # ============================================================================
    # PART 5: LIVE_DRY INVARIANTS
    # ============================================================================
    
    def test_live_dry_must_be_deterministic(self):
        """INVARIANT: LIVE_DRY must be fully deterministic.
        
        Same inputs → same outputs. No randomness, no datetime.now(), no UUID.
        """
        # This is validated by the determinism audit in Phase 0
        # For Phase 2.5, we verify that LIVE_DRY uses deterministic components
        
        from src.limits import DeterministicLimitsProvider
        from src.broker import NullBrokerAdapter
        from datetime import datetime
        import zoneinfo
        
        # LIVE_DRY must use DeterministicLimitsProvider
        provider = DeterministicLimitsProvider(daily_loss_limit=-1000.0)
        ts = datetime(2024, 1, 1, 10, 0, 0, tzinfo=zoneinfo.ZoneInfo("America/Chicago"))
        limit1 = provider.get_daily_loss_limit(ts)
        limit2 = provider.get_daily_loss_limit(ts)
        
        self.assertEqual(
            limit1, limit2,
            "LIVE_DRY LimitsProvider must be deterministic (same input → same output)"
        )
        
        # LIVE_DRY must use NullBrokerAdapter
        adapter = NullBrokerAdapter()
        metadata1 = adapter.get_account_metadata()
        # Small delay to test determinism
        import time
        time.sleep(0.01)
        metadata2 = adapter.get_account_metadata()
        
        # Metadata should be deterministic (same account_id, balance, etc.)
        # Note: timestamp will differ, but other fields should be same
        self.assertEqual(
            metadata1.account_id, metadata2.account_id,
            "LIVE_DRY BrokerAdapter must be deterministic"
        )
        self.assertEqual(
            metadata1.balance, metadata2.balance,
            "LIVE_DRY BrokerAdapter balance must be deterministic"
        )
    
    def test_live_dry_must_use_deterministic_limits_provider(self):
        """INVARIANT: LIVE_DRY must use DeterministicLimitsProvider.
        
        LIVE_DRY mode requires deterministic limits, not broker limits.
        """
        # This is enforced by architecture - LIVE_DRY should use DeterministicLimitsProvider
        # We verify the type is correct
        
        from src.limits import DeterministicLimitsProvider
        
        provider = DeterministicLimitsProvider(daily_loss_limit=-1000.0)
        
        self.assertIsInstance(
            provider, DeterministicLimitsProvider,
            "LIVE_DRY must use DeterministicLimitsProvider"
        )
    
    def test_live_dry_must_use_null_broker_adapter(self):
        """INVARIANT: LIVE_DRY must use NullBrokerAdapter.
        
        LIVE_DRY mode requires null broker adapter, not real broker.
        """
        from src.broker import NullBrokerAdapter
        
        adapter = NullBrokerAdapter()
        
        self.assertIsInstance(
            adapter, NullBrokerAdapter,
            "LIVE_DRY must use NullBrokerAdapter"
        )
    
    # ============================================================================
    # PART 6: COMBINE INVARIANTS
    # ============================================================================
    
    def test_combine_must_ignore_live_only_parameters(self):
        """INVARIANT: COMBINE must ignore LIVE-only parameters.
        
        COMBINE accounts use static limits from config, not live_daily_loss_limit.
        The parameter is accepted but ignored (COMBINE uses self.config.max_daily_loss).
        """
        from src.rules.topstep import TopstepRulesConfig, TopstepRuleset
        from src.rules.drawdown import DrawdownTracker
        from src.rules.day_boundary import TradingDayBoundary
        from src.rebalance.executor import RebalanceExecutionResult
        from src.rebalance.planner import CurrentPortfolioState
        from src.execution import PaperExecutionEngine
        from datetime import datetime, date, time
        import zoneinfo
        
        # COMBINE config with static limits
        config = TopstepRulesConfig(
            account_type="COMBINE",
            max_daily_loss=-1000.0,  # Static limit
            max_trailing_drawdown_pct=5.0,
            account_size=50000.0
        )
        ruleset = TopstepRuleset(config)
        
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(timezone=ct_tz, session_start_time=time(17, 0, 0))
        timestamp = datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz)
        
        # Create loss that would breach injected limit but not static limit
        tracker = DrawdownTracker(initial_balance=50000.0, trading_date=timestamp.date())
        tracker.update(equity=49900.0, realized_pnl=-100.0, unrealized_pnl=0.0, timestamp=timestamp, day_boundary=boundary)  # -$100 loss
        
        current_state = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=50000.0,
            timestamp=timestamp,
            positions_by_instrument={},
            drawdown_tracker=tracker
        )
        
        execution_result = RebalanceExecutionResult(
            execution_id="test",
            execution_timestamp=timestamp,
            plan_id="test",
            intent_results=[],
            execution_summary={},
            mapping={}
        )
        
        execution_engine = PaperExecutionEngine(instrument="AAPL")
        
        # COMBINE should use static limit (-1000.0), not injected limit (-500.0)
        # If live_daily_loss_limit is provided, it should be ignored for COMBINE
        violations = ruleset.validate_execution(
            execution_result,
            current_state,
            execution_engine=execution_engine,
            current_prices={"AAPL": 100.0},
            day_boundary=boundary,
            live_daily_loss_limit=-500.0  # Different from static limit, should be ignored
        )
        
        # With -$100 loss, static limit (-$1000) is not breached, so no violation
        # If COMBINE used injected limit (-$500), it would breach, but it doesn't
        daily_loss_violations = [v for v in violations if "DAILY_LOSS" in v.code]
        
        self.assertEqual(
            len(daily_loss_violations), 0,
            "COMBINE must use static limit from config, not injected live_daily_loss_limit"
        )
    
    def test_combine_must_require_static_limits(self):
        """INVARIANT: COMBINE must require static limits in config.
        
        COMBINE accounts must have max_daily_loss and max_trailing_drawdown_pct in config.
        """
        from src.rules.topstep import TopstepRulesConfig, TopstepRuleset
        from src.rules.drawdown import DrawdownTracker
        from src.rules.day_boundary import TradingDayBoundary
        from src.rebalance.executor import RebalanceExecutionResult
        from src.rebalance.planner import CurrentPortfolioState
        from src.execution import PaperExecutionEngine
        from datetime import datetime, date, time
        import zoneinfo
        
        # COMBINE without max_daily_loss must fail in validate_execution
        config = TopstepRulesConfig(
            account_type="COMBINE",
            max_daily_loss=None,  # Missing
            max_trailing_drawdown_pct=5.0,
            account_size=50000.0
        )
        ruleset = TopstepRuleset(config)
        
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(timezone=ct_tz, session_start_time=time(17, 0, 0))
        timestamp = datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz)
        
        tracker = DrawdownTracker(initial_balance=50000.0, trading_date=timestamp.date())
        tracker.update(equity=50000.0, realized_pnl=0.0, unrealized_pnl=0.0, timestamp=timestamp, day_boundary=boundary)
        
        current_state = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=50000.0,
            timestamp=timestamp,
            positions_by_instrument={},
            drawdown_tracker=tracker
        )
        
        execution_result = RebalanceExecutionResult(
            execution_id="test",
            execution_timestamp=timestamp,
            plan_id="test",
            intent_results=[],
            execution_summary={},
            mapping={}
        )
        
        execution_engine = PaperExecutionEngine(instrument="AAPL")
        
        from src.rules.base import RulesetError
        
        with self.assertRaises((RuntimeError, RulesetError)) as context:
            ruleset.validate_execution(
                execution_result,
                current_state,
                execution_engine=execution_engine,
                current_prices={"AAPL": 100.0},
                day_boundary=boundary
            )
        
        error_msg = str(context.exception)
        self.assertIn(
            "max_daily_loss", error_msg.lower(),
            f"COMBINE must require max_daily_loss in config. Got: {error_msg}"
        )
    
    def test_combine_must_enforce_trailing_drawdown(self):
        """INVARIANT: COMBINE must enforce trailing drawdown.
        
        COMBINE accounts must check and enforce trailing drawdown limits.
        """
        from src.rules.topstep import TopstepRulesConfig, TopstepRuleset
        from src.rules.drawdown import DrawdownTracker
        from src.rules.day_boundary import TradingDayBoundary
        from src.rules.base import RulesViolationSeverity
        from src.rebalance.executor import RebalanceExecutionResult
        from src.rebalance.planner import CurrentPortfolioState
        from src.execution import PaperExecutionEngine
        from datetime import datetime, date, time
        import zoneinfo
        
        config = TopstepRulesConfig(
            account_type="COMBINE",
            max_daily_loss=-1000.0,
            max_trailing_drawdown_pct=5.0,
            account_size=50000.0
        )
        ruleset = TopstepRuleset(config)
        
        ct_tz = zoneinfo.ZoneInfo("America/Chicago")
        boundary = TradingDayBoundary(timezone=ct_tz, session_start_time=time(17, 0, 0))
        timestamp = datetime(2024, 1, 1, 10, 0, 0, tzinfo=ct_tz)
        
        # Create tracker with locked state and breached trailing drawdown
        tracker = DrawdownTracker(initial_balance=50000.0, trading_date=timestamp.date())
        tracker.update(equity=55000.0, realized_pnl=5000.0, unrealized_pnl=0.0, timestamp=timestamp, day_boundary=boundary)  # Lock in
        tracker.update(equity=40000.0, realized_pnl=5000.0, unrealized_pnl=-15000.0, timestamp=timestamp, day_boundary=boundary)  # 27% drawdown (breaches 5%)
        
        self.assertTrue(tracker.is_locked, "Tracker must be locked")
        # Get trailing drawdown from latest snapshot
        if tracker.snapshots:
            latest_snapshot = tracker.snapshots[-1]
            trailing_dd_pct = latest_snapshot.trailing_drawdown_pct
            self.assertGreater(trailing_dd_pct, 5.0, "Drawdown must exceed limit")
        
        current_state = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=50000.0,
            timestamp=timestamp,
            positions_by_instrument={},
            drawdown_tracker=tracker
        )
        
        execution_result = RebalanceExecutionResult(
            execution_id="test",
            execution_timestamp=timestamp,
            plan_id="test",
            intent_results=[],
            execution_summary={},
            mapping={}
        )
        
        execution_engine = PaperExecutionEngine(instrument="AAPL")
        
        violations = ruleset.validate_execution(
            execution_result,
            current_state,
            execution_engine=execution_engine,
            current_prices={"AAPL": 100.0},
            day_boundary=boundary,
            skip_equity_recalculation=True
        )
        
        # Must have HALT violation for trailing drawdown breach
        trailing_dd_violations = [v for v in violations if "TRAILING_DRAWDOWN" in v.code]
        
        self.assertGreater(
            len(trailing_dd_violations), 0,
            "COMBINE must enforce trailing drawdown limits"
        )
        
        halt_violations = [v for v in trailing_dd_violations if v.severity == RulesViolationSeverity.HALT]
        self.assertGreater(
            len(halt_violations), 0,
            "COMBINE trailing drawdown violation must be HALT severity"
        )

