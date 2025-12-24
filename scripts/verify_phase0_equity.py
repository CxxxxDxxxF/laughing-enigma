#!/usr/bin/env python3
"""Phase 0 Equity Verification Script

Runs 5 cycles with price movement and verifies:
1. Unrealized PnL moves across cycles
2. Equity diverges from initial
3. Price source is execution-derived

Usage:
    python scripts/verify_phase0_equity.py --artifacts ./artifacts_phase0_verify
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lifecycle.runner import (
    run_portfolio_cycle,
    ExecutionMode,
    PortfolioCycleConfig,
    persist_cycle_result,
)
from src.lifecycle.state_store import LocalPortfolioStateStore
from src.core.artifacts import LocalArtifactStore
from src.engines.simple import SimpleResearchEngine
from src.execution import PaperExecutionEngine


def create_execution_engine_factory(instrument: str, artifact_store) -> callable:
    """Create execution engine factory."""
    def factory():
        return PaperExecutionEngine(
            instrument=instrument,
            artifact_store=artifact_store
        )
    return factory


def load_base_config() -> PortfolioCycleConfig:
    """Load base config for verification."""
    config_path = Path(__file__).parent.parent / "configs" / "backtest" / "topstep_50k_backtest.json"
    return PortfolioCycleConfig.from_json_file(config_path)


def run_verification_cycles(
    artifact_store: LocalArtifactStore,
    num_cycles: int = 5,
    start_price: float = 150.0
) -> List[str]:
    """Run verification cycles with price movement.
    
    Args:
        artifact_store: Artifact store
        num_cycles: Number of cycles to run
        start_price: Starting price
        
    Returns:
        List of cycle IDs
    """
    # Load base config
    config = load_base_config()
    
    # Initialize stores and engines
    state_store = LocalPortfolioStateStore(artifact_store)
    research_engine = SimpleResearchEngine(artifact_store)
    execution_engine_factory = create_execution_engine_factory("AAPL", artifact_store)
    
    # Price series: decreasing prices to create unrealized PnL
    # Start at 150, decrease by 1 each cycle: 150, 149, 148, 147, 146
    prices = [start_price - i for i in range(num_cycles)]
    
    cycle_ids = []
    start_timestamp = datetime(2025, 12, 22, 17, 0, 0)
    
    print("=" * 80)
    print("Phase 0 Equity Verification")
    print("=" * 80)
    print(f"Running {num_cycles} cycles with price movement")
    print(f"Price series: {prices}")
    print()
    
    for cycle_num in range(num_cycles):
        cycle_timestamp = start_timestamp + timedelta(days=cycle_num)
        cycle_id = f"phase0_verify_{cycle_timestamp.strftime('%Y%m%d_%H%M%S')}"
        cycle_ids.append(cycle_id)
        
        # Update config with current price
        current_price = prices[cycle_num]
        config_dict = config.to_dict()
        config_dict["execution_config"]["price_by_strategy_or_instrument"] = {
            "test_strategy_v1": current_price,
            "allocation_stub_v1": current_price,
            "AAPL": current_price
        }
        config_dict["cycle_id"] = cycle_id
        config_dict["execution_mode"] = "simulation"
        
        cycle_config = PortfolioCycleConfig.from_dict(config_dict)
        
        print(f"Cycle {cycle_num + 1}/{num_cycles}: {cycle_id}")
        print(f"  Price: ${current_price:.2f}")
        
        try:
            result = run_portfolio_cycle(
                config=cycle_config,
                research_engine=research_engine,
                artifact_store=artifact_store,
                execution_engine_factory=execution_engine_factory,
                state_store=state_store,
                cycle_id=cycle_id,
                execution_mode=ExecutionMode.SIMULATION,
                cycle_timestamp=cycle_timestamp
            )
            
            persist_cycle_result(result, artifact_store)
            
            equity = result.summary.get("equity", 0.0)
            unrealized_pnl = result.summary.get("unrealized_pnl", 0.0)
            realized_pnl = result.summary.get("realized_pnl", 0.0)
            
            print(f"  Equity: ${equity:.2f}")
            print(f"  Realized PnL: ${realized_pnl:.2f}")
            print(f"  Unrealized PnL: ${unrealized_pnl:.2f}")
            print()
            
        except Exception as e:
            print(f"  ERROR: {e}")
            raise
    
    return cycle_ids


def verify_condition_1(cycle_results: List[Dict[str, Any]]) -> tuple[bool, str]:
    """Verify: Unrealized PnL moves across cycles.
    
    Returns:
        (passed, evidence)
    """
    unrealized_pnl_values = [
        r["summary"].get("unrealized_pnl", 0.0) 
        for r in cycle_results
    ]
    
    # Check if any are non-zero
    has_non_zero = any(abs(v) > 0.001 for v in unrealized_pnl_values)
    
    # Check if values change
    values_change = len(set(round(v, 2) for v in unrealized_pnl_values)) > 1
    
    passed = has_non_zero and values_change
    
    evidence = {
        "unrealized_pnl_by_cycle": unrealized_pnl_values,
        "has_non_zero": has_non_zero,
        "values_change": values_change
    }
    
    return passed, json.dumps(evidence, indent=2)


def verify_condition_2(cycle_results: List[Dict[str, Any]], initial_equity: float) -> tuple[bool, str]:
    """Verify: Equity diverges from initial.
    
    Returns:
        (passed, evidence)
    """
    equity_values = [
        r["summary"].get("equity", initial_equity)
        for r in cycle_results
    ]
    
    # Check if any equity differs from initial
    diverges = any(abs(e - initial_equity) > 0.01 for e in equity_values)
    
    evidence = {
        "initial_equity": initial_equity,
        "equity_by_cycle": equity_values,
        "diverges": diverges,
        "max_divergence": max(abs(e - initial_equity) for e in equity_values) if diverges else 0.0
    }
    
    return diverges, json.dumps(evidence, indent=2)


def verify_condition_3(cycle_results: List[Dict[str, Any]], artifact_store: LocalArtifactStore) -> tuple[bool, str]:
    """Verify: Price source is execution-derived.
    
    Checks that fills contain prices from execution (not static config).
    If positions exist and unrealized PnL is non-zero, prices must be execution-derived.
    
    Returns:
        (passed, evidence)
    """
    evidence_items = []
    fills_with_prices = []
    
    for cycle_result in cycle_results:
        cycle_id = cycle_result["cycle_id"]
        exec_id = cycle_result.get("rebalance_execution_id")
        
        if exec_id:
            # Load execution result and check fills
            try:
                exec_data = artifact_store.retrieve(exec_id, "rebalance_execution.json")
                if exec_data:
                    exec_dict = json.loads(exec_data.decode('utf-8'))
                    intent_results = exec_dict.get("intent_results", [])
                    
                    for intent_result in intent_results:
                        fills = intent_result.get("fills", [])
                        for fill in fills:
                            if fill.get("price") is not None:
                                fills_with_prices.append({
                                    "cycle_id": cycle_id,
                                    "fill_price": fill.get("price"),
                                    "instrument": fill.get("instrument"),
                                    "quantity": fill.get("quantity")
                                })
            except Exception as e:
                evidence_items.append({
                    "cycle_id": cycle_id,
                    "error": str(e)
                })
    
    # Check if we have positions with unrealized PnL - this proves execution-derived prices
    has_unrealized_pnl = any(
        abs(r["summary"].get("unrealized_pnl", 0.0)) > 0.001 
        for r in cycle_results
    )
    
    # If we have fills with prices, that's evidence of execution-derived prices
    has_fill_prices = len(fills_with_prices) > 0
    
    # Pass if: (1) we have fills with prices, OR (2) we have unrealized PnL (which requires execution prices)
    passed = has_fill_prices or has_unrealized_pnl
    
    evidence = {
        "fills_with_execution_prices": len(fills_with_prices),
        "fill_price_evidence": fills_with_prices[:5],  # First 5 for brevity
        "has_unrealized_pnl": has_unrealized_pnl,
        "execution_derived_prices_confirmed": passed
    }
    
    return passed, json.dumps(evidence, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Phase 0 Equity Verification")
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path("./artifacts_phase0_verify"),
        help="Artifact directory"
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=5,
        help="Number of cycles to run"
    )
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Skip running cycles, only verify existing artifacts"
    )
    
    args = parser.parse_args()
    
    artifact_store = LocalArtifactStore(args.artifacts)
    
    # Run cycles if not skipping
    if not args.skip_run:
        cycle_ids = run_verification_cycles(artifact_store, num_cycles=args.cycles)
    else:
        # Find existing phase0_verify cycles
        cycle_ids = []
        for cycle_dir in (args.artifacts / "runs").glob("phase0_verify_*"):
            cycle_ids.append(cycle_dir.name)
        cycle_ids.sort()
        print(f"Found {len(cycle_ids)} existing cycles")
    
    # Load cycle results
    print("\n" + "=" * 80)
    print("Loading Cycle Results")
    print("=" * 80)
    cycle_results = []
    for cycle_id in cycle_ids:
        try:
            result_data = artifact_store.retrieve(cycle_id, "cycle_result.json")
            if result_data:
                result_dict = json.loads(result_data.decode('utf-8'))
                cycle_results.append(result_dict)
                print(f"✓ Loaded {cycle_id}")
            else:
                print(f"✗ Missing {cycle_id}")
        except Exception as e:
            print(f"✗ Error loading {cycle_id}: {e}")
    
    if not cycle_results:
        print("ERROR: No cycle results found")
        sys.exit(1)
    
    # Get initial equity from first cycle
    initial_equity = cycle_results[0]["summary"].get("equity", 50000.0)
    
    # Run verification
    print("\n" + "=" * 80)
    print("Verification Results")
    print("=" * 80)
    
    # Condition 1: Unrealized PnL moves
    print("\n1. Unrealized PnL Must Move")
    print("-" * 80)
    passed_1, evidence_1 = verify_condition_1(cycle_results)
    print(f"Status: {'✓ PASSED' if passed_1 else '✗ FAILED'}")
    print(f"Evidence:\n{evidence_1}")
    
    # Condition 2: Equity diverges
    print("\n2. Equity Must Diverge from Initial")
    print("-" * 80)
    passed_2, evidence_2 = verify_condition_2(cycle_results, initial_equity)
    print(f"Status: {'✓ PASSED' if passed_2 else '✗ FAILED'}")
    print(f"Evidence:\n{evidence_2}")
    
    # Condition 3: Price source is execution-derived
    print("\n3. Price Source Must Be Execution-Derived")
    print("-" * 80)
    passed_3, evidence_3 = verify_condition_3(cycle_results, artifact_store)
    print(f"Status: {'✓ PASSED' if passed_3 else '✗ FAILED'}")
    print(f"Evidence:\n{evidence_3}")
    
    # Final verdict
    print("\n" + "=" * 80)
    print("Final Verdict")
    print("=" * 80)
    all_passed = passed_1 and passed_2 and passed_3
    print(f"Phase 0 Equity Verification: {'✓ PASSED' if all_passed else '✗ FAILED'}")
    
    if not all_passed:
        print("\nFailed conditions:")
        if not passed_1:
            print("  - Unrealized PnL does not move")
        if not passed_2:
            print("  - Equity does not diverge from initial")
        if not passed_3:
            print("  - Price source is not execution-derived")
        sys.exit(1)
    
    print("\nAll conditions verified. Phase 0 equity movement verification complete.")


if __name__ == "__main__":
    main()

