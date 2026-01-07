"""Production Runner Script.

Main entry point for running the trading system in a continuous loop.
Handles:
- Configuration loading
- Graceful shutdown on SIGINT/SIGTERM
- Exception catching and alerting
- Execution loop throttling
"""
import sys
import os
import time
import signal
import argparse
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lifecycle.runner import run_portfolio_cycle, CycleHaltError
from src.lifecycle.state_store import LocalPortfolioStateStore
from src.core.config import ExecutionMode, AlpacaConfig
from src.core.logger import logger
from src.core.alerting import alert_manager, AlertLevel
from src.core.artifacts import LocalArtifactStore
from src.execution.live_engine import LiveExecutionEngine
from src.data.alpaca_provider import AlpacaMarketDataProvider
from src.execution.alpaca_client import AlpacaClient
from src.execution.order import Order, OrderStatus, OrderSide
from src.execution.fill import Fill
from src.engines.simple import SimpleResearchEngine 
from src.lifecycle.runner import PortfolioCycleConfig, GuardrailsConfig
from src.evaluation.batch import BatchEvaluationConfig, StrategyConfig
from src.allocation.allocator import AllocationConfig
from src.rebalance.planner import RebalanceConfig
from src.core.deterministic_id import generate_cycle_id
import src.strategy.strategies # Register strategies

# Mock Market Data Provider for Dry Run
class MockMarketDataProvider:
    def get_latest_price(self, instrument: str) -> float:
        return 500.0 # Constant dummy price
    
    def get_mark_price(self, instrument: str, timestamp) -> float:
        return 500.0 # Constant dummy price for runner validation

class ProductionRunner:
    """Orchestrates the continuous execution of the trading system."""
    
    def __init__(self, 
                 portfolio_id: str, 
                 strategy_name: str, 
                 execution_mode: ExecutionMode,
                 interval_seconds: int = 60,
                 max_cycles: Optional[int] = None):
        self.portfolio_id = portfolio_id
        self.strategy_name = strategy_name
        self.execution_mode = execution_mode
        self.interval_seconds = interval_seconds
        self.max_cycles = max_cycles
        self.cycles_run = 0
        
        self.running = True
        self.artifact_store = LocalArtifactStore(base_path=Path("data/artifacts"))
        self.state_store = LocalPortfolioStateStore(artifact_store=self.artifact_store)
        
        # Setup Signal Handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        logger.info(f"Runner initialized for {portfolio_id} in {execution_mode.value} mode")

    def _handle_shutdown(self, signum, frame):
        """Handle interrupt signals for graceful shutdown."""
        logger.info(f"Received signal {signum}. Shutting down gracefully...")
        print("\nShutting down gracefully... please wait for current cycle to finish.")
        self.running = False
        
    def _setup_engine_factory(self):
        """Create execution engine factory based on mode."""
        if self.execution_mode in (ExecutionMode.LIVE, ExecutionMode.LIVE_DRY):
            # Load Alpaca Credentials
            api_key = os.getenv("ALPACA_API_KEY")
            secret_key = os.getenv("ALPACA_SECRET_KEY")
            base_url = os.getenv("ALPACA_BASE_URL")
            
            if not all([api_key, secret_key, base_url]):
                 raise ValueError("Missing Alpaca credentials in environment variables")
                 
            config = AlpacaConfig(base_url=base_url, api_key=api_key, secret_key=secret_key)
            client = AlpacaClient(config)
            
            # Provider
            
            # Provider
            self.market_data_provider = AlpacaMarketDataProvider(client)
            
            # Engine Factory
            # Mock Engine for Dry Run Verification
            class MockLiveExecutionEngine(LiveExecutionEngine):
                def sync_portfolio_state(self, state):
                    synced = super().sync_portfolio_state(state)
                    synced.cash_balance = 100000.0
                    synced.total_capital = 100000.0
                    return synced
                
                def submit_order(self, signal):
                    # Mock submission (don't call Alpaca)
                    from src.execution.order import Order, OrderStatus, OrderType
                    from src.execution.signal import SignalType
                    import uuid
                    # Convert SignalType to side string - explicit mapping with error on unknown
                    if signal.signal_type == SignalType.BUY:
                        side = "buy"
                    elif signal.signal_type == SignalType.SELL:
                        side = "sell"
                    elif signal.signal_type == SignalType.HOLD:
                        raise ValueError(f"Cannot create order for HOLD signal: {signal}")
                    else:
                        raise ValueError(f"Unknown signal_type: {signal.signal_type}")
                    return Order(
                        id=str(uuid.uuid4()),
                        signal_id=None,
                        instrument=signal.instrument,
                        quantity=signal.quantity,
                        side=side,
                        order_type=OrderType.MARKET,
                        status=OrderStatus.ACCEPTED,
                        created_at=datetime.now(),
                        accepted_at=datetime.now()
                    )

                def check_execution_status(self, order):
                    # Mock execution fill
                    if order.status == OrderStatus.FILLED:
                        return []
                    
                    fill = Fill(
                        id=f"fill_{order.id}",
                        order_id=order.id,
                        instrument=order.instrument,
                        side=order.side,
                        quantity=order.quantity,
                        price=100.0,  # Dummy price
                        filled_at=datetime.now(),
                        fee=0.0
                    )
                    return [fill]

                def execute_order(self, order, price, timestamp=None):
                    # Mock immediate execution for execute_rebalance_plan compatibility
                    # Note: Order is frozen, so we cannot mutate it
                    fill = Fill(
                        id=f"fill_{order.id}",
                        order_id=order.id,
                        instrument=order.instrument,
                        side=order.side,
                        quantity=order.quantity,
                        price=price or 100.0,
                        filled_at=timestamp or datetime.now(),
                        fee=0.0
                    )
                    return [fill]

            # Mock Market Data Provider
            class MockMarketDataProvider:
                def get_latest_price(self, instrument: str) -> float:
                    return 500.0 # Constant dummy price

            mock_provider = MockMarketDataProvider()

            return lambda: MockLiveExecutionEngine(instrument="SPY", alpaca_client=client) # Set instrument explicit
            
            
        else:
            raise NotImplementedError(f"Mode {self.execution_mode} not fully supported in ProductionRunner yet.")

    def run(self):
        """Start the execution loop."""
        logger.info("Starting execution loop...")
        alert_manager.send("Runner Started", f"Portfolio: {self.portfolio_id}, Mode: {self.execution_mode.value}")
        
        try:
            execution_engine_factory = self._setup_engine_factory()
            
            while self.running:
                if self.max_cycles and self.cycles_run >= self.max_cycles:
                    logger.info(f"Reached max cycles ({self.max_cycles}). Exiting.")
                    break
                    
                start_time = time.time()
                
                try:
                    self._run_single_cycle(execution_engine_factory)
                    self.cycles_run += 1
                except CycleHaltError as e:
                    msg = f"Cycle HALTED: {e}"
                    logger.error(msg)
                    alert_manager.send("Cycle Halted", msg, AlertLevel.CRITICAL)
                    # We continue looping? Or stop? 
                    # Usually halt means we stop trading until manual intervention.
                    # But the runner might want to keep running to see if halt clears?
                    # For safety, let's keep running but maybe switch to slower poll?
                    # Current cycle runner checks halt flag first, so it will block quickly next time.
                    pass
                    
                except Exception as e:
                    msg = f"Unhandled Exception in Cycle: {e}"
                    logger.error(msg, exc_info=True)
                    alert_manager.send("Runner Error", f"{msg}\n{traceback.format_exc()}", AlertLevel.ERROR)
                    # Depending on severity, we might want to exit. 
                    # For now, sleep and retry.
                
                # Sleep handling
                if self.running:
                    elapsed = time.time() - start_time
                    sleep_time = max(0, self.interval_seconds - elapsed)
                    if sleep_time > 0:
                        # Sleep in chunks to allow faster shutdown interrupt
                        chunks = int(sleep_time * 10)
                        for _ in range(chunks):
                            if not self.running: break
                            time.sleep(0.1)
                            
        except Exception as e:
            msg = f"Fatal Runner Crash: {e}"
            logger.critical(msg, exc_info=True)
            alert_manager.send("Runner Crash", f"{msg}\n{traceback.format_exc()}", AlertLevel.CRITICAL)
            sys.exit(1)
            
        logger.info("Runner stopped.")
        alert_manager.send("Runner Stopped", "Graceful shutdown complete.")

    def _run_single_cycle(self, execution_engine_factory):
        """Execute a single portfolio cycle."""
        # Setup Config for Cycle
        # Using StrategyFactory requires passing strategy_name in ruleset_config or similar?
        # Runner currently needs to know HOW to tell runner.py which strategy to use.
        # run_portfolio_cycle takes `ruleset_config`.
        # Note: Current runner.py doesn't strictly enforce strategy selection via factory yet 
        # unless we update `run_portfolio_cycle` to use it.
        # For now, we assume defaults or pass basic config.
        
        # We need a ResearchEngine for `run_portfolio_cycle` signature
        # Use SimpleResearchEngine as placeholder/utility?
        research_engine = SimpleResearchEngine(self.artifact_store)
        
        # Config
        from datetime import timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        # 1. Evaluation Config
        eval_config = BatchEvaluationConfig(
            strategies=[
                StrategyConfig(
                    strategy_id=self.strategy_name,
                    experiment_name="live_execution",
                    experiment_version="v1",
                    experiment_config={}, # Config passed to strategy factory often comes from inputs or special field?
                    # StrategyFactory uses experiment.config AND inputs. 
                    # DualMomentum needs parameters.
                    inputs={
                        "start_date": start_date.strftime("%Y-%m-%d"),
                        "end_date": end_date.strftime("%Y-%m-%d"),
                        "initial_capital": 100000.0,
                        "strategy_type": "dual_momentum",
                        "lookback_days": 126, 
                        "instrument": "SPY",
                        "top_n": 1
                    }
                )
            ]
        )
        
        # 2. Allocation Config
        alloc_config = AllocationConfig(
            total_capital=100000.0,
            allocation_method="equal",
            max_allocation_per_strategy=0.99, 
            min_allocation_per_strategy=0.0
        )
        
        # 3. Rebalance Config
        rebal_config = RebalanceConfig(
            rebalance_threshold_pct=0.01
        )
        
        # 4. Execution Config
        exec_config = {
            "rounding_method": "floor",
            "min_quantity": 1.0
        }

        # 5. Guardrails Config (Required for LIVE/LIVE_DRY)
        guardrails_config = GuardrailsConfig(
            max_turnover_pct_per_cycle=0.999, # Allow effectively 100% turnover
            max_failed_intents=3,
            min_execution_success_rate=0.8,
            max_single_strategy_allocation_fraction=0.99, # Enable 100% allocation for single-strategy testing
            halt_on_any_error=True
        )

        # Ruleset Config
        ruleset_config = {
            "max_position_size": 1.0, # Topstep constraints
            "max_daily_loss": -2000.0
        }

        config = PortfolioCycleConfig(
            portfolio_id=self.portfolio_id,
            evaluation_config=eval_config,
            allocation_config=alloc_config,
            rebalance_config=rebal_config,
            execution_config=exec_config,
            guardrails_config=guardrails_config,
            ruleset_type="topstep", 
            ruleset_config=ruleset_config
        )
        
        
        # Generate Cycle ID
        cycle_timestamp = datetime.now()
        cycle_id = generate_cycle_id(self.portfolio_id, cycle_timestamp.isoformat())
        
        run_portfolio_cycle(
            config=config,
            research_engine=research_engine,
            artifact_store=self.artifact_store,
            execution_engine_factory=execution_engine_factory,
            state_store=self.state_store,
            execution_mode=self.execution_mode,
            cycle_timestamp=cycle_timestamp,
            cycle_id=cycle_id,
            market_data_provider=self.market_data_provider if self.execution_mode != ExecutionMode.LIVE_DRY else MockMarketDataProvider()
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Trading System Live")
    parser.add_argument("--portfolio", required=True, help="Portfolio ID")
    parser.add_argument("--strategy", required=True, help="Strategy Name (e.g. dual_momentum)")
    parser.add_argument("--mode", choices=["LIVE", "LIVE_DRY"], default="LIVE_DRY", help="Execution Mode")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval in seconds")
    parser.add_argument("--max-cycles", type=int, default=None, help="Max cycles to run (for testing)")
    
    args = parser.parse_args()
    
    # Load env
    from dotenv import load_dotenv
    load_dotenv()
    
    mode_enum = ExecutionMode[args.mode]
    
    runner = ProductionRunner(
        portfolio_id=args.portfolio,
        strategy_name=args.strategy,
        execution_mode=mode_enum,
        interval_seconds=args.interval,
        max_cycles=args.max_cycles
    )
    
    runner.run()
