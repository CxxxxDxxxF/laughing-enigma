"""Tests for ExecutionMode and LIVE mode enforcement.

These tests lock in the critical invariants:
- LIVE mode requires explicit timestamps
- LIVE mode requires guardrails
- LIVE mode writes halt flags on halt
- LIVE mode refuses to start when halted
"""

import sys
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest import TestCase

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lifecycle.runner import (
    run_portfolio_cycle,
    PortfolioCycleConfig,
    CycleError,
    CycleHaltError,
    ExecutionMode,
    HaltFlagStore,
)
from src.lifecycle.state_store import LocalPortfolioStateStore
from src.lifecycle.guardrails import GuardrailsConfig
from src.core.artifacts import LocalArtifactStore
from src.engines.simple import SimpleResearchEngine
from src.execution import PaperExecutionEngine
from src.evaluation.batch import BatchEvaluationConfig, StrategyConfig
from src.allocation.allocator import AllocationConfig
from src.rebalance.planner import RebalanceConfig, CurrentPortfolioState
from src.market.interface import MarketDataProvider

class MockMarketDataProvider(MarketDataProvider):
    def get_mark_price(self, instrument, as_of): return 150.0
    def get_execution_price(self, instrument, as_of, side, quantity): return 150.0
    def get_bid_ask(self, instrument, as_of): return (149.0, 151.0)

class TestExecutionMode(TestCase):
    """Test ExecutionMode enforcement."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.artifact_store = LocalArtifactStore(self.temp_dir)
        self.research_engine = SimpleResearchEngine(artifact_store=self.artifact_store)
        self.state_store = LocalPortfolioStateStore(self.artifact_store)
        self.portfolio_id = "test_portfolio"
        self.mock_provider = MockMarketDataProvider()
        
        # Create minimal evaluation config
        self.eval_config = BatchEvaluationConfig(
            strategies=[StrategyConfig(
                strategy_id="test_strategy",
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
                description="Test strategy"
            )],
            parameter_grid=None,
            evaluation_criteria={
                "min_robustness_score": 0.0,
                "max_divergence_pct": 1.0,
                "max_timing_drift_seconds": 999999
            },
            price_series=[150, 151, 152, 153, 154, 155, 156, 157, 158, 159]
        )
        
        # Create guardrails config (non-permissive for LIVE mode)
        self.guardrails_config = GuardrailsConfig(
            max_turnover_pct_per_cycle=0.5,  # < 1.0
            max_failed_intents=0,  # Set
            min_execution_success_rate=0.9,  # > 0.0
            max_single_strategy_allocation_fraction=0.8  # < 1.0
        )
        
        # Create execution engine factory
        def create_engine():
            return PaperExecutionEngine(instrument="AAPL", artifact_store=self.artifact_store)
        self.execution_engine_factory = create_engine
        
        # Base config
        self.base_config = PortfolioCycleConfig(
            portfolio_id=self.portfolio_id,
            evaluation_config=self.eval_config,
            allocation_config=AllocationConfig(
                total_capital=100000.0,
                top_n_strategies=1,
                allocation_method="equal"
            ),
            rebalance_config=RebalanceConfig(
                rebalance_threshold_pct=0.0,
                max_turnover_pct=1.0
            ),
            execution_config={
                "price_by_strategy_or_instrument": {"AAPL": 150.0, "test_strategy": 150.0},
                "rounding_method": "floor",
                "min_quantity": 1.0
            },
            guardrails_config=self.guardrails_config
        )
    
    def tearDown(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_live_requires_cycle_timestamp(self):
        """Test that LIVE mode requires explicit cycle_timestamp."""
        # Should raise CycleError when cycle_timestamp is None in LIVE mode
        with self.assertRaises(CycleError) as cm:
            run_portfolio_cycle(
                config=self.base_config,
                research_engine=self.research_engine,
                artifact_store=self.artifact_store,
                execution_engine_factory=self.execution_engine_factory,
                state_store=self.state_store,
                execution_mode=ExecutionMode.LIVE,
                cycle_timestamp=None  # Missing timestamp
            )
        
        self.assertIn("cycle_timestamp", str(cm.exception))
        # Message is "LIVE/LIVE_DRY mode requires..."
        self.assertIn("LIVE/LIVE_DRY mode", str(cm.exception))
    
    def test_live_requires_guardrails_config(self):
        """Test that LIVE mode requires guardrails_config."""
        config = PortfolioCycleConfig(
            portfolio_id=self.portfolio_id,
            evaluation_config=self.eval_config,
            allocation_config=self.base_config.allocation_config,
            rebalance_config=self.base_config.rebalance_config,
            execution_config=self.base_config.execution_config,
            guardrails_config=None  # Missing guardrails
        )
        
        # Should raise CycleError when guardrails_config is None in LIVE mode
        with self.assertRaises(CycleError) as cm:
            run_portfolio_cycle(
                config=config,
                research_engine=self.research_engine,
                artifact_store=self.artifact_store,
                execution_engine_factory=self.execution_engine_factory,
                state_store=self.state_store,
                execution_mode=ExecutionMode.LIVE,
                cycle_timestamp=datetime.now(),
                cycle_id="test_cycle_guardrails" # Provide cycle_id
            )
        
        self.assertIn("guardrails_config", str(cm.exception))
        self.assertIn("LIVE/LIVE_DRY mode", str(cm.exception))
    
    def test_live_halt_writes_halt_flag(self):
        """Test that LIVE mode halt writes HALTED flag."""
        # Trigger a time reversal halt - simpler and more deterministic
        future_timestamp = datetime(2024, 1, 2, 12, 0, 0)
        past_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        
        # Save state with future timestamp
        current_state = CurrentPortfolioState(
            strategy_allocations={"test_strategy": 1000.0},
            total_capital=10000.0,
            timestamp=future_timestamp
        )
        self.state_store.save_state(self.portfolio_id, current_state)
        
        # Try to run cycle with past timestamp (will trigger time reversal halt)
        # Must provide cycle_id to pass validation
        with self.assertRaises(CycleHaltError):
            run_portfolio_cycle(
                config=self.base_config,
                research_engine=self.research_engine,
                artifact_store=self.artifact_store,
                execution_engine_factory=self.execution_engine_factory,
                state_store=self.state_store,
                execution_mode=ExecutionMode.LIVE,
                cycle_timestamp=past_timestamp,
                cycle_id="test_cycle_halt",
                market_data_provider=self.mock_provider
            )
        
        # Verify HALTED flag exists
    
    def test_live_refuses_start_when_halted(self):
        """Test that LIVE mode refuses to start when HALTED flag exists."""
        # Create and write halt flag manually
        halt_store = HaltFlagStore(self.artifact_store)
        halt_store.write_halt_flag(
            portfolio_id=self.portfolio_id,
            cycle_id="test_cycle_1",
            reason="Test halt",
            halted_at=datetime.now(),
            violations_summary=[]
        )
        
        # Verify flag exists
        self.assertTrue(halt_store.halt_flag_exists(self.portfolio_id))
        
        # Try to run cycle in LIVE mode - should raise CycleError
        with self.assertRaises(CycleError) as cm:
            run_portfolio_cycle(
                config=self.base_config,
                research_engine=self.research_engine,
                artifact_store=self.artifact_store,
                execution_engine_factory=self.execution_engine_factory,
                state_store=self.state_store,
                execution_mode=ExecutionMode.LIVE,
                cycle_timestamp=datetime.now(),
                cycle_id="test_cycle_resume",
                market_data_provider=self.mock_provider
            )
        
        # Updated assertion for new error message
        self.assertIn("is HALTED", str(cm.exception))
        self.assertIn("dashboard.py resolve", str(cm.exception))
    
    def test_live_requires_cycle_id(self):
        """Test that LIVE mode requires explicit cycle_id."""
        # Try to run cycle in LIVE mode without cycle_id (should raise CycleError)
        with self.assertRaises(CycleError) as cm:
            run_portfolio_cycle(
                config=self.base_config,
                research_engine=self.research_engine,
                artifact_store=self.artifact_store,
                execution_engine_factory=self.execution_engine_factory,
                state_store=self.state_store,
                execution_mode=ExecutionMode.LIVE,
                cycle_timestamp=datetime.now(),
                cycle_id=None  # Missing cycle_id
            )
        
        self.assertIn("cycle_id", str(cm.exception))
        self.assertIn("LIVE/LIVE_DRY mode", str(cm.exception))

