import sys
import shutil
import json
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lifecycle.runner import run_portfolio_cycle, ExecutionMode, CycleError, HaltFlagStore, PortfolioCycleConfig, CycleHaltError
from src.core.artifacts import LocalArtifactStore
from src.lifecycle.state_store import LocalPortfolioStateStore
from src.rebalance.planner import CurrentPortfolioState
from src.rules.drawdown import DrawdownTracker
from src.engines.simple import SimpleResearchEngine
from src.execution import PaperExecutionEngine
from src.data.providers import StaticMarketDataProvider
from src.evaluation.batch import BatchEvaluationConfig, StrategyConfig
from src.allocation.allocator import AllocationConfig
from src.rebalance.planner import RebalanceConfig
from src.core.instrument_spec import AAPL_EQUITY, register_instrument

def setup_env(pid):
    artifacts_dir = Path(f"./artifacts_test_clearance_{pid}")
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir

def create_config(pid, total_capital):
    return PortfolioCycleConfig(
        portfolio_id=pid,
        evaluation_config=BatchEvaluationConfig(
            strategies=[
                StrategyConfig("s1", "exp", "v1", {}, {"instrument": "AAPL", "strategy_type": "buy_hold", "start_date": "2024-01-01", "end_date": "2024-12-31", "initial_capital": total_capital/2}, "desc"),
                StrategyConfig("s2", "exp", "v1", {}, {"instrument": "AAPL", "strategy_type": "buy_hold", "start_date": "2024-01-01", "end_date": "2024-12-31", "initial_capital": total_capital/2}, "desc")
            ],
            parameter_grid=None,
            evaluation_criteria={}, price_series=[100]*10
        ),
        allocation_config=AllocationConfig(total_capital=total_capital, top_n_strategies=2, allocation_method="equal"),
        rebalance_config=RebalanceConfig(0.0, 0.99, allow_partial_rebalance=True),
        execution_config={"price_by_strategy_or_instrument": {"AAPL": 100.0}},
        ruleset_type="topstep",
        ruleset_config={"account_size": total_capital, "max_daily_loss": -500.0},
        guardrails_config=GuardrailsConfig(
            max_turnover_pct_per_cycle=0.999,
            max_failed_intents=100,
            min_execution_success_rate=0.01,  # Test: low threshold for halt clearance test
            max_single_strategy_allocation_fraction=0.9
        )
    )

from src.lifecycle.runner import GuardrailsConfig

def test_prevention_of_run_while_halted():
    print("Test: Prevention of run while halted")
    pid = "test_halt_block"
    artifacts_dir = setup_env(pid)
    store = LocalArtifactStore(artifacts_dir)
    
    # Write a halt flag
    halt_store = HaltFlagStore(store)
    halt_store.write_halt_flag(pid, "cycle_1", "Manual Halt", datetime.now(), [])
    
    # Register instrument
    register_instrument(AAPL_EQUITY)
    
    try:
        # Try to run
        run_portfolio_cycle(
            config=create_config(pid, 10000.0),
            research_engine=SimpleResearchEngine(store),
            artifact_store=store,
            execution_engine_factory=lambda: PaperExecutionEngine("AAPL", store, account_cash=Decimal("100000"), account_equity=Decimal("100000")),
            cycle_timestamp=datetime.now(),
            execution_mode=ExecutionMode.LIVE_DRY,
            market_data_provider=StaticMarketDataProvider({"AAPL": 100.0}),
            cycle_id="test_cycle_1"
        )
        print("FAIL: Should have raised CycleError")
        sys.exit(1)
    except CycleError as e:
        if "is HALTED" in str(e):
            print("PASS: Blocked execution due to halt flag.")
        else:
            print(f"FAIL: Raised wrong error: {e}")
            sys.exit(1)
    finally:
        shutil.rmtree(artifacts_dir)

def test_state_continuity():
    print("\nTest: State continuity (Resuming with loss triggers halt)")
    pid = "test_resume"
    artifacts_dir = setup_env(pid)
    store = LocalArtifactStore(artifacts_dir)
    state_store = LocalPortfolioStateStore(store)
    
    # Save a "halted" state with 10% loss (9000 equity / 10000 initial)
    state = CurrentPortfolioState(
        strategy_allocations={},
        total_capital=9000.0,
        cash_balance=9000.0,  # Explicitly set cash balance
        timestamp=datetime.now(),
        drawdown_tracker=DrawdownTracker(10000.0, date.today()),
        positions_by_instrument={},
        metadata={"halted": True, "halt_reason": "Max Daily Loss"}
    )
    # Ensure tracker reflects the loss by updating it once (though constructor doesn't do it)
    # The setup above implies: 
    # initial_balance = 10000.
    # We will resume. runner will mark-to-market.
    # total_capital=9000. 
    # Equity will be 9000.
    # Tracker will see 9000. Loss 1000.
    # Max loss is 500.
    # Should halt.
    
    state_store.save_state(pid, state, "cycle_1_halted_reason_after")
    
    # No halt flag (simulating clear)
    
    try:
        # Try to run
        run_portfolio_cycle(
            config=create_config(pid, 10000.0),
            research_engine=SimpleResearchEngine(store),
            artifact_store=store,
            execution_engine_factory=lambda: PaperExecutionEngine("AAPL", artifact_store=store, account_cash=Decimal("100000"), account_equity=Decimal("100000")),
            cycle_timestamp=datetime.now(),
            state_store=state_store, # Must provide state store
            execution_mode=ExecutionMode.LIVE_DRY,
            market_data_provider=StaticMarketDataProvider({"AAPL": 100.0}),
            cycle_id="cycle_2"
        )
        print("FAIL: Resumed successfully but should have halted due to loss.")
    except CycleError as e:
        # runner.py might wrap CycleHaltError
        error_str = str(e)
        if "Cycle halted" in error_str and "Ruleset violation" in error_str and "Daily loss" in error_str:
            print(f"PASS: Halted as expected: {e}")
        else:
             print(f"FAIL: Wrong halt reason/error: {e}")
             sys.exit(1)
    except Exception as e:
        print(f"FAIL: Wrong error: {type(e)} {e}")
        sys.exit(1)
    finally:
        shutil.rmtree(artifacts_dir)

if __name__ == "__main__":
    test_prevention_of_run_while_halted()
    test_state_continuity()
