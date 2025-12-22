"""Tests for allocator ExecutionMode enforcement."""

import sys
from pathlib import Path
from datetime import datetime
from unittest import TestCase

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.allocation.allocator import (
    allocate_capital,
    AllocationConfig,
    AllocationError,
)
from src.evaluation.batch import StrategyEvaluation, EvaluationResult, EvaluationMetrics
from src.lifecycle.runner import ExecutionMode


class TestAllocatorExecutionMode(TestCase):
    """Test allocator ExecutionMode enforcement."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create minimal evaluation
        self.evaluation = StrategyEvaluation(
            evaluation_id="test_eval",
            timestamp=datetime.now(),
            results=[
                EvaluationResult(
                    strategy_id="test_strategy",
                    experiment_name="test",
                    experiment_version="v1",
                    evaluation_metrics=EvaluationMetrics(
                        total_return=0.1,
                        sharpe_ratio=1.0,
                        max_drawdown=0.05,
                        execution_robustness_score=0.8
                    ),
                    passed=True
                )
            ]
        )
        self.config = AllocationConfig(
            total_capital=100000.0,
            top_n_strategies=1,
            allocation_method="equal"
        )
    
    def test_live_requires_allocation_timestamp(self):
        """Test that LIVE mode requires explicit allocation_timestamp."""
        with self.assertRaises(AllocationError) as cm:
            allocate_capital(
                evaluation=self.evaluation,
                config=self.config,
                allocation_id="test_alloc",
                allocation_timestamp=None,  # Missing timestamp
                execution_mode=ExecutionMode.LIVE
            )
        
        self.assertIn("allocation_timestamp", str(cm.exception))
        self.assertIn("LIVE mode", str(cm.exception))
    
    def test_live_requires_allocation_id(self):
        """Test that LIVE mode requires explicit allocation_id."""
        with self.assertRaises(AllocationError) as cm:
            allocate_capital(
                evaluation=self.evaluation,
                config=self.config,
                allocation_id=None,  # Missing ID
                allocation_timestamp=datetime.now(),
                execution_mode=ExecutionMode.LIVE
            )
        
        self.assertIn("allocation_id", str(cm.exception))
        self.assertIn("LIVE mode", str(cm.exception))

