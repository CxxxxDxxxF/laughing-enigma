"""Off-hours optimization runner.

This module runs backtests and strategy optimization during market closed periods.
It leverages the existing batch evaluation system to test parameter combinations
and identify improvements.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
import json
import time

from ..evaluation.batch import (
    BatchEvaluationConfig,
    StrategyConfig,
    run_batch_evaluation,
    StrategyEvaluation,
)
from ..engines.simple import SimpleResearchEngine
from ..core.artifacts import ArtifactStore, LocalArtifactStore
from ..execution import PaperExecutionEngine
from ..core.logger import logger


@dataclass
class OptimizationResult:
    """Result of an off-hours optimization run.
    
    Attributes:
        batch_id: Unique identifier for the optimization batch
        started_at: When optimization started
        completed_at: When optimization finished
        strategies_tested: Number of strategy configurations tested
        best_strategy_id: ID of the best performing strategy
        best_sharpe: Best Sharpe ratio achieved
        improvement_pct: Percentage improvement over baseline (if any)
        results_path: Path to detailed results
    """
    batch_id: str
    started_at: datetime
    completed_at: datetime
    strategies_tested: int
    best_strategy_id: Optional[str] = None
    best_sharpe: float = 0.0
    improvement_pct: float = 0.0
    results_path: Optional[str] = None
    metric_name: str = "sharpe"
    best_metric_value: float = 0.0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "strategies_tested": self.strategies_tested,
            "best_strategy_id": self.best_strategy_id,
            "metric_name": self.metric_name,
            "best_metric_value": self.best_metric_value,
            "improvement_pct": self.improvement_pct,
            "results_path": self.results_path,
            "errors": self.errors,
        }


# Default parameter grids for optimization
DEFAULT_PARAMETER_GRIDS = {
    "dual_momentum": {
        "lookback_days": [63, 126, 189, 252],  # 3mo, 6mo, 9mo, 12mo
        "threshold": [-0.02, 0.0, 0.02, 0.05],  # Various trend thresholds
    }
}


def create_optimization_config(
    strategy_name: str,
    instrument: str = "SPY",
    parameter_grid: Optional[Dict[str, List[Any]]] = None
) -> BatchEvaluationConfig:
    """Create a batch evaluation config for optimization.
    
    Args:
        strategy_name: Name of the strategy to optimize
        instrument: Target instrument
        parameter_grid: Optional custom parameter grid
        
    Returns:
        BatchEvaluationConfig for batch evaluation
    """
    grid = parameter_grid or DEFAULT_PARAMETER_GRIDS.get(strategy_name, {})
    
    # Defaults for inputs
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    base_config = StrategyConfig(
        strategy_id=f"{strategy_name}_opt",
        experiment_name=strategy_name,
        experiment_version="opt_v1",
        experiment_config={},
        inputs={
            "instrument": instrument,
            "strategy_id": strategy_name,
            "strategy_type": strategy_name,
            "initial_capital": 100000.0,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        },
        description=f"Optimization run for {strategy_name}"
    )
    
    return BatchEvaluationConfig(
        strategies=[base_config],
        parameter_grid=grid,
    )


def run_off_hours_optimization(
    portfolio_id: str,
    strategy_name: str = "dual_momentum",
    artifact_store: Optional[ArtifactStore] = None,
    max_duration_seconds: float = 3600 * 4,  # 4 hours default
    parameter_grid: Optional[Dict[str, List[Any]]] = None,
    execution_engine_factory: Optional[Callable[[], PaperExecutionEngine]] = None,
) -> OptimizationResult:
    """Run off-hours optimization for a strategy.
    
    This function:
    1. Creates optimization configs with parameter grid
    2. Runs batch evaluation on each combination
    3. Identifies best performing configuration
    4. Persists results for review
    
    Args:
        portfolio_id: Portfolio identifier (for namespacing results)
        strategy_name: Strategy to optimize
        artifact_store: Optional artifact store (creates default if not provided)
        max_duration_seconds: Maximum time to run optimization
        parameter_grid: Optional custom parameter grid
        execution_engine_factory: Optional factory for execution engine
        
    Returns:
        OptimizationResult with summary of findings
    """
    started_at = datetime.now()
    deadline = started_at + timedelta(seconds=max_duration_seconds)
    batch_id = f"opt_{portfolio_id}_{started_at.strftime('%Y%m%d_%H%M%S')}"
    
    logger.info(f"Starting off-hours optimization: {batch_id}")
    logger.info(f"Strategy: {strategy_name}, Deadline: {deadline}")
    
    # Setup
    if artifact_store is None:
        artifact_store = LocalArtifactStore(base_path=Path("data/artifacts"))
    
    if execution_engine_factory is None:
        def create_engine():
            return PaperExecutionEngine(instrument="SPY")
        execution_engine_factory = create_engine
    
    # Create optimization config
    opt_config = create_optimization_config(
        strategy_name=strategy_name,
        parameter_grid=parameter_grid
    )
    
    # Create research engine
    research_engine = SimpleResearchEngine(artifact_store=artifact_store)
    
    errors = []
    best_strategy_id = None
    best_sharpe = -999.0
    strategies_tested = 0
    
    try:
        # Check deadline
        if datetime.now() >= deadline:
            logger.warning("Optimization deadline reached before starting. Skipping.")
            return OptimizationResult(
                batch_id=batch_id,
                started_at=started_at,
                completed_at=datetime.now(),
                strategies_tested=0,
                errors=["Deadline reached before starting"]
            )
        
        # Run batch evaluation
        evaluation = run_batch_evaluation(
            config=opt_config,
            research_engine=research_engine,
            artifact_store=artifact_store,
            execution_engine_factory=execution_engine_factory,
            batch_id=batch_id
        )
        
        strategies_tested = len(evaluation.results)
        
        # Find best result
        if evaluation.results:
            best_result = max(
                evaluation.results,
                key=lambda r: r.evaluation_metrics.sharpe_ratio if r.evaluation_metrics else -999
            )
            best_strategy_id = best_result.strategy_id
            best_sharpe = best_result.evaluation_metrics.sharpe_ratio if best_result.evaluation_metrics else 0.0
        
        logger.info(f"Optimization complete. Tested {strategies_tested} configurations.")
        logger.info(f"Best: {best_strategy_id} (Sharpe: {best_sharpe:.3f})")
        
    except Exception as e:
        logger.error(f"Optimization error: {e}")
        errors.append(str(e))
    
    completed_at = datetime.now()
    results_path = f"data/artifacts/runs/{batch_id}/batch_summary.json"
    
    result = OptimizationResult(
        batch_id=batch_id,
        started_at=started_at,
        completed_at=completed_at,
        strategies_tested=strategies_tested,
        best_strategy_id=best_strategy_id,
        best_sharpe=best_sharpe,
        metric_name="sharpe",
        best_metric_value=best_sharpe,
        results_path=results_path,
        errors=errors
    )
    
    # Persist optimization result summary
    try:
        summary_json = json.dumps(result.to_dict(), indent=2).encode('utf-8')
        artifact_store.store(
            f"optimization/{portfolio_id}",
            f"{batch_id}_summary.json",
            summary_json
        )
    except Exception as e:
        logger.error(f"Failed to persist optimization summary: {e}")
    
    return result
