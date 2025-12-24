#!/usr/bin/env python3
"""Trace one cycle end-to-end to find where equity stops updating.

This script traces:
price → signal → intent → fill → position → PnL → equity

Stops at the first broken link.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lifecycle.runner import run_portfolio_cycle, PortfolioCycleConfig, ExecutionMode
from src.engines.simple import SimpleResearchEngine
from src.core.artifacts import LocalArtifactStore
from src.execution import PaperExecutionEngine
from src.lifecycle.state_store import LocalPortfolioStateStore

def trace_cycle(config_path: Path, artifacts_dir: Path, cycle_num: int = 1):
    """Trace one specific cycle."""
    
    # Load config
    with open(config_path, 'r') as f:
        config_dict = json.load(f)
    
    config = PortfolioCycleConfig.from_dict(config_dict)
    
    # Setup
    artifact_store = LocalArtifactStore(artifacts_dir)
    research_engine = SimpleResearchEngine()
    state_store = LocalPortfolioStateStore(artifact_store)
    
    # Execution engine factory
    instrument = "AAPL"
    if config.evaluation_config.strategies:
        instrument = config.evaluation_config.strategies[0].inputs.get("instrument", "AAPL")
    
    def create_engine():
        return PaperExecutionEngine(instrument=instrument, artifact_store=artifact_store)
    
    # Set up cycle timestamp
    start_timestamp = datetime.now().replace(hour=17, minute=0, second=0, microsecond=0)
    cycle_timestamp = start_timestamp + timedelta(days=cycle_num - 1)
    cycle_id = f"trace_cycle_{cycle_num}"
    
    print("=" * 80)
    print(f"TRACING CYCLE {cycle_num}")
    print("=" * 80)
    print(f"Cycle ID: {cycle_id}")
    print(f"Timestamp: {cycle_timestamp}")
    print()
    
    # STEP 1: Price Input
    print("STEP 1: PRICE INPUT")
    print("-" * 80)
    price_map = config.execution_config.get("price_by_strategy_or_instrument", {})
    print(f"Execution config prices: {price_map}")
    
    # Check if price_series exists
    price_series = config.evaluation_config.price_series
    if price_series:
        print(f"Price series (evaluation): {price_series}")
        if cycle_num <= len(price_series):
            expected_price = price_series[cycle_num - 1]
            print(f"Expected price for cycle {cycle_num}: ${expected_price:.2f}")
            
            # Check if execution config matches
            for key, price in price_map.items():
                if price != expected_price:
                    print(f"  WARNING: {key} price ${price:.2f} != expected ${expected_price:.2f}")
        else:
            print(f"  WARNING: Cycle {cycle_num} exceeds price_series length ({len(price_series)})")
    else:
        print("  WARNING: No price_series in evaluation_config")
    
    print()
    
    # Load state before (if exists)
    current_state = None
    if cycle_num > 1:
        try:
            state_id = f"trace_cycle_{cycle_num-1}_after"
            current_state = state_store.load_state(config.portfolio_id, state_id)
            if current_state:
                print(f"Loaded state from cycle {cycle_num-1}:")
                print(f"  Total capital: ${current_state.total_capital:,.2f}")
                print(f"  Positions: {list(current_state.positions_by_instrument.keys()) if current_state.positions_by_instrument else 'None'}")
        except Exception as e:
            print(f"No previous state found: {e}")
    
    print()
    
    # STEP 2: Run cycle
    print("STEP 2: RUNNING CYCLE")
    print("-" * 80)
    
    try:
        result = run_portfolio_cycle(
            config=config,
            research_engine=research_engine,
            artifact_store=artifact_store,
            execution_engine_factory=create_engine,
            state_store=state_store,
            cycle_id=cycle_id,
            execution_mode=ExecutionMode.SIMULATION,
            cycle_timestamp=cycle_timestamp
        )
        
        # STEP 3: Signal Generation (check evaluation)
        print("\nSTEP 3: SIGNAL GENERATION")
        print("-" * 80)
        if result.evaluation_id:
            eval_data = artifact_store.retrieve(result.evaluation_id, "evaluation.json")
            if eval_data:
                eval_dict = json.loads(eval_data.decode('utf-8'))
                strategies = eval_dict.get('strategies', [])
                print(f"Strategies evaluated: {len(strategies)}")
                for strat in strategies:
                    print(f"  - {strat.get('strategy_id')}: {strat.get('status', 'unknown')}")
        
        # STEP 4: Order Creation & Execution (check rebalance execution)
        print("\nSTEP 4: ORDER CREATION & EXECUTION")
        print("-" * 80)
        if result.rebalance_execution_id:
            exec_data = artifact_store.retrieve(result.rebalance_execution_id, "execution_result.json")
            if exec_data:
                exec_dict = json.loads(exec_data.decode('utf-8'))
                summary = exec_dict.get('execution_summary', {})
                print(f"Orders submitted: {summary.get('orders_submitted', 0)}")
                print(f"Fills created: {summary.get('fills_created', 0)}")
                
                # Check fills
                fills = exec_dict.get('fills', [])
                if fills:
                    print(f"Fill details:")
                    for fill in fills[:3]:  # First 3 fills
                        print(f"  - {fill.get('instrument')}: {fill.get('quantity')} @ ${fill.get('price', 0):.2f}")
        
        # STEP 5: Position State
        print("\nSTEP 5: POSITION STATE")
        print("-" * 80)
        if result.state_after_id:
            state_after = state_store.load_state(config.portfolio_id, result.state_after_id)
            if state_after:
                print(f"Positions after cycle:")
                if state_after.positions_by_instrument:
                    for inst, pos_dict in state_after.positions_by_instrument.items():
                        print(f"  {inst}: {pos_dict.get('quantity', 0)} @ ${pos_dict.get('cost_basis', 0):.2f}")
                        print(f"    Realized PnL: ${pos_dict.get('realized_pnl', 0):.2f}")
                else:
                    print("  No positions")
        
        # STEP 6: PnL Calculation
        print("\nSTEP 6: PNL CALCULATION")
        print("-" * 80)
        summary = result.summary
        print(f"Realized PnL: ${summary.get('realized_pnl', 0):,.2f}")
        print(f"Unrealized PnL: ${summary.get('unrealized_pnl', 0):,.2f}")
        
        # STEP 7: Equity Update
        print("\nSTEP 7: EQUITY UPDATE")
        print("-" * 80)
        equity = summary.get('equity', 0)
        print(f"Equity in cycle summary: ${equity:,.2f}")
        
        # Check if it changed
        if current_state:
            prev_equity = current_state.total_capital
            print(f"Previous equity: ${prev_equity:,.2f}")
            change = equity - prev_equity
            print(f"Change: ${change:,.2f}")
            
            if abs(change) < 0.01:
                print("\n⚠️  WARNING: EQUITY DID NOT CHANGE")
                print("   This indicates a broken link in the chain")
            else:
                print(f"\n✓ Equity changed by ${change:,.2f}")
        else:
            print("No previous state (first cycle)")
            expected_equity = config.allocation_config.total_capital
            if abs(equity - expected_equity) < 0.01:
                print(f"⚠️  WARNING: Equity equals initial capital (${expected_equity:,.2f})")
                print("   This may be normal for cycle 1 if no trades occurred")
        
        print("\n" + "=" * 80)
        print("CYCLE TRACE COMPLETE")
        print("=" * 80)
        
        return result
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description="Trace one cycle end-to-end")
    parser.add_argument('--config', type=Path, required=True, help='Config file')
    parser.add_argument('--artifacts', type=Path, required=True, help='Artifacts directory')
    parser.add_argument('--cycle', type=int, default=1, help='Cycle number to trace (default: 1)')
    
    args = parser.parse_args()
    
    trace_cycle(args.config, args.artifacts, args.cycle)

