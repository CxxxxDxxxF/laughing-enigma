"""Batch evaluation harness for testing multiple strategies consistently.

This module provides a deterministic batch evaluation system that can run
many strategy evaluations and produce a single aggregated report.

Determinism guarantees:
- Same config → same evaluation order
- Same inputs → same outputs
- Isolated paper sessions per evaluation (no cross-contamination)
- Deterministic parameter grid expansion
"""

import json
import sys
import itertools
import argparse
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from .evaluator import (
    evaluate_strategy,
    compare_strategies,
    EvaluationResult,
    StrategyEvaluation,
    EvaluationError,
)
from ..engines.simple import SimpleResearchEngine
from ..core.experiment import Experiment
from ..core.artifacts import ArtifactStore
from ..execution import PaperExecutionEngine


class BatchEvaluationError(Exception):
    """Error raised when batch evaluation fails."""
    pass


@dataclass
class StrategyConfig:
    """Configuration for a single strategy to evaluate.
    
    Attributes:
        strategy_id: Unique identifier for this strategy
        experiment_name: Name of experiment
        experiment_version: Version of experiment
        experiment_config: Experiment configuration dict
        inputs: Backtest inputs (start_date, end_date, initial_capital, instrument)
        description: Optional description
    """
    
    strategy_id: str
    experiment_name: str
    experiment_version: str
    experiment_config: Dict[str, Any]
    inputs: Dict[str, Any]
    description: Optional[str] = None
    
    def to_experiment(self) -> Experiment:
        """Convert to Experiment object.
        
        Returns:
            Experiment instance
        """
        return Experiment(
            name=self.experiment_name,
            version=self.experiment_version,
            config=self.experiment_config,
            created_at=datetime.now(),
            description=self.description
        )


@dataclass
class BatchEvaluationConfig:
    """Configuration for batch evaluation.
    
    Attributes:
        strategies: List of strategy configurations
        parameter_grid: Optional parameter grid for input overrides
                       Format: {"parameter_name": [value1, value2, ...]}
        evaluation_criteria: Optional evaluation criteria overrides
        price_series: Optional price series (list of floats)
                     If None, prices are not provided (orders won't execute)
        batch_id: Optional batch identifier (auto-generated if not provided)
        
    Note:
        parameter_grid creates a cartesian product of parameter combinations.
        Each combination is evaluated as a separate strategy run.
    """
    
    strategies: List[StrategyConfig]
    parameter_grid: Optional[Dict[str, List[Any]]] = None
    evaluation_criteria: Optional[Dict[str, Any]] = None
    price_series: Optional[List[float]] = None
    batch_id: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BatchEvaluationConfig':
        """Load config from dictionary.
        
        Args:
            data: Dictionary containing config data
            
        Returns:
            BatchEvaluationConfig instance
            
        Raises:
            BatchEvaluationError: If config is invalid
        """
        try:
            strategies = [
                StrategyConfig(
                    strategy_id=s["strategy_id"],
                    experiment_name=s["experiment_name"],
                    experiment_version=s["experiment_version"],
                    experiment_config=s["experiment_config"],
                    inputs=s["inputs"],
                    description=s.get("description")
                )
                for s in data["strategies"]
            ]
            
            return cls(
                strategies=strategies,
                parameter_grid=data.get("parameter_grid"),
                evaluation_criteria=data.get("evaluation_criteria"),
                price_series=data.get("price_series"),
                batch_id=data.get("batch_id")
            )
        except KeyError as e:
            raise BatchEvaluationError(f"Missing required config field: {e}") from e
        except Exception as e:
            raise BatchEvaluationError(f"Invalid config format: {e}") from e
    
    @classmethod
    def from_json_file(cls, config_path: Path) -> 'BatchEvaluationConfig':
        """Load config from JSON file.
        
        Args:
            config_path: Path to JSON config file
            
        Returns:
            BatchEvaluationConfig instance
            
        Raises:
            BatchEvaluationError: If file cannot be read or parsed
        """
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except FileNotFoundError:
            raise BatchEvaluationError(f"Config file not found: {config_path}")
        except json.JSONDecodeError as e:
            raise BatchEvaluationError(f"Invalid JSON in config file: {e}") from e
        except Exception as e:
            raise BatchEvaluationError(f"Failed to load config: {e}") from e
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize config to dictionary."""
        return {
            "strategies": [
                {
                    "strategy_id": s.strategy_id,
                    "experiment_name": s.experiment_name,
                    "experiment_version": s.experiment_version,
                    "experiment_config": s.experiment_config,
                    "inputs": s.inputs,
                    "description": s.description,
                }
                for s in self.strategies
            ],
            "parameter_grid": self.parameter_grid,
            "evaluation_criteria": self.evaluation_criteria,
            "price_series": self.price_series,
            "batch_id": self.batch_id,
        }


def _expand_parameter_grid(
    base_inputs: Dict[str, Any],
    parameter_grid: Dict[str, List[Any]]
) -> List[Dict[str, Any]]:
    """Expand parameter grid into list of input combinations.
    
    Creates cartesian product of all parameter values.
    
    Args:
        base_inputs: Base inputs dict
        parameter_grid: Parameter grid specification
        
    Returns:
        List of input dicts, one per combination
        
    Example:
        base = {"a": 1, "b": 2}
        grid = {"a": [10, 20], "c": [100, 200]}
        Returns:
        [
            {"a": 10, "b": 2, "c": 100},
            {"a": 10, "b": 2, "c": 200},
            {"a": 20, "b": 2, "c": 100},
            {"a": 20, "b": 2, "c": 200},
        ]
    """
    if not parameter_grid:
        return [base_inputs.copy()]
    
    # Get parameter names and value lists
    param_names = list(parameter_grid.keys())
    param_values = [parameter_grid[name] for name in param_names]
    
    # Generate cartesian product
    combinations = []
    for values in itertools.product(*param_values):
        # Create new inputs dict with overrides
        new_inputs = base_inputs.copy()
        for name, value in zip(param_names, values):
            new_inputs[name] = value
        combinations.append(new_inputs)
    
    return combinations


def _generate_strategy_combinations(
    config: BatchEvaluationConfig
) -> List[tuple[str, StrategyConfig, Dict[str, Any]]]:
    """Generate all strategy × parameter combinations to evaluate.
    
    Args:
        config: Batch evaluation config
        
    Returns:
        List of tuples: (effective_strategy_id, strategy_config, inputs)
        
    Note:
        effective_strategy_id includes parameter grid suffix if applicable.
    """
    combinations = []
    
    for strategy in config.strategies:
        # Expand parameter grid for this strategy
        input_combinations = _expand_parameter_grid(
            strategy.inputs,
            config.parameter_grid or {}
        )
        
        for i, inputs in enumerate(input_combinations):
            # Generate effective strategy ID
            if len(input_combinations) > 1:
                effective_id = f"{strategy.strategy_id}_param_{i}"
            else:
                effective_id = strategy.strategy_id
            
            combinations.append((effective_id, strategy, inputs))
    
    return combinations


def run_batch_evaluation(
    config: BatchEvaluationConfig,
    research_engine: SimpleResearchEngine,
    artifact_store: ArtifactStore,
    execution_engine_factory: Callable[[], PaperExecutionEngine],
    batch_id: Optional[str] = None,
    light_artifacts: bool = False
) -> StrategyEvaluation:
    """Run batch evaluation of multiple strategies.
    
    Process:
    1. Generate all strategy × parameter combinations
    2. For each combination:
       a. Create isolated paper session
       b. Run evaluation
       c. Collect result
    3. Aggregate results via compare_strategies
    4. Persist batch artifacts
    
    Determinism guarantees:
    - Combinations are processed in deterministic order
    - Each evaluation uses isolated paper session
    - Same config → same results
    
    Args:
        config: Batch evaluation configuration
        research_engine: Research engine for backtesting
        artifact_store: Artifact store for persistence
        execution_engine_factory: Factory function that creates new PaperExecutionEngine
                                 (must create isolated sessions)
        batch_id: Optional batch identifier (auto-generated if not provided)
        
    Returns:
        StrategyEvaluation with all results aggregated and ranked
        
    Raises:
        BatchEvaluationError: If batch evaluation fails
        
    Example:
        >>> def create_engine():
        ...     return PaperExecutionEngine(instrument="AAPL", artifact_store=store)
        >>> evaluation = run_batch_evaluation(
        ...     config=config,
        ...     research_engine=engine,
        ...     artifact_store=store,
        ...     execution_engine_factory=create_engine
        ... )
        >>> print(f"Top strategy: {evaluation.ranked_results[0].strategy_id}")
    """
    if batch_id is None:
        batch_id = config.batch_id or f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Generate all combinations
    combinations = _generate_strategy_combinations(config)
    
    if not combinations:
        raise BatchEvaluationError("No strategy combinations to evaluate")
    
    evaluation_results: List[EvaluationResult] = []
    errors: List[Dict[str, Any]] = []
    
    # Evaluate each combination
    for effective_id, strategy, inputs in combinations:
        try:
            # Create isolated execution engine for this evaluation
            execution_engine = execution_engine_factory()
            
            # Create experiment
            experiment = strategy.to_experiment()
            
            # Run evaluation
            result = evaluate_strategy(
                strategy_id=effective_id,
                experiment=experiment,
                inputs=inputs,
                research_engine=research_engine,
                execution_engine=execution_engine,
                artifact_store=artifact_store,
                price_series=config.price_series,
                evaluation_criteria=config.evaluation_criteria,
                light_artifacts=light_artifacts
            )
            
            evaluation_results.append(result)
            
        except Exception as e:
            error_info = {
                "strategy_id": effective_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            errors.append(error_info)
            
            # Continue with other evaluations even if one fails
            # This ensures batch evaluation is resilient
    
    if not evaluation_results:
        raise BatchEvaluationError(
            f"All evaluations failed. Errors: {errors}"
        )
    
    # Aggregate results
    evaluation = compare_strategies(evaluation_results)
    
    # Add batch metadata
    evaluation.evaluation_id = batch_id
    
    # Persist batch artifacts
    _persist_batch_artifacts(
        batch_id=batch_id,
        evaluation=evaluation,
        config=config,
        errors=errors,
        artifact_store=artifact_store,
        light_artifacts=light_artifacts
    )
    
    return evaluation


def _persist_batch_artifacts(
    batch_id: str,
    evaluation: StrategyEvaluation,
    config: BatchEvaluationConfig,
    errors: List[Dict[str, Any]],
    artifact_store: ArtifactStore,
    light_artifacts: bool = False
) -> None:
    """Persist batch evaluation artifacts.
    
    Persists:
    - batch_summary.json: Overall results and ranking
    - results_index.json: List of evaluation IDs, strategies, pass/fail
    
    Args:
        batch_id: Batch identifier
        evaluation: StrategyEvaluation result
        config: Batch config used
        errors: List of errors encountered
        artifact_store: Artifact store
    """
    # Batch summary
    batch_summary = {
        "batch_id": batch_id,
        "evaluation_timestamp": evaluation.evaluation_timestamp.isoformat(),
        "total_strategies": evaluation.summary["total_strategies"],
        "passed_count": evaluation.summary["passed_count"],
        "failed_count": evaluation.summary["failed_count"],
        "average_robustness_score": evaluation.summary["average_robustness_score"],
        "top_strategy_id": evaluation.summary["top_strategy_id"],
        "ranking": [
            {
                "rank": i + 1,
                "strategy_id": r.strategy_id,
                "robustness_score": r.evaluation_metrics.execution_robustness_score,
                "passed": r.passed,
            }
            for i, r in enumerate(evaluation.ranked_results)
        ],
        "errors": errors,
    }
    
    if not light_artifacts:
        batch_summary_json = json.dumps(batch_summary, indent=2).encode('utf-8')
        artifact_store.store(batch_id, "batch_summary.json", batch_summary_json)
        
        # Results index
        results_index = {
            "batch_id": batch_id,
            "evaluation_timestamp": evaluation.evaluation_timestamp.isoformat(),
            "results": [
                {
                    "strategy_id": r.strategy_id,
                    "experiment_name": r.experiment_name,
                    "experiment_version": r.experiment_version,
                    "backtest_run_id": r.backtest_result.run_id,
                    "paper_session_id": r.paper_session_id,
                    "passed": r.passed,
                    "robustness_score": r.evaluation_metrics.execution_robustness_score,
                    "failure_reasons": r.failure_reasons,
                }
                for r in evaluation.results
            ],
        }
        
        results_index_json = json.dumps(results_index, indent=2).encode('utf-8')
        artifact_store.store(batch_id, "results_index.json", results_index_json)
        
        # Full evaluation (for detailed analysis)
        from .evaluator import persist_evaluation
        persist_evaluation(evaluation, artifact_store, light_artifacts=light_artifacts)


def main():
    """CLI entrypoint for batch evaluation.
    
    Usage:
        python -m src.evaluation.batch --config <config_path>
    """
    parser = argparse.ArgumentParser(
        description="Run batch strategy evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example config.json:
{
  "strategies": [
    {
      "strategy_id": "strat_1",
      "experiment_name": "momentum",
      "experiment_version": "v1",
      "experiment_config": {},
      "inputs": {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "initial_capital": 100000,
        "instrument": "AAPL"
      }
    }
  ],
  "parameter_grid": {
    "initial_capital": [100000, 200000]
  },
  "evaluation_criteria": {
    "min_robustness_score": 0.7
  },
  "price_series": [150.0, 151.0, ...]
}
        """
    )
    
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to JSON config file"
    )
    
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("./artifacts"),
        help="Directory for artifacts (default: ./artifacts)"
    )
    
    args = parser.parse_args()
    
    try:
        # Load config
        config = BatchEvaluationConfig.from_json_file(args.config)
        
        # Create artifact store
        from ..core.artifacts import LocalArtifactStore
        artifact_store = LocalArtifactStore(args.artifacts_dir)
        
        # Create research engine
        research_engine = SimpleResearchEngine(artifact_store=artifact_store)
        
        # Create execution engine factory
        # Extract instrument from first strategy (assumes single instrument batch)
        if not config.strategies:
            raise BatchEvaluationError("Config must contain at least one strategy")
        
        first_strategy = config.strategies[0]
        instrument = first_strategy.inputs.get("instrument", "UNKNOWN")
        
        def create_engine():
            return PaperExecutionEngine(
                instrument=instrument,
                artifact_store=artifact_store
            )
        
        # Run batch evaluation
        evaluation = run_batch_evaluation(
            config=config,
            research_engine=research_engine,
            artifact_store=artifact_store,
            execution_engine_factory=create_engine
        )
        
        # Print summary
        print(f"Batch evaluation complete: {evaluation.evaluation_id}")
        print(f"Total strategies: {evaluation.summary['total_strategies']}")
        print(f"Passed: {evaluation.summary['passed_count']}")
        print(f"Failed: {evaluation.summary['failed_count']}")
        print(f"Top strategy: {evaluation.summary['top_strategy_id']}")
        print(f"Average robustness: {evaluation.summary['average_robustness_score']:.2f}")
        
        sys.exit(0)
        
    except BatchEvaluationError as e:
        print(f"Batch evaluation error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

