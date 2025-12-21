"""Demo runner for ruleset violations.

This script demonstrates ruleset validation by triggering WARN and HALT violations.
"""

import json
from pathlib import Path
from datetime import datetime

from .topstep import TopstepRulesConfig, TopstepRuleset
from .base import RulesViolationSeverity


def create_mock_rebalance_plan(total_turnover: float):
    """Create a mock rebalance plan for testing."""
    class MockRebalancePlan:
        def __init__(self, turnover):
            self.metrics = {"total_turnover": turnover}
    
    return MockRebalancePlan(total_turnover)


def create_mock_portfolio_state(total_capital: float):
    """Create a mock portfolio state for testing."""
    from src.rebalance.planner import CurrentPortfolioState
    
    return CurrentPortfolioState(
        strategy_allocations={},
        total_capital=total_capital,
        timestamp=datetime.now()
    )


def create_mock_execution_result():
    """Create a mock execution result for testing."""
    class MockIntentResult:
        def __init__(self, success, fills):
            self.success = success
            self.fills = fills
    
    class MockFill:
        def __init__(self, fee):
            self.fee = fee
    
    class MockExecutionResult:
        def __init__(self):
            self.intent_results = [
                MockIntentResult(True, [MockFill(10.0), MockFill(20.0)]),
            ]
    
    return MockExecutionResult()


def demo_warn_violation():
    """Demonstrate a WARN violation (trailing drawdown rule not implemented)."""
    print("=" * 60)
    print("Demo: WARN Violation")
    print("=" * 60)
    
    config = TopstepRulesConfig(
        max_turnover_pct=50.0,
        account_size=100000.0
    )
    ruleset = TopstepRuleset(config)
    
    plan = create_mock_rebalance_plan(30000.0)  # 30% turnover (within limit)
    state = create_mock_portfolio_state(100000.0)
    
    violations = ruleset.validate_plan(plan, state)
    
    print(f"\nFound {len(violations)} violations:")
    for v in violations:
        print(f"  - [{v.severity.value.upper()}] {v.code}: {v.message}")
        if v.metadata:
            print(f"    Metadata: {v.metadata}")
    
    warn_count = sum(1 for v in violations if v.severity == RulesViolationSeverity.WARN)
    print(f"\nSummary: {warn_count} WARN violations (cycle can continue)")
    print()


def demo_halt_violation():
    """Demonstrate a HALT violation (max turnover exceeded)."""
    print("=" * 60)
    print("Demo: HALT Violation")
    print("=" * 60)
    
    config = TopstepRulesConfig(
        max_turnover_pct=50.0,  # 50% max
        account_size=100000.0
    )
    ruleset = TopstepRuleset(config)
    
    # Create plan with 60% turnover (exceeds 50% limit)
    plan = create_mock_rebalance_plan(60000.0)  # 60% turnover
    state = create_mock_portfolio_state(100000.0)
    
    violations = ruleset.validate_plan(plan, state)
    
    print(f"\nFound {len(violations)} violations:")
    for v in violations:
        print(f"  - [{v.severity.value.upper()}] {v.code}: {v.message}")
        if v.metadata:
            print(f"    Metadata: {json.dumps(v.metadata, indent=6)}")
    
    halt_count = sum(1 for v in violations if v.severity == RulesViolationSeverity.HALT)
    warn_count = sum(1 for v in violations if v.severity == RulesViolationSeverity.WARN)
    
    print(f"\nSummary: {halt_count} HALT violations (cycle must stop)")
    print(f"         {warn_count} WARN violations")
    print()


def main():
    """Run demo violations."""
    print("\nTopstep Ruleset Violation Demo\n")
    
    demo_warn_violation()
    demo_halt_violation()
    
    print("=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

