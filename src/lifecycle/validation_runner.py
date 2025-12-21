"""Validation runner for Phase 15 survivability analysis.

This script runs 20-30 consecutive portfolio cycles with:
- Frozen configuration (no mid-run changes)
- Deterministic day advancement (synthetic days)
- Sequential state carry-forward
- All outcomes captured (completed/skipped/halted)

After cycles complete, runs survivability analysis and outputs observations.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .runner import (
    PortfolioCycleConfig,
    CycleResult,
    run_portfolio_cycle,
    persist_cycle_result,
)
from .state_store import LocalPortfolioStateStore
from ..core.artifacts import LocalArtifactStore, ArtifactStore
from ..engines.simple import SimpleResearchEngine
from ..execution import PaperExecutionEngine
from ..analysis.survivability import analyze_survivability, SurvivabilityMetrics


def load_frozen_config(config_path: Path) -> PortfolioCycleConfig:
    """Load frozen validation config.
    
    Args:
        config_path: Path to validation_cycle.json
        
    Returns:
        PortfolioCycleConfig instance
    """
    config = PortfolioCycleConfig.from_json_file(config_path)
    
    # Verify config is suitable for validation
    if config.portfolio_id != "validation_portfolio":
        print(f"WARNING: portfolio_id is {config.portfolio_id}, expected 'validation_portfolio'")
    
    return config


def generate_price_series_scenario_a(start_price: float = 100.0, num_days: int = 30, daily_change_pct: float = -0.30) -> List[float]:
    """Generate Scenario A: Gentle downward grind price series.
    
    Args:
        start_price: Starting price (default: 100.0)
        num_days: Number of days (default: 30)
        daily_change_pct: Daily percentage change (default: -0.30%)
        
    Returns:
        List of prices, one per day
    """
    prices = []
    current_price = start_price
    
    for day in range(num_days):
        prices.append(current_price)
        # Apply daily change: new_price = current_price * (1 + daily_change_pct / 100)
        current_price = current_price * (1.0 + daily_change_pct / 100.0)
    
    return prices


def generate_price_series_scenario_lock_in_activation(start_price: float = 100.0, num_days: int = 30) -> List[float]:
    """Generate price series for Class 2 validation: Drawdown Lock-In Activation.
    
    Pattern:
    - First 5-8 cycles: Gentle upward drift (ensure equity exceeds initial balance to lock drawdown)
    - Remaining cycles: Choppy sideways/down movement (create drawdown but stay within limits)
    
    This scenario is designed to:
    1. Trigger drawdown tracker lock-in (equity > initial balance)
    2. Create trailing drawdown from high-water mark
    3. Stay safely within drawdown and daily loss limits
    
    Args:
        start_price: Starting price (default: 100.0)
        num_days: Number of days (default: 30)
        
    Returns:
        List of prices, one per day (deterministic)
    """
    prices = []
    current_price = start_price
    
    # Phase 1: Gentle upward drift (cycles 1-7, ~2% total gain)
    # Daily changes: +0.15%, +0.20%, +0.25%, +0.30%, +0.35%, +0.40%, +0.35%
    upward_pattern = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.35]  # Percentage changes
    
    for day in range(min(7, num_days)):
        prices.append(current_price)
        daily_change_pct = upward_pattern[day % len(upward_pattern)]
        current_price = current_price * (1.0 + daily_change_pct / 100.0)
    
    # Phase 2: Choppy sideways/down movement (remaining cycles)
    # Pattern: small up/down movements that create drawdown from high-water mark
    # but stay within reasonable limits (not too steep)
    # Pattern: -0.2%, +0.1%, -0.3%, +0.2%, -0.25%, +0.15%, -0.2%, +0.1%
    choppy_pattern = [-0.2, +0.1, -0.3, +0.2, -0.25, +0.15, -0.2, +0.1]  # Percentage changes
    
    for day in range(7, num_days):
        prices.append(current_price)
        pattern_index = (day - 7) % len(choppy_pattern)
        daily_change_pct = choppy_pattern[pattern_index]
        current_price = current_price * (1.0 + daily_change_pct / 100.0)
    
    return prices


def generate_price_series_scenario_choppy_downward(start_price: float = 100.0, num_days: int = 30) -> List[float]:
    """Generate choppy downward price series with repeating 4-day pattern.
    
    Pattern repeats every 4 days:
    - Day 1: -0.5%
    - Day 2: +0.3%
    - Day 3: -0.6%
    - Day 4: +0.2%
    
    Net direction: downward (over 4 days: -0.5% + 0.3% - 0.6% + 0.2% = -0.6%)
    
    Args:
        start_price: Starting price (default: 100.0)
        num_days: Number of days (default: 30)
        
    Returns:
        List of prices, one per day (deterministic)
    """
    prices = []
    current_price = start_price
    
    # 4-day pattern: [day_1_change, day_2_change, day_3_change, day_4_change] in percentage
    pattern = [-0.5, +0.3, -0.6, +0.2]  # Percentage changes
    
    for day in range(num_days):
        prices.append(current_price)
        
        # Get pattern index (0, 1, 2, 3, 0, 1, 2, 3, ...)
        pattern_index = day % len(pattern)
        daily_change_pct = pattern[pattern_index]
        
        # Apply daily change: new_price = current_price * (1 + daily_change_pct / 100)
        current_price = current_price * (1.0 + daily_change_pct / 100.0)
    
    return prices


def advance_price_deterministic(price_series: List[float], day: int) -> float:
    """Get price from deterministic price series for a given day.
    
    Args:
        price_series: Pre-generated price series
        day: Day number (1, 2, 3, ...)
        
    Returns:
        Price for this day (repeats last value if day exceeds series length)
    """
    day_index = day - 1  # Convert to 0-based index
    if day_index < len(price_series):
        return price_series[day_index]
    else:
        # Repeat last value for days beyond series
        return price_series[-1] if price_series else 100.0


def update_config_for_day(
    config: PortfolioCycleConfig, 
    day: int, 
    current_price: float,
    enable_hold_quantity: bool = False
) -> PortfolioCycleConfig:
    """Update config with new day's timestamp, prices, and hold-quantity mode.
    
    Args:
        config: Base frozen config
        day: Day number (1, 2, 3, ...)
        current_price: Price for this day
        enable_hold_quantity: Whether to enable hold-quantity mode (cycles 2+)
        
    Returns:
        Updated config (new instance, doesn't modify original)
    """
    # Create new execution config with updated price
    new_execution_config = config.execution_config.copy()
    new_execution_config["price_by_strategy_or_instrument"] = {
        "validation_strategy_v1": current_price,
        "AAPL": current_price
    }
    
    # Create new config dict
    config_dict = config.to_dict()
    config_dict["execution_config"] = new_execution_config
    
    # Set hold-quantity validation mode (cycle 1 = bootstrap, cycles 2+ = hold quantity)
    config_dict["validation_hold_quantity"] = enable_hold_quantity
    config_dict["validation_bootstrap_first_cycle"] = True  # Always bootstrap cycle 1
    
    # Reload as PortfolioCycleConfig (preserves all other fields)
    return PortfolioCycleConfig.from_dict(config_dict)


def load_cycle_results(artifact_store: LocalArtifactStore, cycle_ids: List[str]) -> List[Dict[str, Any]]:
    """Load cycle results from artifact store.
    
    Args:
        artifact_store: Artifact store instance
        cycle_ids: List of cycle IDs to load
        
    Returns:
        List of cycle result dicts (in order)
    """
    results = []
    
    for cycle_id in cycle_ids:
        try:
            result_data = artifact_store.retrieve(cycle_id, "cycle_result.json")
            if result_data:
                result_dict = json.loads(result_data.decode('utf-8'))
                results.append(result_dict)
            else:
                print(f"WARNING: No cycle_result.json found for {cycle_id}")
        except Exception as e:
            print(f"ERROR: Failed to load cycle {cycle_id}: {e}")
            import traceback
            traceback.print_exc()
    
    return results


def persist_survivability_metrics(metrics: SurvivabilityMetrics, artifact_store: LocalArtifactStore):
    """Persist survivability metrics to artifact store.
    
    Args:
        metrics: SurvivabilityMetrics instance
        artifact_store: Artifact store instance
    """
    try:
        metrics_dict = metrics.to_dict()
        metrics_json = json.dumps(metrics_dict, indent=2).encode('utf-8')
        artifact_store.store("validation", "survivability_metrics.json", metrics_json)
        print(f"Survivability metrics persisted to artifacts/validation/survivability_metrics.json")
    except Exception as e:
        print(f"WARNING: Failed to persist survivability metrics: {e}")


def run_full_validation(
    config_path: Path,
    artifacts_dir: Path,
    num_cycles: int = 30,
    scenario: str = "gentle_downward"
) -> SurvivabilityMetrics:
    """Run full validation: cycles + survivability analysis.
    
    This is the main entry point for Phase 15 validation.
    
    Args:
        config_path: Path to frozen validation config
        artifacts_dir: Directory for artifacts
        num_cycles: Number of cycles to run (default: 30)
        scenario: Price scenario ("gentle_downward" for Scenario A)
        
    Returns:
        SurvivabilityMetrics from analysis
    """
    # Step 1: Run validation cycles
    cycle_ids = run_validation(
        config_path=config_path,
        artifacts_dir=artifacts_dir,
        num_cycles=num_cycles,
        scenario=scenario
    )
    
    if not cycle_ids:
        print("ERROR: No cycles were executed")
        return SurvivabilityMetrics(total_cycles=0)
    
    # Step 2: Load all cycle results
    artifact_store = LocalArtifactStore(artifacts_dir)
    print(f"\nLoading {len(cycle_ids)} cycle results for analysis...")
    cycle_results = load_cycle_results(artifact_store, cycle_ids)
    
    if not cycle_results:
        print("ERROR: Failed to load any cycle results")
        return SurvivabilityMetrics(total_cycles=0)
    
    print(f"Loaded {len(cycle_results)} cycle results")
    print()
    
    # Step 3: Run survivability analysis
    print("Running survivability analysis...")
    # Pass state_store to enable snapshot-based proximity metrics
    state_store = LocalPortfolioStateStore(artifact_store)
    metrics = analyze_survivability(cycle_results, artifact_store=artifact_store, state_store=state_store)
    print("Analysis complete")
    print()
    
    # Step 4: Persist metrics
    persist_survivability_metrics(metrics, artifact_store)
    print()
    
    # Step 5: Print summary
    print_survivability_summary(metrics)
    
    return metrics


def run_validation(
    config_path: Path,
    artifacts_dir: Path,
    num_cycles: int = 30,
    scenario: str = "gentle_downward"
) -> List[str]:
    """Run validation cycles sequentially with hold-quantity mode.
    
    Cycle 1: Bootstrap normally (establishes position)
    Cycles 2-30: Hold-quantity validation mode (mark-to-market only, no rebalancing)
    
    Args:
        config_path: Path to frozen validation config
        artifacts_dir: Directory for artifacts
        num_cycles: Number of cycles to run (default: 30)
        scenario: Price scenario ("gentle_downward" for Scenario A)
        
    Returns:
        List of cycle IDs that were executed
    """
    print("=" * 70)
    print("Phase 15 Validation Run (Hold-Quantity Mode)")
    print("=" * 70)
    print(f"Config: {config_path}")
    print(f"Artifacts: {artifacts_dir}")
    print(f"Cycles: {num_cycles}")
    print(f"Scenario: {scenario}")
    print("=" * 70)
    print()
    
    # Load frozen config
    base_config = load_frozen_config(config_path)
    
    # Generate price series based on scenario
    if scenario == "gentle_downward":
        # Scenario A: Gentle downward grind
        # Start: 100.00, Daily: -0.30%, Length: 30 days
        price_series = generate_price_series_scenario_a(start_price=100.0, num_days=num_cycles, daily_change_pct=-0.30)
        print(f"Price series: Scenario A (Gentle downward grind)")
        print(f"  Start: ${price_series[0]:.2f}")
        print(f"  Daily change: -0.30%")
        print(f"  End (day {num_cycles}): ${price_series[-1]:.2f}")
    elif scenario == "choppy_downward":
        # Choppy downward: 4-day repeating pattern with net downward direction
        price_series = generate_price_series_scenario_choppy_downward(start_price=100.0, num_days=num_cycles)
        print(f"Price series: Choppy downward (4-day repeating pattern)")
        print(f"  Start: ${price_series[0]:.2f}")
        print(f"  Pattern: -0.5%, +0.3%, -0.6%, +0.2% (repeats)")
        print(f"  End (day {num_cycles}): ${price_series[-1]:.2f}")
    elif scenario == "lock_in_activation":
        # Class 2: Drawdown lock-in activation
        # First 7 cycles: upward drift, then choppy sideways/down
        price_series = generate_price_series_scenario_lock_in_activation(start_price=100.0, num_days=num_cycles)
        print(f"Price series: Lock-in activation (Class 2 validation)")
        print(f"  Start: ${price_series[0]:.2f}")
        print(f"  Phase 1 (cycles 1-7): Gentle upward drift (~2% gain)")
        print(f"  Phase 2 (cycles 8+): Choppy sideways/down movement")
        print(f"  Peak: ${max(price_series):.2f} (cycle {price_series.index(max(price_series)) + 1})")
        print(f"  End (day {num_cycles}): ${price_series[-1]:.2f}")
    else:
        raise ValueError(f"Unknown scenario: {scenario}")
    
    print()
    
    # Initialize components
    artifact_store = LocalArtifactStore(artifacts_dir)
    research_engine = SimpleResearchEngine(artifact_store=artifact_store)
    state_store = LocalPortfolioStateStore(artifact_store)
    
    # Create execution engine factory
    instrument = "AAPL"
    def create_engine():
        return PaperExecutionEngine(
            instrument=instrument,
            artifact_store=artifact_store
        )
    
    # Track cycles
    cycle_ids: List[str] = []
    first_cycle_timestamp = datetime(2024, 1, 2, 0, 0, 0)  # Start Jan 2, 2024
    
    print(f"Starting validation run...")
    print(f"First cycle timestamp: {first_cycle_timestamp.isoformat()}")
    print(f"Cycle 1: Bootstrap (normal execution)")
    print(f"Cycles 2-{num_cycles}: Hold-quantity mode (mark-to-market validation only)")
    print()
    
    # Run cycles sequentially
    for day in range(1, num_cycles + 1):
        print(f"--- Cycle {day}/{num_cycles} ---")
        
        # Get price for this day from pre-generated series
        current_price = advance_price_deterministic(price_series, day)
        print(f"Price for day {day}: ${current_price:.2f}")
        
        # Enable hold-quantity mode for cycles 2+
        enable_hold_quantity = (day > 1)
        if enable_hold_quantity:
            print(f"Mode: Hold-quantity validation (mark-to-market only)")
        
        # Update config for this day with hold-quantity mode
        day_config = update_config_for_day(
            base_config, 
            day, 
            current_price,
            enable_hold_quantity=enable_hold_quantity
        )
        
        # Calculate cycle timestamp (advance by 1 day per cycle)
        cycle_timestamp = first_cycle_timestamp + timedelta(days=day - 1)
        
        try:
            # Generate unique cycle_id for this day
            unique_cycle_id = f"cycle_day{day:02d}_{cycle_timestamp.strftime('%Y%m%d_%H%M%S')}"
            
            # Run cycle (hold-quantity mode is set in config)
            result = run_portfolio_cycle(
                config=day_config,
                research_engine=research_engine,
                artifact_store=artifact_store,
                execution_engine_factory=create_engine,
                state_store=state_store,
                cycle_id=unique_cycle_id  # Pass unique cycle_id
            )
            
            # Persist result (uses cycle_id from result)
            cycle_id = persist_cycle_result(result, artifact_store)
            cycle_ids.append(cycle_id)
            
            print(f"Cycle ID: {cycle_id}")
            print(f"Status: {result.status}")
            if result.status != "completed":
                print(f"Reason: {result.skip_reason}")
            if result.rules_violations:
                print(f"Violations: {len(result.rules_violations)}")
                for v in result.rules_violations[:2]:  # Show first 2
                    if isinstance(v, dict):
                        severity = v.get('severity', 'unknown')
                        code = v.get('code', 'unknown')
                    else:
                        severity = getattr(v, 'severity', 'unknown')
                        code = getattr(v, 'code', 'unknown')
                    print(f"  - {severity}: {code}")
            
            print()
            
            # Stop early if halted (validation still succeeds)
            if result.status == "halted":
                print(f"HALT detected at cycle {day}. Stopping early.")
                print(f"Days survived: {day - 1}")
                break
                
        except Exception as e:
            print(f"ERROR in cycle {day}: {e}")
            import traceback
            traceback.print_exc()
            print("Continuing to next cycle...")
            print()
            continue
    
    print(f"Validation run complete. Executed {len(cycle_ids)} cycles.")
    print()
    
    return cycle_ids


def analyze_validation_results(
    cycle_results: List[Dict[str, Any]]
) -> SurvivabilityMetrics:
    """Analyze validation cycle results.
    
    Args:
        cycle_results: List of cycle result dicts
        
    Returns:
        SurvivabilityMetrics
    """
    print("=" * 70)
    print("Survivability Analysis")
    print("=" * 70)
    print()
    
    metrics = analyze_survivability(cycle_results)
    
    print(f"Total cycles analyzed: {metrics.total_cycles}")
    print(f"  Completed: {metrics.completed_cycles}")
    print(f"  Halted: {metrics.halted_cycles}")
    print()
    
    print(f"Violations:")
    print(f"  Total: {metrics.total_violations}")
    print(f"  HALT: {metrics.halt_violations}")
    print(f"  WARN: {metrics.warn_violations}")
    print(f"  WARN-only cycles: {metrics.warn_only_cycles}")
    print()
    
    print(f"Daily Loss Utilization:")
    if metrics.daily_loss_utilization_avg is not None:
        print(f"  Average: {metrics.daily_loss_utilization_avg:.2%}")
        print(f"  Max: {metrics.daily_loss_utilization_max:.2%}")
        print(f"  90th percentile: {metrics.daily_loss_utilization_p90:.2%}")
    else:
        print("  No data available (no daily loss violations with metadata)")
    print()
    
    print(f"Trailing Drawdown Proximity:")
    if metrics.trailing_drawdown_proximity_avg is not None:
        print(f"  Average: {metrics.trailing_drawdown_proximity_avg:.2%}")
        print(f"  Max: {metrics.trailing_drawdown_proximity_max:.2%}")
        if metrics.min_distance_to_drawdown_violation is not None:
            print(f"  Min distance to violation: {metrics.min_distance_to_drawdown_violation:.2%}")
            if metrics.min_distance_to_drawdown_violation < 0.1:
                print(f"    ⚠️  WARNING: Very close to limit!")
    else:
        print("  No data available (no trailing drawdown violations with metadata)")
    print()
    
    print(f"Turnover Pressure:")
    if metrics.turnover_pressure_avg is not None:
        print(f"  Average: {metrics.turnover_pressure_avg:.2%}")
        print(f"  Max: {metrics.turnover_pressure_max:.2%}")
    else:
        print("  No data available")
    print()
    
    print(f"Survival Metrics:")
    print(f"  Days survived: {metrics.days_survived if metrics.days_survived is not None else 'N/A (never halted)'}")
    print(f"  Max violation-free streak: {metrics.violation_free_streak_max}")
    print(f"  Current violation-free streak: {metrics.violation_free_streak_current}")
    print()
    
    return metrics


def print_survivability_summary(metrics: SurvivabilityMetrics):
    """Print clear textual summary of survivability metrics.
    
    Args:
        metrics: SurvivabilityMetrics instance
    """
    print("=" * 70)
    print("Survivability Analysis Summary")
    print("=" * 70)
    print()
    
    print(f"Cycle Statistics:")
    print(f"  Total cycles: {metrics.total_cycles}")
    print(f"  Completed: {metrics.completed_cycles}")
    print(f"  Halted: {metrics.halted_cycles}")
    print()
    
    print(f"Days Survived:")
    if metrics.days_survived is not None:
        print(f"  Days until first HALT: {metrics.days_survived}")
    else:
        print(f"  No HALT occurred (survived all {metrics.total_cycles} cycles)")
    print()
    
    print(f"Violations:")
    print(f"  Total violations: {metrics.total_violations}")
    print(f"  HALT violations: {metrics.halt_violations}")
    print(f"  WARN violations: {metrics.warn_violations}")
    print(f"  WARN-only cycles: {metrics.warn_only_cycles}")
    print(f"  Maximum violation-free streak: {metrics.violation_free_streak_max} cycles")
    print(f"  Current violation-free streak: {metrics.violation_free_streak_current} cycles")
    print()
    
    print(f"Daily Loss Utilization:")
    if metrics.daily_loss_utilization_avg is not None:
        print(f"  Average: {metrics.daily_loss_utilization_avg:.2%}")
        print(f"  Maximum: {metrics.daily_loss_utilization_max:.2%}")
        if metrics.daily_loss_utilization_p90 is not None:
            print(f"  90th percentile: {metrics.daily_loss_utilization_p90:.2%}")
    else:
        print(f"  No data available")
    print()
    
    print(f"Trailing Drawdown Proximity:")
    if metrics.trailing_drawdown_proximity_avg is not None:
        print(f"  Average: {metrics.trailing_drawdown_proximity_avg:.2%}")
        print(f"  Maximum: {metrics.trailing_drawdown_proximity_max:.2%}")
        if metrics.min_distance_to_drawdown_violation is not None:
            print(f"  Min distance to violation: {metrics.min_distance_to_drawdown_violation:.2%}")
            if metrics.min_distance_to_drawdown_violation <= 1.0:
                print(f"    (Warning: At or past limit threshold)")
    else:
        print(f"  No data available")
    print()
    
    print(f"Turnover Pressure:")
    if metrics.turnover_pressure_avg is not None:
        print(f"  Average: {metrics.turnover_pressure_avg:.2%}")
        print(f"  Maximum: {metrics.turnover_pressure_max:.2%}")
    else:
        print(f"  No data available")
    print()
    
    print("=" * 70)


def print_observations(metrics: SurvivabilityMetrics):
    """Print observation questions for manual answers.
    
    Args:
        metrics: SurvivabilityMetrics instance
    """
    print("=" * 70)
    print("Validation Observations (Answer in Plain English)")
    print("=" * 70)
    print()
    print("1. Daily Loss Utilization:")
    print("   Fill in: 'This strategy typically runs at ___% daily loss utilization.'")
    print("   Fill in: 'Spikes occur when ___.'")
    if metrics.daily_loss_utilization_avg is not None:
        print(f"   [Data: avg={metrics.daily_loss_utilization_avg:.2%}, max={metrics.daily_loss_utilization_max:.2%}, p90={metrics.daily_loss_utilization_p90:.2%}]")
    print()
    
    print("2. Trailing Drawdown Proximity:")
    print("   Fill in: 'Drawdown proximity tends to ___ over time.'")
    print("   Fill in: 'After losses it usually moves ___.'")
    if metrics.trailing_drawdown_proximity_avg is not None:
        print(f"   [Data: avg={metrics.trailing_drawdown_proximity_avg:.2%}, max={metrics.trailing_drawdown_proximity_max:.2%}, min_dist={metrics.min_distance_to_drawdown_violation:.2%}]")
    print()
    
    print("3. WARN Clustering:")
    print("   Fill in: 'WARN-only cycles usually appear ___ cycles before a HALT.'")
    print(f"   [Data: warn_only_cycles={metrics.warn_only_cycles}, halted_cycles={metrics.halted_cycles}]")
    print()
    
    print("4. Turnover Pressure:")
    print("   Fill in: 'Turnover pressure peaks when ___, especially during ___.'")
    if metrics.turnover_pressure_avg is not None:
        print(f"   [Data: avg={metrics.turnover_pressure_avg:.2%}, max={metrics.turnover_pressure_max:.2%}]")
    print()
    
    print("5. Judgment:")
    print("   Fill in: 'This strategy becomes dangerous when ___.'")
    print("   Fill in: 'I believe strategies should be penalized when ___.'")
    print()
    
    print("=" * 70)


def main():
    """CLI entrypoint for validation runner."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Phase 15 validation runner for survivability analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python -m src.lifecycle.validation_runner \\
        --config configs/validation_cycle.json \\
        --artifacts-dir ./artifacts \\
        --cycles 30 \\
        --scenario gentle_downward
    
    python -m src.lifecycle.validation_runner \\
        --config configs/validation_cycle.json \\
        --artifacts-dir ./artifacts \\
        --cycles 30 \\
        --scenario choppy_downward
        """
    )
    
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to validation config JSON file"
    )
    
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("./artifacts"),
        help="Directory for artifacts (default: ./artifacts)"
    )
    
    parser.add_argument(
        "--cycles",
        type=int,
        default=30,
        help="Number of cycles to run (default: 30)"
    )
    
    parser.add_argument(
        "--scenario",
        type=str,
        default="gentle_downward",
        choices=["gentle_downward", "choppy_downward", "lock_in_activation"],
        help="Price scenario (default: gentle_downward)"
    )
    
    args = parser.parse_args()
    
    try:
        metrics = run_full_validation(
            config_path=args.config,
            artifacts_dir=args.artifacts_dir,
            num_cycles=args.cycles,
            scenario=args.scenario
        )
        
        print(f"\nValidation complete.")
        print(f"Results persisted to: {args.artifacts_dir}/validation/survivability_metrics.json")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

