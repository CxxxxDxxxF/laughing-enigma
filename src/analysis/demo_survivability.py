"""Demo of survivability analysis across multiple cycles."""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.analysis.survivability import analyze_survivability, SurvivabilityMetrics


def create_mock_cycle_result(
    cycle_id: str,
    status: str,
    rules_violations: list,
    ruleset_config: dict,
    rebalance_turnover: float = 0.0,
    total_capital: float = 100000.0
) -> dict:
    """Create a mock cycle result for testing."""
    return {
        "cycle_id": cycle_id,
        "cycle_timestamp": datetime.now().isoformat(),
        "portfolio_id": "demo_portfolio",
        "status": status,
        "rules_violations": rules_violations,
        "ruleset_config": ruleset_config,
        "summary": {
            "rebalance_summary": {
                "total_turnover": rebalance_turnover,
            },
            "allocation_summary": {
                "total_capital": total_capital,
            },
        }
    }


def main():
    """Run survivability analysis demo."""
    print("=" * 70)
    print("Survivability Analysis Demo")
    print("=" * 70)
    
    # Create mock cycle results simulating a strategy that gradually approaches limits
    ruleset_config = {
        "max_daily_loss": -5000.0,
        "max_trailing_drawdown_pct": 5.0,
        "max_turnover_pct": 50.0,
    }
    
    cycles = []
    
    # Cycle 1: Clean run, no violations
    cycles.append(create_mock_cycle_result(
        "cycle_1",
        "completed",
        [],
        ruleset_config,
        rebalance_turnover=10000.0,
        total_capital=100000.0
    ))
    
    # Cycle 2: Small daily loss (60% of limit)
    cycles.append(create_mock_cycle_result(
        "cycle_2",
        "completed",
        [{
            "code": "TOPSTEP_DAILY_LOSS_WARNING",
            "severity": "warn",
            "metadata": {
                "daily_loss": -3000.0,
                "equity": 97000.0,
                "initial_balance": 100000.0,
            }
        }],
        ruleset_config,
        rebalance_turnover=15000.0,
        total_capital=100000.0
    ))
    
    # Cycle 3: Higher trailing drawdown proximity (80% of limit)
    cycles.append(create_mock_cycle_result(
        "cycle_3",
        "completed",
        [{
            "code": "TOPSTEP_TRAILING_DRAWDOWN_WARNING",
            "severity": "warn",
            "metadata": {
                "trailing_drawdown_pct": 4.0,
                "equity": 101000.0,
                "initial_balance": 100000.0,
            }
        }],
        ruleset_config,
        rebalance_turnover=20000.0,
        total_capital=100000.0
    ))
    
    # Cycle 4: Near limit on daily loss (90% of limit)
    cycles.append(create_mock_cycle_result(
        "cycle_4",
        "completed",
        [{
            "code": "TOPSTEP_DAILY_LOSS_WARNING",
            "severity": "warn",
            "metadata": {
                "daily_loss": -4500.0,
                "equity": 95500.0,
                "initial_balance": 100000.0,
            }
        }],
        ruleset_config,
        rebalance_turnover=18000.0,
        total_capital=100000.0
    ))
    
    # Cycle 5: High turnover pressure (80% of limit)
    cycles.append(create_mock_cycle_result(
        "cycle_5",
        "completed",
        [],
        ruleset_config,
        rebalance_turnover=40000.0,  # 40% turnover = 80% of 50% limit
        total_capital=100000.0
    ))
    
    # Cycle 6: HALT - trailing drawdown exceeded
    cycles.append(create_mock_cycle_result(
        "cycle_6",
        "halted",
        [{
            "code": "TOPSTEP_MAX_TRAILING_DRAWDOWN_EXCEEDED",
            "severity": "halt",
            "metadata": {
                "trailing_drawdown_pct": 5.5,
                "equity": 99450.0,
                "initial_balance": 100000.0,
            }
        }],
        ruleset_config,
        rebalance_turnover=12000.0,
        total_capital=100000.0
    ))
    
    # Analyze survivability
    metrics = analyze_survivability(cycles)
    
    print(f"\nAnalyzed {metrics.total_cycles} cycles")
    print(f"  Completed: {metrics.completed_cycles}")
    print(f"  Halted: {metrics.halted_cycles}")
    
    print(f"\nViolations:")
    print(f"  Total: {metrics.total_violations}")
    print(f"  HALT: {metrics.halt_violations}")
    print(f"  WARN: {metrics.warn_violations}")
    print(f"  WARN-only cycles: {metrics.warn_only_cycles}")
    
    print(f"\nDaily Loss Utilization:")
    if metrics.daily_loss_utilization_avg is not None:
        print(f"  Average: {metrics.daily_loss_utilization_avg:.2%}")
        print(f"  Max: {metrics.daily_loss_utilization_max:.2%}")
        print(f"  90th percentile: {metrics.daily_loss_utilization_p90:.2%}")
    else:
        print("  No data available")
    
    print(f"\nTrailing Drawdown Proximity:")
    if metrics.trailing_drawdown_proximity_avg is not None:
        print(f"  Average: {metrics.trailing_drawdown_proximity_avg:.2%}")
        print(f"  Max: {metrics.trailing_drawdown_proximity_max:.2%}")
        if metrics.min_distance_to_drawdown_violation is not None:
            print(f"  Min distance to violation: {metrics.min_distance_to_drawdown_violation:.2%}")
    else:
        print("  No data available")
    
    print(f"\nTurnover Pressure:")
    if metrics.turnover_pressure_avg is not None:
        print(f"  Average: {metrics.turnover_pressure_avg:.2%}")
        print(f"  Max: {metrics.turnover_pressure_max:.2%}")
    else:
        print("  No data available")
    
    print(f"\nSurvival Metrics:")
    print(f"  Days survived: {metrics.days_survived if metrics.days_survived is not None else 'N/A'}")
    print(f"  Max violation-free streak: {metrics.violation_free_streak_max}")
    print(f"  Current violation-free streak: {metrics.violation_free_streak_current}")
    
    print(f"\nSurvivability Summary (JSON):")
    print(json.dumps(metrics.to_dict(), indent=2))
    
    print("\n" + "=" * 70)
    print("Demo Complete")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

