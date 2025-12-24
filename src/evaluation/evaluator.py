"""Strategy evaluation pipeline.

This module provides deterministic evaluation of strategies by:
1. Running backtest
2. Running paper trading session
3. Running divergence analysis
4. Computing evaluation metrics
5. Ranking strategies
"""

import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

from ..engines.simple import SimpleResearchEngine, RawReturns, BacktestResult
from ..core.experiment import Experiment
from ..execution import PaperExecutionEngine, Fill, Order, Position
from ..core.artifacts import ArtifactStore
from ..integration.pipeline import execute_signals_from_raw_returns
from ..analysis.divergence import (
    analyze_backtest_vs_paper,
    DivergenceAnalysis,
    persist_divergence_analysis,
)
from ..core.metrics import Metrics


class EvaluationError(Exception):
    """Error raised when strategy evaluation fails."""
    pass


@dataclass
class EvaluationMetrics:
    """Metrics for evaluating a strategy's execution robustness.
    
    Combines backtest metrics, paper execution metrics, and divergence metrics
    to provide a holistic view of strategy performance.
    
    Attributes:
        backtest_sharpe: Sharpe ratio from backtest
        backtest_total_return: Total return from backtest
        backtest_max_drawdown: Maximum drawdown from backtest
        paper_realized_pnl: Realized PnL from paper trading
        paper_total_return: Total return from paper trading
        divergence_final_equity: Final equity divergence (paper - backtest)
        divergence_max_equity: Maximum equity divergence (absolute)
        divergence_timing_drift_avg: Average timing drift in seconds
        divergence_attribution: Divergence cause attribution counts
        execution_robustness_score: Composite score (0.0 to 1.0)
        
    Note:
        execution_robustness_score is computed from divergence metrics:
        - Lower divergence = higher robustness
        - Penalizes timing drift, price impact, position sizing errors
    """
    
    backtest_sharpe: float
    backtest_total_return: float
    backtest_max_drawdown: float
    paper_realized_pnl: float
    paper_total_return: float
    divergence_final_equity: float
    divergence_max_equity: float
    divergence_timing_drift_avg: float
    divergence_attribution: Dict[str, int]
    execution_robustness_score: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return asdict(self)


@dataclass
class EvaluationResult:
    """Result of a single strategy evaluation.
    
    Attributes:
        strategy_id: Identifier for the strategy/experiment
        experiment_name: Experiment name
        experiment_version: Experiment version
        evaluation_timestamp: When evaluation was performed
        backtest_result: BacktestResult from research engine
        paper_session_id: Paper trading session identifier
        divergence_analysis: DivergenceAnalysis comparing backtest vs paper
        evaluation_metrics: Computed evaluation metrics
        passed: Whether strategy passed evaluation criteria
        failure_reasons: List of reasons if evaluation failed
        
    Note:
        passed is True if all evaluation criteria are met, False otherwise.
        failure_reasons contains human-readable explanations of failures.
    """
    
    strategy_id: str
    experiment_name: str
    experiment_version: str
    evaluation_timestamp: datetime
    backtest_result: BacktestResult
    paper_session_id: str
    divergence_analysis: DivergenceAnalysis
    evaluation_metrics: EvaluationMetrics
    passed: bool
    failure_reasons: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "strategy_id": self.strategy_id,
            "experiment_name": self.experiment_name,
            "experiment_version": self.experiment_version,
            "evaluation_timestamp": self.evaluation_timestamp.isoformat(),
            "backtest_run_id": self.backtest_result.run_id,
            "paper_session_id": self.paper_session_id,
            "divergence_analysis_id": f"{self.backtest_result.run_id}_{self.paper_session_id}",
            "evaluation_metrics": self.evaluation_metrics.to_dict(),
            "passed": self.passed,
            "failure_reasons": self.failure_reasons,
        }


@dataclass
class StrategyEvaluation:
    """Complete strategy evaluation with ranking.
    
    Attributes:
        evaluation_id: Unique identifier for this evaluation run
        evaluation_timestamp: When evaluation was performed
        results: List of evaluation results (one per strategy)
        ranked_results: Results sorted by execution_robustness_score (descending)
        summary: Summary statistics across all strategies
    """
    
    evaluation_id: str
    evaluation_timestamp: datetime
    results: List[EvaluationResult]
    ranked_results: List[EvaluationResult]
    summary: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "evaluation_id": self.evaluation_id,
            "evaluation_timestamp": self.evaluation_timestamp.isoformat(),
            "results": [r.to_dict() for r in self.results],
            "ranked_results": [r.to_dict() for r in self.ranked_results],
            "summary": self.summary,
        }


def _compute_execution_robustness_score(
    divergence_analysis: DivergenceAnalysis,
    backtest_sharpe: float
) -> float:
    """Compute execution robustness score (0.0 to 1.0).
    
    Higher score = more robust execution (lower divergence).
    
    Scoring factors:
    - Equity divergence (lower is better)
    - Timing drift (lower is better)
    - Attribution (fewer causes is better)
    - Backtest Sharpe (higher is better, for normalization)
    
    Args:
        divergence_analysis: DivergenceAnalysis result
        backtest_sharpe: Sharpe ratio from backtest
        
    Returns:
        Score between 0.0 (poor) and 1.0 (excellent)
    """
    metrics = divergence_analysis.metrics
    
    # Normalize equity divergence (as percentage of initial equity)
    # Use absolute max divergence to penalize large deviations
    max_equity_div = abs(metrics.max_equity_divergence)
    # Assume initial equity of 100000 for normalization (in production, pass this)
    normalized_divergence = min(max_equity_div / 100000.0, 1.0)  # Cap at 100%
    
    # Normalize timing drift (penalize delays > 1 hour)
    max_timing_drift = abs(metrics.max_timing_drift_seconds) if metrics.max_timing_drift_seconds else 0.0
    normalized_timing = min(max_timing_drift / 3600.0, 1.0)  # Cap at 1 hour
    
    # Normalize attribution (fewer causes = better)
    total_divergence_points = metrics.total_divergence_points
    if total_divergence_points == 0:
        normalized_attribution = 1.0
    else:
        # Count non-"none" causes
        non_none_causes = sum(
            count for cause, count in metrics.attribution.items()
            if cause != "none"
        )
        normalized_attribution = 1.0 - min(non_none_causes / total_divergence_points, 1.0)
    
    # Combine factors (weighted average)
    robustness = (
        0.4 * (1.0 - normalized_divergence) +  # 40% weight on equity divergence
        0.3 * (1.0 - normalized_timing) +      # 30% weight on timing drift
        0.3 * normalized_attribution            # 30% weight on attribution
    )
    
    # Ensure score is between 0 and 1
    return max(0.0, min(1.0, robustness))


def _compute_evaluation_metrics(
    backtest_result: BacktestResult,
    paper_realized_pnl: float,
    paper_initial_capital: float,
    divergence_analysis: DivergenceAnalysis
) -> EvaluationMetrics:
    """Compute evaluation metrics from backtest, paper, and divergence results.
    
    Args:
        backtest_result: BacktestResult from research engine
        paper_realized_pnl: Realized PnL from paper trading
        paper_initial_capital: Initial capital for paper trading
        divergence_analysis: DivergenceAnalysis result
        
    Returns:
        EvaluationMetrics object
    """
    backtest_metrics = backtest_result.metrics
    
    # Compute paper total return
    paper_total_return = paper_realized_pnl / paper_initial_capital if paper_initial_capital > 0 else 0.0
    
    # Compute execution robustness score
    robustness_score = _compute_execution_robustness_score(
        divergence_analysis,
        backtest_metrics.sharpe_ratio
    )
    
    return EvaluationMetrics(
        backtest_sharpe=backtest_metrics.sharpe_ratio,
        backtest_total_return=backtest_metrics.total_return,
        backtest_max_drawdown=backtest_metrics.max_drawdown,
        paper_realized_pnl=paper_realized_pnl,
        paper_total_return=paper_total_return,
        divergence_final_equity=divergence_analysis.metrics.final_equity_divergence,
        divergence_max_equity=divergence_analysis.metrics.max_equity_divergence,
        divergence_timing_drift_avg=divergence_analysis.metrics.average_timing_drift_seconds,
        divergence_attribution=divergence_analysis.metrics.attribution,
        execution_robustness_score=robustness_score
    )


def _check_evaluation_criteria(
    metrics: EvaluationMetrics,
    min_robustness_score: float = 0.7,
    max_divergence_pct: float = 0.05,  # 5% max equity divergence
    max_timing_drift_seconds: float = 3600.0  # 1 hour max drift
) -> Tuple[bool, List[str]]:
    """Check if strategy passes evaluation criteria.
    
    Args:
        metrics: EvaluationMetrics to check
        min_robustness_score: Minimum robustness score to pass (default: 0.7)
        max_divergence_pct: Maximum equity divergence as percentage (default: 5%)
        max_timing_drift_seconds: Maximum timing drift in seconds (default: 1 hour)
        
    Returns:
        Tuple of (passed: bool, failure_reasons: List[str])
    """
    passed = True
    failure_reasons = []
    
    # Check robustness score
    if metrics.execution_robustness_score < min_robustness_score:
        passed = False
        failure_reasons.append(
            f"Execution robustness score {metrics.execution_robustness_score:.2f} "
            f"below minimum {min_robustness_score:.2f}"
        )
    
    # Check equity divergence (as percentage)
    divergence_pct = abs(metrics.divergence_final_equity) / 100000.0  # Assume 100k initial
    if divergence_pct > max_divergence_pct:
        passed = False
        failure_reasons.append(
            f"Equity divergence {divergence_pct:.2%} exceeds maximum {max_divergence_pct:.2%}"
        )
    
    # Check timing drift
    if abs(metrics.divergence_timing_drift_avg) > max_timing_drift_seconds:
        passed = False
        failure_reasons.append(
            f"Average timing drift {metrics.divergence_timing_drift_avg:.0f}s "
            f"exceeds maximum {max_timing_drift_seconds:.0f}s"
        )
    
    return passed, failure_reasons


def evaluate_strategy(
    strategy_id: str,
    experiment: Experiment,
    inputs: Dict[str, Any],
    research_engine: SimpleResearchEngine,
    execution_engine: PaperExecutionEngine,
    artifact_store: ArtifactStore,
    price_series: Optional[List[float]] = None,
    evaluation_criteria: Optional[Dict[str, Any]] = None,
    light_artifacts: bool = False
) -> EvaluationResult:
    """Evaluate a single strategy by running backtest, paper trading, and divergence analysis.
    
    Process:
    1. Run backtest using research engine
    2. Extract raw returns from backtest
    3. Execute signals in paper trading session
    4. Run divergence analysis
    5. Compute evaluation metrics
    6. Check evaluation criteria
    
    Args:
        strategy_id: Unique identifier for this strategy evaluation
        experiment: Experiment configuration
        inputs: Backtest inputs (start_date, end_date, initial_capital, instrument)
        research_engine: Research engine for backtesting
        execution_engine: Paper execution engine
        artifact_store: Artifact store for persistence
        price_series: Optional price series for execution (one per day)
        evaluation_criteria: Optional criteria overrides
        
    Returns:
        EvaluationResult with evaluation metrics and pass/fail status
        
    Raises:
        EvaluationError: If evaluation fails
        
    Example:
        >>> result = evaluate_strategy(
        ...     strategy_id="strat_1",
        ...     experiment=experiment,
        ...     inputs={"start_date": "2024-01-01", "end_date": "2024-12-31", ...},
        ...     research_engine=engine,
        ...     execution_engine=paper_engine,
        ...     artifact_store=store
        ... )
        >>> print(f"Strategy passed: {result.passed}")
        >>> print(f"Robustness score: {result.evaluation_metrics.execution_robustness_score}")
    """
    try:
        run_id = f"{strategy_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Step 1: Run backtest
        backtest_result = research_engine.run_backtest(experiment, run_id, inputs, light_artifacts=light_artifacts)
        
        # Step 2: Load raw returns from artifacts
        # Note: raw_returns.json is always written (even in light mode) because it's required for evaluation
        raw_returns_data = artifact_store.retrieve(run_id, "raw_returns.json")
        if not raw_returns_data:
            raise EvaluationError(f"Failed to retrieve raw returns for run {run_id}")
        
        raw_returns_dict = json.loads(raw_returns_data.decode('utf-8'))
        raw_returns = RawReturns(
            dates=raw_returns_dict["dates"],
            returns=raw_returns_dict["returns"],
            initial_capital=raw_returns_dict["initial_capital"],
            final_value=raw_returns_dict["final_value"]
        )
        
        # Step 3: Execute signals in paper trading
        instrument = inputs["instrument"]
        strategy_type = inputs.get("strategy_type", "buy_hold")
        strategy_params = experiment.config.get("strategy_params", {})
        execution_results = execute_signals_from_raw_returns(
            raw_returns=raw_returns,
            instrument=instrument,
            execution_engine=execution_engine,
            price_series=price_series,
            strategy_type=strategy_type,
            strategy_params=strategy_params
        )
        
        paper_session_id = execution_engine.session_id
        
        # Step 4: Collect paper execution data
        fills = []
        for order in execution_results["orders_created"]:
            order_fills = execution_engine.get_fills(order.id)
            fills.extend(order_fills)
        
        orders = execution_engine.list_orders()
        
        # Build positions by date from fills
        # Track position state as we iterate through fills chronologically
        positions_by_date: Dict[datetime.date, Position] = {}
        current_position = None
        for fill in sorted(fills, key=lambda f: f.timestamp if f.timestamp else datetime.min):
            if fill.timestamp:
                fill_date = fill.timestamp.date()
                # Get position after this fill
                current_position = execution_engine.get_position(fill.instrument)
                if current_position:
                    positions_by_date[fill_date] = current_position
        
        # Get latest position for realized PnL
        latest_position = execution_engine.get_position(instrument)
        paper_realized_pnl = latest_position.realized_pnl if latest_position else 0.0
        
        # Step 5: Run divergence analysis
        divergence_analysis = analyze_backtest_vs_paper(
            backtest_run_id=run_id,
            raw_returns=raw_returns,
            paper_session_id=paper_session_id,
            fills=fills,
            orders=orders,
            positions_by_date=positions_by_date
        )
        
        # Step 6: Compute evaluation metrics
        initial_capital = inputs.get("initial_capital", raw_returns.initial_capital)
        evaluation_metrics = _compute_evaluation_metrics(
            backtest_result=backtest_result,
            paper_realized_pnl=paper_realized_pnl,
            paper_initial_capital=initial_capital,
            divergence_analysis=divergence_analysis
        )
        
        # Step 7: Check evaluation criteria
        criteria = evaluation_criteria or {}
        passed, failure_reasons = _check_evaluation_criteria(
            metrics=evaluation_metrics,
            min_robustness_score=criteria.get("min_robustness_score", 0.7),
            max_divergence_pct=criteria.get("max_divergence_pct", 0.05),
            max_timing_drift_seconds=criteria.get("max_timing_drift_seconds", 3600.0)
        )
        
        return EvaluationResult(
            strategy_id=strategy_id,
            experiment_name=experiment.name,
            experiment_version=experiment.version,
            evaluation_timestamp=datetime.now(),
            backtest_result=backtest_result,
            paper_session_id=paper_session_id,
            divergence_analysis=divergence_analysis,
            evaluation_metrics=evaluation_metrics,
            passed=passed,
            failure_reasons=failure_reasons
        )
        
    except Exception as e:
        raise EvaluationError(f"Failed to evaluate strategy {strategy_id}: {e}") from e


def compare_strategies(
    evaluation_results: List[EvaluationResult]
) -> StrategyEvaluation:
    """Compare and rank multiple strategy evaluations.
    
    Args:
        evaluation_results: List of evaluation results to compare
        
    Returns:
        StrategyEvaluation with ranked results and summary
    """
    if not evaluation_results:
        raise EvaluationError("Cannot compare empty list of strategies")
    
    # Rank by execution robustness score (descending)
    ranked_results = sorted(
        evaluation_results,
        key=lambda r: r.evaluation_metrics.execution_robustness_score,
        reverse=True
    )
    
    # Compute summary statistics
    robustness_scores = [r.evaluation_metrics.execution_robustness_score for r in evaluation_results]
    backtest_sharpes = [r.evaluation_metrics.backtest_sharpe for r in evaluation_results]
    passed_count = sum(1 for r in evaluation_results if r.passed)
    
    summary = {
        "total_strategies": len(evaluation_results),
        "passed_count": passed_count,
        "failed_count": len(evaluation_results) - passed_count,
        "average_robustness_score": sum(robustness_scores) / len(robustness_scores),
        "max_robustness_score": max(robustness_scores),
        "min_robustness_score": min(robustness_scores),
        "average_backtest_sharpe": sum(backtest_sharpes) / len(backtest_sharpes),
        "top_strategy_id": ranked_results[0].strategy_id if ranked_results else None,
    }
    
    evaluation_id = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    return StrategyEvaluation(
        evaluation_id=evaluation_id,
        evaluation_timestamp=datetime.now(),
        results=evaluation_results,
        ranked_results=ranked_results,
        summary=summary
    )


def persist_evaluation(
    evaluation: StrategyEvaluation,
    artifact_store: ArtifactStore,
    light_artifacts: bool = False
) -> str:
    """Persist strategy evaluation to artifact store.
    
    Args:
        evaluation: StrategyEvaluation to persist
        artifact_store: ArtifactStore instance
        
    Returns:
        Evaluation identifier
    """
    if light_artifacts:
        return evaluation.evaluation_id
    try:
        evaluation_json = json.dumps(evaluation.to_dict(), indent=2).encode('utf-8')
        artifact_store.store(
            evaluation.evaluation_id,
            "evaluation_report.json",
            evaluation_json
        )
        return evaluation.evaluation_id
    except Exception as e:
        raise EvaluationError(f"Failed to persist evaluation: {e}") from e

