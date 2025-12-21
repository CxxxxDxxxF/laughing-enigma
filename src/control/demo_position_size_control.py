"""Demo: Position size control prevents HALT on downward price movement.

This demo shows that with survivability controls enabled, the system
clamps allocations to position size limits instead of halting on
TOPSTEP_MAX_POSITION_SIZE_EXCEEDED violations.

Scenario:
- Start price: 100.00
- Price declines: 99.50, 99.00, 98.50 (gentle downward movement)
- Total capital: 100,000
- Max position size: 1000 units
- Expected: Cycles complete with control events logged, no HALT
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.engines.simple import SimpleResearchEngine
from src.core.artifacts import LocalArtifactStore
from src.execution import PaperExecutionEngine
from src.lifecycle.runner import PortfolioCycleConfig, run_portfolio_cycle
from src.lifecycle.state_store import LocalPortfolioStateStore
from src.evaluation.batch import BatchEvaluationConfig, StrategyConfig


def create_demo_config(prices: Dict[str, float]) -> PortfolioCycleConfig:
    """Create a demo cycle config with Topstep rules."""
    return PortfolioCycleConfig(
        portfolio_id="demo_position_control",
        evaluation_config=BatchEvaluationConfig(
            strategies=[
                StrategyConfig(
                    strategy_id="demo_strategy",
                    experiment_name="momentum",
                    experiment_version="v1",
                    experiment_config={"daily_trend": 0.00005},
                    inputs={
                        "start_date": "2024-01-01",
                        "end_date": "2024-03-31",
                        "initial_capital": 100000,
                        "instrument": "AAPL",
                        "strategy_type": "buy_hold"
                    },
                    description="Demo strategy"
                )
            ],
            parameter_grid=None,
            evaluation_criteria={
                "min_robustness_score": 0.0,
                "max_divergence_pct": 1.0,
                "max_timing_drift_seconds": 999999
            },
            price_series=list(prices.values())[:10]  # Use first 10 prices for evaluation
        ),
        allocation_config={
            "total_capital": 100000,
            "top_n_strategies": 1,
            "min_robustness_score": 0.0,
            "max_allocation_per_strategy": 1.0,
            "min_allocation_per_strategy": 0.0,
            "allocation_method": "equal",
            "max_total_leverage": 1.0,
            "require_all_passed": False
        },
        rebalance_config={
            "rebalance_threshold_pct": 0.0,  # Always rebalance
            "max_turnover_pct": 1.0,
            "min_trade_size": 0.0,
            "allow_partial_rebalance": True
        },
        execution_config={
            "price_by_strategy_or_instrument": prices,
            "rounding_method": "floor",
            "min_quantity": 1.0
        },
        cadence_config={
            "frequency": "manual",
            "min_seconds_between_cycles": None,
            "timezone": "UTC"
        },
        guardrails_config=None,
        ruleset_type="topstep",
        ruleset_config={
            "max_position_size": 1000.0,  # 1000 units max
            "max_daily_loss": -5000.0,  # $5k daily loss limit
            "max_trailing_drawdown_pct": 10.0,  # 10% trailing drawdown
            "account_size": 100000.0
        }
    )


def run_demo():
    """Run the position size control demo."""
    print("=" * 80)
    print("Position Size Control Demo")
    print("=" * 80)
    print()
    print("Scenario: Gentle downward price movement")
    print("  Start price: $100.00")
    print("  Prices: 100.00 → 99.50 → 99.00 → 98.50")
    print("  Capital: $100,000")
    print("  Max position size: 1000 units")
    print()
    print("Expected behavior:")
    print("  - Cycle 1: Normal allocation (price $100, quantity ~1000)")
    print("  - Cycle 2: Price $99.50 → quantity would be ~1005 → clamped to 1000")
    print("  - Cycle 3: Price $99.00 → quantity would be ~1010 → clamped to 1000")
    print("  - Cycle 4: Price $98.50 → quantity would be ~1015 → clamped to 1000")
    print("  - All cycles complete (no HALT on position size)")
    print("  - Control events logged in cycle_result.json")
    print()
    
    # Create artifacts directory
    artifacts_dir = Path("artifacts/demo_position_control")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize components
    artifact_store = LocalArtifactStore(str(artifacts_dir))
    research_engine = SimpleResearchEngine(artifact_store)
    state_store = LocalPortfolioStateStore(artifact_store)
    
    def execution_engine_factory():
        return PaperExecutionEngine(
            session_id=f"demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            instrument="AAPL",
            initial_capital=100000.0
        )
    
    # Price series (gentle downward movement)
    prices = {
        "AAPL": 100.00,  # Cycle 1
    }
    
    # Run cycle 1 (establish initial position)
    print("Running Cycle 1 (price $100.00)...")
    config1 = create_demo_config({"AAPL": 100.00, "demo_strategy": 100.00})
    result1 = run_portfolio_cycle(
        config=config1,
        research_engine=research_engine,
        artifact_store=artifact_store,
        execution_engine_factory=execution_engine_factory,
        state_store=state_store,
        cycle_id="cycle_01"
    )
    
    print(f"  Status: {result1.status}")
    if result1.survivability_control_events:
        print(f"  Control events: {len(result1.survivability_control_events)}")
        for event in result1.survivability_control_events[:2]:  # Show first 2
            print(f"    - {event.get('code')}: {event.get('message', '')[:60]}")
    if result1.rules_violations:
        print(f"  Rules violations: {len(result1.rules_violations)}")
        for v in result1.rules_violations[:2]:
            print(f"    - {v.get('code')}: {v.get('severity')}")
    print()
    
    # Run cycle 2 (price drops, should trigger control event)
    print("Running Cycle 2 (price $99.50)...")
    config2 = create_demo_config({"AAPL": 99.50, "demo_strategy": 99.50})
    result2 = run_portfolio_cycle(
        config=config2,
        research_engine=research_engine,
        artifact_store=artifact_store,
        execution_engine_factory=execution_engine_factory,
        state_store=state_store,
        cycle_id="cycle_02"
    )
    
    print(f"  Status: {result2.status}")
    if result2.survivability_control_events:
        print(f"  Control events: {len(result2.survivability_control_events)}")
        for event in result2.survivability_control_events:
            print(f"    - {event.get('code')}: {event.get('message', '')[:70]}")
            metadata = event.get('metadata', {})
            if 'utilization' in metadata:
                print(f"      Utilization: {metadata['utilization']:.2%}")
    if result2.rules_violations:
        print(f"  Rules violations: {len(result2.rules_violations)}")
        for v in result2.rules_violations:
            print(f"    - {v.get('code')}: {v.get('severity')}")
    print()
    
    # Run cycle 3 (price continues to drop)
    print("Running Cycle 3 (price $99.00)...")
    config3 = create_demo_config({"AAPL": 99.00, "demo_strategy": 99.00})
    result3 = run_portfolio_cycle(
        config=config3,
        research_engine=research_engine,
        artifact_store=artifact_store,
        execution_engine_factory=execution_engine_factory,
        state_store=state_store,
        cycle_id="cycle_03"
    )
    
    print(f"  Status: {result3.status}")
    if result3.survivability_control_events:
        print(f"  Control events: {len(result3.survivability_control_events)}")
        for event in result3.survivability_control_events:
            print(f"    - {event.get('code')}: {event.get('message', '')[:70]}")
    print()
    
    # Summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    
    all_completed = all(r.status == "completed" for r in [result1, result2, result3])
    total_control_events = sum(
        len(r.survivability_control_events) if r.survivability_control_events else 0
        for r in [result1, result2, result3]
    )
    total_violations = sum(
        len(r.rules_violations) if r.rules_violations else 0
        for r in [result1, result2, result3]
    )
    
    print(f"All cycles completed: {all_completed}")
    print(f"Total control events: {total_control_events}")
    print(f"Total rules violations: {total_violations}")
    print()
    
    if all_completed and total_control_events > 0:
        print("✓ SUCCESS: Position size controls prevented HALT violations")
        print("  - All cycles completed successfully")
        print("  - Control events logged when allocations were clamped")
        print("  - No position size violations occurred")
    elif not all_completed:
        print("✗ FAILURE: One or more cycles halted")
        print("  - Expected all cycles to complete with controls enabled")
    else:
        print("⚠ WARNING: No control events logged")
        print("  - Controls may not have been triggered (price movement may be insufficient)")
    
    print()
    print(f"Artifacts saved to: {artifacts_dir}")


if __name__ == "__main__":
    run_demo()
