"""Demo of state continuity: drawdown tracker persists across cycles.

This script:
1. Runs cycle 1 that locks tracker (equity > initial)
2. Runs cycle 2 that uses persisted state and triggers trailing drawdown HALT

Verifies that tracker is loaded from portfolio state and not reinitialized.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, date

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.lifecycle.runner import PortfolioCycleConfig, run_portfolio_cycle
from src.core.artifacts import LocalArtifactStore
from src.lifecycle.state_store import LocalPortfolioStateStore
from src.engines.simple import SimpleResearchEngine
from src.execution import PaperExecutionEngine


def create_cycle_config(portfolio_id: str, total_capital: float, price: float):
    """Create a cycle config for testing."""
    from src.evaluation.batch import BatchEvaluationConfig, StrategyConfig
    from src.allocation.allocator import AllocationConfig
    from src.rebalance.planner import RebalanceConfig
    from src.rules import TopstepRulesConfig
    
    return PortfolioCycleConfig(
        portfolio_id=portfolio_id,
        evaluation_config=BatchEvaluationConfig(
            strategies=[
                StrategyConfig(
                    strategy_id="test_strategy",
                    experiment_name="momentum",
                    experiment_version="v1",
                    experiment_config={"daily_trend": 0.00005},
                    inputs={
                        "start_date": "2024-01-01",
                        "end_date": "2024-03-31",
                        "initial_capital": total_capital,
                        "instrument": "AAPL",
                        "strategy_type": "buy_hold"
                    },
                    description="Test strategy"
                )
            ],
            parameter_grid=None,
            evaluation_criteria={
                "min_robustness_score": 0.0,
                "max_divergence_pct": 1.0,
                "max_timing_drift_seconds": 999999
            },
            price_series=[150, 151, 152, 153, 154, 155, 156, 157, 158, 159]
        ),
        allocation_config=AllocationConfig(
            total_capital=total_capital,
            top_n_strategies=1,
            allocation_method="equal"
        ),
        rebalance_config=RebalanceConfig(
            rebalance_threshold_pct=0.0,
            max_turnover_pct=1.0
        ),
        execution_config={
            "price_by_strategy_or_instrument": {
                "test_strategy": price,
                "AAPL": price
            },
            "rounding_method": "floor",
            "min_quantity": 1.0
        },
        ruleset_type="topstep",
        ruleset_config={
            "max_turnover_pct": 100.0,
            "max_position_size": 10000.0,
            "max_daily_loss": -10000.0,
            "max_trailing_drawdown_pct": 3.0,  # 3% max trailing drawdown
            "account_size": total_capital
        }
    )


def main():
    """Run two-cycle demo."""
    print("=" * 70)
    print("Two-Cycle Drawdown Tracker Continuity Demo")
    print("=" * 70)
    
    portfolio_id = "test_drawdown_continuity"
    total_capital = 100000.0
    
    # Clean up any existing artifacts
    artifacts_dir = Path("./artifacts_test_continuity")
    if artifacts_dir.exists():
        import shutil
        shutil.rmtree(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    artifact_store = LocalArtifactStore(artifacts_dir)
    state_store = LocalPortfolioStateStore(artifact_store)
    research_engine = SimpleResearchEngine(artifact_store=artifact_store)
    
    def create_engine():
        return PaperExecutionEngine(instrument="AAPL", artifact_store=artifact_store)
    
    # Cycle 1: Lock the tracker (equity > initial)
    print("\n" + "=" * 70)
    print("CYCLE 1: Lock Tracker (Equity Exceeds Initial)")
    print("=" * 70)
    
    # Use a high price so execution creates a position with profit
    # This will make equity > initial balance, locking the tracker
    config_1 = create_cycle_config(portfolio_id, total_capital, price=155.0)
    
    result_1 = run_portfolio_cycle(
        config=config_1,
        research_engine=research_engine,
        artifact_store=artifact_store,
        execution_engine_factory=create_engine,
        state_store=state_store
    )
    
    print(f"\nCycle 1 Status: {result_1.status}")
    print(f"State After ID: {result_1.state_after_id}")
    
    # Load the state after cycle 1
    if result_1.state_after_id:
        state_after_1 = state_store._load_state(portfolio_id, result_1.state_after_id)
        if state_after_1.drawdown_tracker:
            print(f"\nTracker After Cycle 1:")
            print(f"  Initial Balance: ${state_after_1.drawdown_tracker.initial_balance:,.2f}")
            print(f"  High-Water Mark: ${state_after_1.drawdown_tracker.high_water_mark:,.2f}")
            print(f"  Is Locked: {state_after_1.drawdown_tracker.is_locked}")
            if state_after_1.drawdown_tracker.snapshots:
                latest = state_after_1.drawdown_tracker.snapshots[-1]
                print(f"  Latest Equity: ${latest.equity:,.2f}")
                print(f"  Latest Trailing Drawdown: {latest.trailing_drawdown_pct:.2f}%")
        else:
            print("\n⚠ WARNING: No drawdown tracker in state after cycle 1!")
    
    # Cycle 2: Trigger trailing drawdown HALT using persisted state
    print("\n" + "=" * 70)
    print("CYCLE 2: Trigger Trailing Drawdown HALT (Using Persisted State)")
    print("=" * 70)
    
    # Use a lower price to create a drawdown from the high-water mark
    # If high-water mark was ~$105k and we use price that gives ~$101k equity,
    # we get ~$4k drawdown = ~3.8% which exceeds 3% limit
    config_2 = create_cycle_config(portfolio_id, total_capital, price=148.0)
    
    result_2 = run_portfolio_cycle(
        config=config_2,
        research_engine=research_engine,
        artifact_store=artifact_store,
        execution_engine_factory=create_engine,
        state_store=state_store
    )
    
    print(f"\nCycle 2 Status: {result_2.status}")
    print(f"State After ID: {result_2.state_after_id}")
    print(f"Skip Reason: {result_2.skip_reason}")
    
    print(f"\nRules Violations: {len(result_2.rules_violations)}")
    for v in result_2.rules_violations:
        print(f"  [{v['severity']}] {v['code']}: {v['message']}")
    
    # Verify expectations
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)
    
    if result_1.state_after_id and result_1.status == "completed":
        state_after_1 = state_store._load_state(portfolio_id, result_1.state_after_id)
        if state_after_1.drawdown_tracker and state_after_1.drawdown_tracker.is_locked:
            print("✓ Cycle 1: Tracker locked successfully")
        else:
            print("✗ Cycle 1: Tracker not locked (may need price adjustment)")
    
    if result_2.status == "halted":
        halt_violations = [v for v in result_2.rules_violations if v['severity'] == 'halt']
        if any('TRAILING_DRAWDOWN' in v['code'] for v in halt_violations):
            print("✓ Cycle 2: Trailing drawdown HALT triggered")
        else:
            print("⚠ Cycle 2: HALT occurred but not from trailing drawdown")
    else:
        print("⚠ Cycle 2: Expected HALT but got status:", result_2.status)
    
    if result_2.state_after_id is None and result_2.status == "halted":
        print("✓ Cycle 2: state_after_id is None (correct for halted cycle)")
    elif result_2.status == "halted":
        print("⚠ Cycle 2: state_after_id is set but status is halted (may be incorrect)")
    
    print("\n" + "=" * 70)
    print("Demo Complete")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

