"""Verification test for halt persistence.

Ensures that when a cycle halts (e.g. from Max Daily Loss), the state is still persisted
so that the drawdown tracker's history (and valid daily loss) is not lost.

Scenario:
1. Cycle 1: Profitable trade -> Locks tracker (equity > initial).
2. Cycle 2: Loss trade -> Triggers Max Daily Loss limit -> HALT.
3. Verification:
   - Check that Cycle 2 halted.
   - Check that state_after_id IS NOT None.
   - Load the halted state and verify it contains the updated drawdown tracker 
     reflecting the daily loss.
"""

import sys
import shutil
from pathlib import Path
from datetime import datetime, date

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lifecycle.runner import PortfolioCycleConfig, run_portfolio_cycle, ExecutionMode, CycleHaltError, GuardrailsConfig, HaltFlagStore
from src.core.artifacts import LocalArtifactStore
from src.lifecycle.state_store import LocalPortfolioStateStore
from src.engines.simple import SimpleResearchEngine
from src.execution import PaperExecutionEngine
from src.execution.clock import FixedClock
from src.execution.id_provider import DeterministicIDProvider

def create_cycle_config(portfolio_id: str, total_capital: float, price: float, mode: ExecutionMode = ExecutionMode.LIVE_DRY):
    """Create a cycle config for testing."""
    from src.evaluation.batch import BatchEvaluationConfig, StrategyConfig
    from src.allocation.allocator import AllocationConfig
    # Import RebalanceConfig (may be needed depending on implementation)
    from src.rebalance.planner import RebalanceConfig
    
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
                ),
                StrategyConfig(
                    strategy_id="dummy_strategy",
                    experiment_name="noop",
                    experiment_version="v1",
                    experiment_config={},
                    inputs={},
                    description="Dummy for diversification"
                )
            ],
            parameter_grid=None,
            evaluation_criteria={
                "min_robustness_score": 0.0,
                "max_divergence_pct": 1.0,
                "max_timing_drift_seconds": 999999
            },
            price_series=[150]*10
        ),
        allocation_config=AllocationConfig(
            total_capital=total_capital,
            top_n_strategies=2,
            allocation_method="equal"
        ),
        rebalance_config=RebalanceConfig(
            rebalance_threshold_pct=0.0,
            max_turnover_pct=100.0
        ),
        execution_config={
            "price_by_strategy_or_instrument": {
                "test_strategy": price,
                "dummy_strategy": price,
                "AAPL": price
            },
            "rounding_method": "floor",
            "min_quantity": 1.0
        },
        ruleset_type="topstep",
        ruleset_config={
            "max_turnover_pct": 100.0,
            "max_position_size": 10000.0,
            "max_daily_loss": -1000.0,  # Tight daily loss limit
            "max_trailing_drawdown_pct": 3.0,
            "account_size": total_capital
        },
        guardrails_config=GuardrailsConfig(
            max_turnover_pct_per_cycle=10.0,
            max_failed_intents=100,
            min_execution_success_rate=0.0,
            max_single_strategy_allocation_fraction=1.0
        )
    )

def main():
    print("=" * 70)
    print("Halt Persistence Verification")
    print("=" * 70)
    
    portfolio_id = "test_halt_persistence"
    total_capital = 100000.0
    artifacts_dir = Path("./artifacts_test_halt")
    
    # Cleanup
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    artifact_store = LocalArtifactStore(artifacts_dir)
    state_store = LocalPortfolioStateStore(artifact_store)
    research_engine = SimpleResearchEngine(artifact_store=artifact_store)
    
    def create_engine():
        return PaperExecutionEngine(instrument="AAPL", artifact_store=artifact_store)
    
    # --- Cycle 1: Profitable, Lock Tracker ---
    print("\n[Cycle 1] Locking tracker with profit...")
    # Price 155 -> Profit ~ $3,332 (Alloc ~100k / 150 * (155-150)) if buy at 150? 
    # Actually wait. Allocation will buy at execution price.
    # To lock tracker, we need equity > initial.
    # We need to buy low, then have price high.
    # But PaperExecutionEngine executes at current price.
    # So we execute at 150. Equity = Cash + Position(Cost 150).
    # Unrealized PnL is 0 at purchase.
    # Wait, runner.py updates tracker using `validate_execution` or post-exec block.
    # If standard mode, `validate_execution` calculates equity.
    # `validate_execution` uses current prices.
    # Cycle 1: Execute at 150.
    
    ts1 = datetime(2024, 1, 1, 10, 0, 0)
    config_1 = create_cycle_config(portfolio_id, total_capital, price=150.0)
    
    res1 = run_portfolio_cycle(
        config=config_1,
        research_engine=research_engine,
        artifact_store=artifact_store,
        execution_engine_factory=create_engine,
        state_store=state_store,
        execution_mode=ExecutionMode.SIMULATION,
        cycle_timestamp=ts1,
        cycle_id="cycle_1"
    )
    print(f"Cycle 1 Status: {res1.status}")
    assert res1.status == "completed"
    
    # Check state 1 - verify position exists
    state_1 = state_store._load_state(portfolio_id, res1.state_after_id)
    print(f"Cycle 1 Equity: ${state_1.total_capital:,.2f}")
    assert state_1.drawdown_tracker is not None
    
    # Cycle 1.5: We need to update equity to be profitable to lock tracker?
    # Or just start with profit. 
    # Let's say we just want to hit Max Daily Loss in Cycle 2.
    # If we buy at 150 in C1.
    # In C2 (same day? or next day?), price drops to 140.
    # Loss = (140 - 150) * Qty.
    # Qty approx 100k / 150 = 666.
    # Loss approx 666 * 10 = $6,660.
    # Max Daily Loss is -1000.
    # This should HALT.
    
    # --- Cycle 2: Massive Loss -> HALT ---
    print("\n[Cycle 2] Triggering Max Daily Loss...")
    ts2 = datetime(2024, 1, 1, 14, 0, 0) # Same day
    config_2 = create_cycle_config(portfolio_id, total_capital, price=140.0)
    
    res2 = run_portfolio_cycle(
        config=config_2,
        research_engine=research_engine,
        artifact_store=artifact_store,
        execution_engine_factory=create_engine,
        state_store=state_store,
        execution_mode=ExecutionMode.SIMULATION,
        cycle_timestamp=ts2,
        cycle_id="cycle_2"
    )
    # SIMULATION mode returns halted result, does not raise CycleHaltError
    print(f"Cycle 2 Status: {res2.status}")
    print(f"Cycle 2 ID: {res2.cycle_id}")
    print(f"Cycle 2 State After ID: {res2.state_after_id}")
    
    # --- VERIFICATION ---
    print("\n[Verification]")
    
    # 1. Status must be halted
    if res2.status != "halted":
        print("FAIL: Status is not 'halted'")
        sys.exit(1)
        
    # 2. State After ID must NOT be None (The Fix)
    if res2.state_after_id is None:
        print("FAIL: state_after_id is None! Fix not working.")
        sys.exit(1)
    print("PASS: state_after_id is present.")
    
    # 3. Load halted state
    state_halted = state_store._load_state(portfolio_id, res2.state_after_id)
    
    # 4. Check metadata
    meta = state_halted.metadata
    print(f"Metadata: {meta}")
    if not meta or not meta.get("halted"):
        print("FAIL: Metadata missing or halted != True")
        sys.exit(1)
    print("PASS: Metadata confirms halted state.")
    
    # 5. Check Drawdown Tracker reflects the loss
    # Tracker should show equity drop.
    tracker = state_halted.drawdown_tracker
    last_snap = tracker.snapshots[-1]
    
    print(f"Equity in Halted State: ${last_snap.equity:,.2f}")
    daily_loss = tracker.get_daily_loss(last_snap.equity)
    print(f"Daily Loss in Halted State: ${daily_loss:,.2f}")
    
    if daily_loss > -100.0: # Should be around -6k
        print("FAIL: Daily loss is too small, tracker wasn't updated correctly?")
        sys.exit(1)
        
    print("PASS: Drawdown tracker captured values before halt.")
    print("PASS: Drawdown tracker captured values before halt.")

    # 6. RESTART VERIFICATION - Ensure load_latest_state picks up the halted state
    # If the persisted state doesn't have the right suffix (e.g. _after), load_latest_state might skip it
    # and load Cycle 1's state, essentially rolling back the loss.
    print("\n[Restart Verification]")
    latest_state = state_store.load_latest_state(portfolio_id)
    
    if latest_state is None:
        print("FAIL: Latest state is None")
        sys.exit(1)
        
    print(f"Latest State Timestamp: {latest_state.timestamp}")
    print(f"Latest State Halt Reason: {latest_state.metadata.get('halt_reason', 'None')}")
    
    # Check if this is indeed the halted state from Cycle 2 via metadata
    if not latest_state.metadata.get("halted"):
        print("FAIL: load_latest_state() loaded a non-halted state (likely rolled back to Cycle 1)!")
        sys.exit(1)
        
    # Double check values
    loader_tracker = latest_state.drawdown_tracker
    last_snap_loaded = loader_tracker.snapshots[-1]
    msg = f"Loaded Equity: ${last_snap_loaded.equity:,.2f}"
    print(msg)
    
    # It should match the halted state we inspected manually
    if abs(last_snap_loaded.equity - last_snap.equity) > 0.01:
        print(f"FAIL: Loaded equity {last_snap_loaded.equity} != Halted equity {last_snap.equity}")
        sys.exit(1)
        
    print("PASS: System correctly loads the halted state upon restart.")
    
    # 7. RECOVERY FLOW VERIFICATION: Clear Halt -> Run Cycle 3 -> Verify Lineage
    print("\n[Recovery Flow Verification]")
    
    # 7a. Clear Halt Flag
    halt_store = HaltFlagStore(artifact_store)
    print("Clearing halt flag...")
    halt_store.clear_halt_flag(portfolio_id)
    if halt_store.halt_flag_exists(portfolio_id):
        print("FAIL: Halt flag should be gone")
        sys.exit(1)
        
    # 7b. Run Cycle 3 (Recovery)
    print("Running Cycle 3 (Recovery)...")
    ts3 = datetime(2024, 1, 2, 10, 0, 0) # Next day
    # Price recovers slightly, or doesn't matter, just need to run
    config_3 = create_cycle_config(portfolio_id, total_capital, price=145.0)
    
    res3 = run_portfolio_cycle(
        config=config_3,
        research_engine=research_engine,
        artifact_store=artifact_store,
        execution_engine_factory=create_engine,
        state_store=state_store,
        execution_mode=ExecutionMode.SIMULATION,
        cycle_timestamp=ts3,
        cycle_id="cycle_3"
    )
    print(f"Cycle 3 Status: {res3.status}")
    assert res3.status == "completed"
    
    # 7c. Verify Lineage
    # Note: runner creates a NEW snapshot for state_before_id (e.g. cycle_3_before), so IDs won't match.
    # We must verify that the CONTENT of cycle_3_before matches cycle_2's halted state.
    # Specifically: Timestamp, Equity, Drawdown.
    
    print(f"Cycle 3 State Before ID: {res3.state_before_id}")
    
    # Load the actual snapshot used for Cycle 3
    state_3_start = state_store._load_state(portfolio_id, res3.state_before_id)
    state_2_end = state_store._load_state(portfolio_id, res2.state_after_id)
    
    print(f"C2 End TS:   {state_2_end.timestamp}")
    print(f"C3 Start TS: {state_3_start.timestamp}")
    
    if state_3_start.timestamp != state_2_end.timestamp:
        print(f"FAIL: Timestamp mismatch! C3 loaded state from {state_3_start.timestamp}, expected {state_2_end.timestamp}")
        # If it loaded C1, timestamp would be TS1
        sys.exit(1)

    print("PASS: Lineage preserved (Cycle 3 loaded state with correct timestamp).")
    
    # 7d. Verify Drawdown Tracker in Cycle 3
    # Should start with the drawdown from C2
    print(f"Cycle 3 Start Equity: ${state_3_start.total_capital:,.2f}")
    
    if abs(state_3_start.total_capital - 93340.00) > 1.0:
        print(f"FAIL: Cycle 3 started with wrong equity: {state_3_start.total_capital}")
        sys.exit(1)
        
    print("PASS: Cycle 3 started with correct equity/drawdown.")
    
    print("\nSUCCESS: Halted state persisted and recovered correctly.")

if __name__ == "__main__":
    main()
