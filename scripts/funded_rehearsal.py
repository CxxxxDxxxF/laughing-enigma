#!/usr/bin/env python3
"""One-command funded account rehearsal script.

This script runs cycles in LIVE_DRY mode with a funded firm config to validate
that the system halts exactly when it should, matching funded firm behavior.

Usage:
    python scripts/funded_rehearsal.py --config configs/funded/topstep_50k.json --cycles 30

This is the mandatory rehearsal step before any live execution.
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lifecycle.runner import (
    run_portfolio_cycle,
    ExecutionMode,
    PortfolioCycleConfig,
    persist_cycle_result,
    HaltFlagStore,
    CycleHaltError,
)
from src.lifecycle.state_store import LocalPortfolioStateStore
from src.core.artifacts import LocalArtifactStore
from src.engines.simple import SimpleResearchEngine
from src.execution import PaperExecutionEngine
from src.analysis.evidence_report import generate_evidence_report, print_evidence_report


def create_execution_engine_factory(instrument: str, artifact_store) -> callable:
    """Create execution engine factory."""
    def factory():
        return PaperExecutionEngine(
            instrument=instrument,
            artifact_store=artifact_store
        )
    return factory


def run_funded_rehearsal(
    config_path: Path,
    artifacts_dir: Path,
    num_cycles: int = 30,
    start_timestamp: Optional[datetime] = None,
    strategy_config: Optional[dict] = None
) -> List[str]:
    """Run funded account rehearsal in LIVE_DRY mode.
    
    Args:
        config_path: Path to funded firm config JSON
        artifacts_dir: Directory for artifacts
        num_cycles: Number of cycles to run
        start_timestamp: Optional starting timestamp (defaults to now)
        strategy_config: Optional strategy config to inject (if config has empty strategies)
        
    Returns:
        List of cycle IDs executed
        
    Raises:
        SystemExit: If halt occurs or critical error
    """
    # Load config
    config = PortfolioCycleConfig.from_json_file(config_path)
    
    # Validate config is for LIVE_DRY
    if config.day_boundary_config is None:
        print("ERROR: Funded config must include day_boundary_config")
        sys.exit(1)
    
    print("=" * 80)
    print(f"Funded Account Rehearsal: {config.portfolio_id}")
    print("=" * 80)
    print(f"Config: {config_path}")
    print(f"Mode: LIVE_DRY (strict rules, paper execution)")
    print(f"Cycles: {num_cycles}")
    print(f"Account Size: ${config.allocation_config.total_capital:,.0f}")
    if config.ruleset_config:
        print(f"Daily Loss Limit: ${abs(config.ruleset_config.get('max_daily_loss', 0)):,.0f}")
        print(f"Trailing Drawdown Limit: {config.ruleset_config.get('max_trailing_drawdown_pct', 0)}%")
    print()
    
    # Initialize stores and engines
    artifact_store = LocalArtifactStore(artifacts_dir)
    state_store = LocalPortfolioStateStore(artifact_store)
    research_engine = SimpleResearchEngine(artifact_store)
    
    # Check for existing halt flag
    halt_store = HaltFlagStore(artifact_store)
    if halt_store.halt_flag_exists(config.portfolio_id):
        halt_data = halt_store.read_halt_flag(config.portfolio_id)
        print(f"ERROR: Portfolio {config.portfolio_id} is already halted")
        print(f"  Halted at: {halt_data.get('halted_at', 'Unknown')}")
        print(f"  Reason: {halt_data.get('reason', 'Unknown')}")
        print(f"\nTo clear halt flag, run:")
        print(f"  python -m src.lifecycle.halt_cli clear {config.portfolio_id} --artifacts {artifacts_dir}")
        sys.exit(1)
    
    # Setup execution engine factory
    # Get instrument from strategy config or use default
    instrument = "AAPL"  # Default
    if strategy_config and strategy_config.get("instrument"):
        instrument = strategy_config["instrument"]
    elif config.evaluation_config.strategies:
        instrument = config.evaluation_config.strategies[0].inputs.get("instrument", "AAPL")
    
    execution_engine_factory = create_execution_engine_factory(instrument, artifact_store)
    
    # Set start timestamp
    if start_timestamp is None:
        start_timestamp = datetime.now()
        # Round to session start if configured
        if config.day_boundary_config:
            from src.rules.day_boundary import TradingDayBoundary
            boundary = TradingDayBoundary.from_config(config.day_boundary_config)
            # Get session start time
            session_start = boundary.session_start_time
            start_timestamp = start_timestamp.replace(
                hour=session_start.hour,
                minute=session_start.minute,
                second=session_start.second,
                microsecond=0
            )
    
    # Generate cycle IDs and timestamps deterministically
    cycle_ids: List[str] = []
    cycle_timestamps: List[datetime] = []
    
    for i in range(num_cycles):
        cycle_timestamp = start_timestamp + timedelta(hours=i * 24)  # One cycle per day
        cycle_id = f"cycle_{cycle_timestamp.strftime('%Y%m%d_%H%M%S')}"
        cycle_ids.append(cycle_id)
        cycle_timestamps.append(cycle_timestamp)
    
    print(f"Starting rehearsal at: {start_timestamp.isoformat()}")
    print()
    
    # Run cycles
    completed_cycles = 0
    for i, (cycle_id, cycle_timestamp) in enumerate(zip(cycle_ids, cycle_timestamps)):
        print(f"--- Cycle {i+1}/{num_cycles} ({cycle_id}) ---")
        print(f"Timestamp: {cycle_timestamp.isoformat()}")
        
        try:
            result = run_portfolio_cycle(
                config=config,
                research_engine=research_engine,
                artifact_store=artifact_store,
                execution_engine_factory=execution_engine_factory,
                state_store=state_store,
                cycle_id=cycle_id,
                execution_mode=ExecutionMode.LIVE_DRY,
                cycle_timestamp=cycle_timestamp
            )
            
            # Persist result
            persist_cycle_result(result, artifact_store)
            completed_cycles += 1
            
            print(f"Status: {result.status}")
            if result.status == "halted":
                print(f"Reason: {result.skip_reason}")
                print("\nHALT DETECTED - Rehearsal stopped")
                break
            
        except CycleHaltError as e:
            print(f"HALT ERROR: {e}")
            print(f"Result: {e.result.status}")
            print(f"Reason: {e.result.skip_reason}")
            print("\nHALT DETECTED - Rehearsal stopped")
            break
        except Exception as e:
            print(f"ERROR: Cycle failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        print()
    
    print("=" * 80)
    print(f"Rehearsal Complete: {completed_cycles}/{num_cycles} cycles")
    print("=" * 80)
    
    # Check halt status
    if halt_store.halt_flag_exists(config.portfolio_id):
        halt_data = halt_store.read_halt_flag(config.portfolio_id)
        print(f"\nPortfolio HALTED")
        print(f"  Halted at: {halt_data.get('halted_at', 'Unknown')}")
        print(f"  Cycle ID: {halt_data.get('cycle_id', 'Unknown')}")
        print(f"  Reason: {halt_data.get('reason', 'Unknown')}")
        print(f"\nTo inspect halt details:")
        print(f"  python -m src.lifecycle.halt_cli inspect {config.portfolio_id} --artifacts {artifacts_dir}")
    
    # Generate evidence report
    try:
        print("\nGenerating evidence report...")
        report = generate_evidence_report(
            artifact_store=artifact_store,
            portfolio_id=config.portfolio_id,
            start_date=cycle_timestamps[0].date() if cycle_timestamps else None,
            end_date=cycle_timestamps[-1].date() if cycle_timestamps else None
        )
        print_evidence_report(report)
        
        # Save report
        report_path = artifacts_dir / f"evidence_report_{config.portfolio_id}.json"
        import json
        from src.analysis.evidence_report import report_to_dict
        report_path.write_text(json.dumps(report_to_dict(report), indent=2))
        print(f"\nEvidence report saved to: {report_path}")
        
    except Exception as e:
        print(f"WARNING: Could not generate evidence report: {e}")
        import traceback
        traceback.print_exc()
    
    return cycle_ids[:completed_cycles]


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run funded account rehearsal in LIVE_DRY mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 30 cycles with Topstep 50k config
  python scripts/funded_rehearsal.py --config configs/funded/topstep_50k.json --cycles 30
  
  # Run with custom artifacts directory
  python scripts/funded_rehearsal.py --config configs/funded/topstep_100k.json --artifacts ./my_artifacts
        """
    )
    
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to funded firm config JSON file"
    )
    
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path("./artifacts"),
        help="Artifacts directory (default: ./artifacts)"
    )
    
    parser.add_argument(
        "--cycles",
        type=int,
        default=30,
        help="Number of cycles to run (default: 30)"
    )
    
    parser.add_argument(
        "--start-timestamp",
        type=str,
        help="Start timestamp (ISO format, e.g., 2024-01-01T17:00:00). Defaults to now."
    )
    
    args = parser.parse_args()
    
    # Parse start timestamp if provided
    start_timestamp = None
    if args.start_timestamp:
        start_timestamp = datetime.fromisoformat(args.start_timestamp)
    
    # Run rehearsal
    cycle_ids = run_funded_rehearsal(
        config_path=args.config,
        artifacts_dir=args.artifacts,
        num_cycles=args.cycles,
        start_timestamp=start_timestamp
    )
    
    print(f"\nCompleted {len(cycle_ids)} cycles")
    sys.exit(0 if len(cycle_ids) == args.cycles else 1)


if __name__ == "__main__":
    main()

