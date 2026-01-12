import sys
from decimal import Decimal
import shutil
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lifecycle.runner import PortfolioCycleConfig, run_portfolio_cycle, ExecutionMode, CycleHaltError, GuardrailsConfig
from src.core.artifacts import LocalArtifactStore
from src.lifecycle.state_store import LocalPortfolioStateStore
from src.engines.simple import SimpleResearchEngine
from src.execution import PaperExecutionEngine
from src.data.providers import StaticMarketDataProvider
from src.evaluation.batch import BatchEvaluationConfig, StrategyConfig
from src.allocation.allocator import AllocationConfig
from src.rebalance.planner import RebalanceConfig
from src.core.instrument_spec import AAPL_EQUITY, register_instrument

def create_config(portfolio_id: str, total_capital: float):
    return PortfolioCycleConfig(
        portfolio_id=portfolio_id,
        evaluation_config=BatchEvaluationConfig(
            strategies=[
                StrategyConfig(
                    strategy_id="test_strat",
                    experiment_name="test",
                    experiment_version="v1",
                    experiment_config={},
                    inputs={ 
                        "instrument": "AAPL", 
                        "strategy_type": "buy_hold",
                        "start_date": "2024-01-01",
                        "end_date": "2024-12-31",
                        "initial_capital": 50000.0
                    },
                    description="Test"
                ),
                StrategyConfig(
                    strategy_id="dummy_strat",
                    experiment_name="noop",
                    experiment_version="v1",
                    experiment_config={},
                    inputs={
                        "instrument": "AAPL",
                        "strategy_type": "buy_hold",
                         "start_date": "2024-01-01",
                        "end_date": "2024-12-31",
                        "initial_capital": 50000.0
                    },
                    description="Dummy"
                )
            ],
            parameter_grid=None,
            evaluation_criteria={ "min_robustness_score": 0.0, "max_divergence_pct": 1.0, "max_timing_drift_seconds": 999999 },
            price_series=[100]*10
        ),
        allocation_config=AllocationConfig(total_capital=total_capital, top_n_strategies=2, allocation_method="equal"),
        rebalance_config=RebalanceConfig(rebalance_threshold_pct=0.0, max_turnover_pct=0.99, allow_partial_rebalance=True),
        execution_config={
            "price_by_strategy_or_instrument": { "AAPL": 100.0 }, # Config price
            "rounding_method": "floor",
            "min_quantity": 1.0
        },
        ruleset_type="topstep",
        ruleset_config={
            "max_turnover_pct": 100.0,
            "max_position_size": 10000.0,
            "max_daily_loss": -1000.0,
            "max_trailing_drawdown_pct": 3.0,
            "account_size": total_capital
        },
        guardrails_config=GuardrailsConfig(
            max_turnover_pct_per_cycle=0.999,
            max_failed_intents=100,
            min_execution_success_rate=0.50,  # Test: allow 50% for two-strategy test
            max_single_strategy_allocation_fraction=0.9
        )
    )

def test_live_price_injection():
    print("="*50)
    print("Verifying Live Price Injection")
    print("="*50)
    
    pid = "test_live_prices"
    artifacts_dir = Path("./artifacts_test_live")
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Register instrument for position sizing
    register_instrument(AAPL_EQUITY)
    
    max_price = 999.0
    
    # 1. Setup
    config = create_config(pid, 100000.0)
    artifact_store = LocalArtifactStore(artifacts_dir)
    state_store = LocalPortfolioStateStore(artifact_store)
    research = SimpleResearchEngine(artifact_store)
    
    # 2. Configure Provider with a distinct price
    provider = StaticMarketDataProvider(prices={"AAPL": max_price})
    
    def create_engine():
        return PaperExecutionEngine(instrument="AAPL", artifact_store=artifact_store, account_cash=Decimal("100000"), account_equity=Decimal("100000"))
    
    # 3. Run Cycle in LIVE_DRY mode
    print("Running cycle in LIVE_DRY mode...")
    res = run_portfolio_cycle(
        config=config,
        research_engine=research,
        artifact_store=artifact_store,
        execution_engine_factory=create_engine,
        cycle_timestamp=datetime(2024, 1, 1),
        state_store=state_store,
        execution_mode=ExecutionMode.LIVE_DRY,
        cycle_id="live_test_1",
        market_data_provider=provider
    )
    
    if res.status != "completed":
        print(f"FAIL: Cycle failed with status {res.status}")
        sys.exit(1)
        
    # 4. Verify Execution Used Implied Price
    # We can check the allocation result or execution result?
    # Execution result stores 'execution_price' in fills? Not easily accessible here maybe.
    # But positions in state should reflect the cost basis.
    
    state = state_store.load_latest_state(pid)
    pos = state.positions_by_instrument.get("AAPL")
    
    if not pos:
        print("FAIL: No position created")
        sys.exit(1)
        
    print(f"Position Cost Basis: ${pos.cost_basis:.2f}")
    
    if abs(pos.cost_basis - max_price) < 0.01:
        print("PASS: Used injected live price.")
    elif abs(pos.cost_basis - 100.0) < 0.01:
        print("FAIL: Used config price (100.0) instead of live price.")
        sys.exit(1)
    else:
        print(f"Got basis: {pos.cost_basis}")
        sys.exit(1)

if __name__ == "__main__":
    test_live_price_injection()
