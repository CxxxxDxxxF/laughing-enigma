"""Portfolio lifecycle runner.

This module orchestrates the complete portfolio lifecycle:
1. Evaluate strategies (batch evaluation)
2. Allocate capital across top strategies
3. Plan rebalance from current state to target allocations
4. Execute rebalance plan through paper execution engine

This is pure orchestration - no new business logic, only wiring existing components.

Determinism guarantees:
- Same configs + same data → same cycle result
- No background state
- No mutable globals
- Deterministic execution order
"""

import json
import sys
import argparse
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from ..evaluation.batch import (
    BatchEvaluationConfig,
    run_batch_evaluation,
    StrategyEvaluation,
)
from ..allocation.allocator import (
    AllocationConfig,
    allocate_capital,
    AllocationResult,
)
from ..rebalance.planner import (
    RebalanceConfig,
    plan_rebalance,
    RebalancePlan,
    CurrentPortfolioState,
)
from ..rebalance.executor import (
    RebalanceSignalMapper,
    execute_rebalance_plan,
    RebalanceExecutionResult,
)
from ..engines.simple import SimpleResearchEngine
from ..core.artifacts import ArtifactStore, LocalArtifactStore
from ..execution import PaperExecutionEngine


class CycleError(Exception):
    """Error raised when portfolio cycle execution fails."""
    pass


@dataclass
class PortfolioCycleConfig:
    """Configuration for a complete portfolio cycle.
    
    This config contains all sub-configs needed to run a full cycle:
    evaluation → allocation → rebalance → execution
    
    Attributes:
        evaluation_config: Batch evaluation configuration
        allocation_config: Capital allocation configuration
        rebalance_config: Rebalance planning configuration
        execution_config: Rebalance execution configuration
            - price_by_strategy_or_instrument: Dict[str, float] - prices for execution
            - rounding_method: str - rounding method ("floor", "round", "ceil")
            - min_quantity: float - minimum quantity
        current_state: Current portfolio state (None = assume flat/empty)
        cycle_id: Optional cycle identifier (auto-generated if not provided)
    """
    
    evaluation_config: BatchEvaluationConfig
    allocation_config: AllocationConfig
    rebalance_config: RebalanceConfig
    execution_config: Dict[str, Any]
    current_state: Optional[CurrentPortfolioState] = None
    cycle_id: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PortfolioCycleConfig':
        """Load config from dictionary.
        
        Args:
            data: Dictionary containing config data
            
        Returns:
            PortfolioCycleConfig instance
            
        Raises:
            CycleError: If config is invalid
        """
        try:
            # Import here to avoid circular dependencies
            from ..evaluation.batch import BatchEvaluationConfig
            from ..allocation.allocator import AllocationConfig
            from ..rebalance.planner import RebalanceConfig, CurrentPortfolioState
            
            eval_config = BatchEvaluationConfig.from_dict(data["evaluation_config"])
            
            alloc_data = data["allocation_config"]
            alloc_config = AllocationConfig(
                total_capital=alloc_data["total_capital"],
                top_n_strategies=alloc_data.get("top_n_strategies"),
                min_robustness_score=alloc_data.get("min_robustness_score", 0.0),
                max_allocation_per_strategy=alloc_data.get("max_allocation_per_strategy", 1.0),
                min_allocation_per_strategy=alloc_data.get("min_allocation_per_strategy", 0.0),
                allocation_method=alloc_data.get("allocation_method", "robustness_weighted"),
                max_total_leverage=alloc_data.get("max_total_leverage", 1.0),
                require_all_passed=alloc_data.get("require_all_passed", False),
            )
            
            rebalance_data = data["rebalance_config"]
            rebalance_config = RebalanceConfig(
                rebalance_threshold_pct=rebalance_data.get("rebalance_threshold_pct", 0.05),
                max_turnover_pct=rebalance_data.get("max_turnover_pct", 1.0),
                min_trade_size=rebalance_data.get("min_trade_size", 0.0),
                allow_partial_rebalance=rebalance_data.get("allow_partial_rebalance", True),
            )
            
            # Current state
            current_state = None
            if "current_state" in data and data["current_state"]:
                state_data = data["current_state"]
                current_state = CurrentPortfolioState(
                    strategy_allocations=state_data["strategy_allocations"],
                    total_capital=state_data["total_capital"],
                    timestamp=datetime.fromisoformat(state_data["timestamp"]),
                )
            
            return cls(
                evaluation_config=eval_config,
                allocation_config=alloc_config,
                rebalance_config=rebalance_config,
                execution_config=data["execution_config"],
                current_state=current_state,
                cycle_id=data.get("cycle_id"),
            )
        except KeyError as e:
            raise CycleError(f"Missing required config field: {e}") from e
        except Exception as e:
            raise CycleError(f"Invalid config format: {e}") from e
    
    @classmethod
    def from_json_file(cls, config_path: Path) -> 'PortfolioCycleConfig':
        """Load config from JSON file.
        
        Args:
            config_path: Path to JSON config file
            
        Returns:
            PortfolioCycleConfig instance
            
        Raises:
            CycleError: If file cannot be read or parsed
        """
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except FileNotFoundError:
            raise CycleError(f"Config file not found: {config_path}")
        except json.JSONDecodeError as e:
            raise CycleError(f"Invalid JSON in config file: {e}") from e
        except Exception as e:
            raise CycleError(f"Failed to load config: {e}") from e
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize config to dictionary."""
        return {
            "evaluation_config": self.evaluation_config.to_dict(),
            "allocation_config": {
                "total_capital": self.allocation_config.total_capital,
                "top_n_strategies": self.allocation_config.top_n_strategies,
                "min_robustness_score": self.allocation_config.min_robustness_score,
                "max_allocation_per_strategy": self.allocation_config.max_allocation_per_strategy,
                "min_allocation_per_strategy": self.allocation_config.min_allocation_per_strategy,
                "allocation_method": self.allocation_config.allocation_method,
                "max_total_leverage": self.allocation_config.max_total_leverage,
                "require_all_passed": self.allocation_config.require_all_passed,
            },
            "rebalance_config": {
                "rebalance_threshold_pct": self.rebalance_config.rebalance_threshold_pct,
                "max_turnover_pct": self.rebalance_config.max_turnover_pct,
                "min_trade_size": self.rebalance_config.min_trade_size,
                "allow_partial_rebalance": self.rebalance_config.allow_partial_rebalance,
            },
            "execution_config": self.execution_config,
            "current_state": self.current_state.to_dict() if self.current_state else None,
            "cycle_id": self.cycle_id,
        }


@dataclass
class CycleResult:
    """Result of a complete portfolio cycle.
    
    Attributes:
        cycle_id: Unique identifier for this cycle
        cycle_timestamp: When cycle was executed
        evaluation_id: ID of evaluation result
        allocation_id: ID of allocation result
        rebalance_plan_id: ID of rebalance plan
        rebalance_execution_id: ID of rebalance execution
        summary: Summary metrics across the cycle
    """
    
    cycle_id: str
    cycle_timestamp: datetime
    evaluation_id: str
    allocation_id: str
    rebalance_plan_id: str
    rebalance_execution_id: str
    summary: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "cycle_id": self.cycle_id,
            "cycle_timestamp": self.cycle_timestamp.isoformat(),
            "evaluation_id": self.evaluation_id,
            "allocation_id": self.allocation_id,
            "rebalance_plan_id": self.rebalance_plan_id,
            "rebalance_execution_id": self.rebalance_execution_id,
            "summary": self.summary,
        }


def run_portfolio_cycle(
    config: PortfolioCycleConfig,
    research_engine: SimpleResearchEngine,
    artifact_store: ArtifactStore,
    execution_engine_factory: Callable[[], PaperExecutionEngine],
    cycle_id: Optional[str] = None
) -> CycleResult:
    """Run a complete portfolio lifecycle cycle.
    
    Orchestrates:
    1. Batch evaluation of strategies
    2. Capital allocation across top strategies
    3. Rebalance planning from current state to targets
    4. Rebalance execution through paper engine
    
    Determinism guarantees:
    - Same configs + same data → same cycle result
    - No background state
    - Deterministic execution order
    
    Args:
        config: Portfolio cycle configuration
        research_engine: Research engine for backtesting
        artifact_store: Artifact store for persistence
        execution_engine_factory: Factory function that creates PaperExecutionEngine
                                 (must create isolated sessions)
        cycle_id: Optional cycle identifier (auto-generated if not provided)
        
    Returns:
        CycleResult with references to all sub-artifacts and summary
        
    Raises:
        CycleError: If cycle execution fails
        
    Example:
        >>> def create_engine():
        ...     return PaperExecutionEngine(instrument="AAPL", artifact_store=store)
        >>> result = run_portfolio_cycle(
        ...     config=cycle_config,
        ...     research_engine=engine,
        ...     artifact_store=store,
        ...     execution_engine_factory=create_engine
        ... )
        >>> print(f"Cycle {result.cycle_id} completed")
        >>> print(f"Top strategy: {result.summary['top_strategy_id']}")
    """
    if cycle_id is None:
        cycle_id = config.cycle_id or f"cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    try:
        # Step 1: Batch evaluation
        evaluation = run_batch_evaluation(
            config=config.evaluation_config,
            research_engine=research_engine,
            artifact_store=artifact_store,
            execution_engine_factory=execution_engine_factory
        )
        evaluation_id = evaluation.evaluation_id
        
        # Step 2: Capital allocation
        allocation_result = allocate_capital(
            evaluation=evaluation,
            config=config.allocation_config
        )
        from ..allocation.allocator import persist_allocation
        allocation_id = persist_allocation(allocation_result, artifact_store)
        
        # Step 3: Determine current state
        if config.current_state is None:
            # Assume flat/empty portfolio
            current_state = CurrentPortfolioState(
                strategy_allocations={},
                total_capital=config.allocation_config.total_capital,
                timestamp=datetime.now()
            )
        else:
            current_state = config.current_state
        
        # Step 4: Rebalance planning
        rebalance_plan = plan_rebalance(
            allocation_result=allocation_result,
            current_state=current_state,
            config=config.rebalance_config
        )
        from ..rebalance.planner import persist_rebalance_plan
        rebalance_plan_id = persist_rebalance_plan(rebalance_plan, artifact_store)
        
        # Step 5: Rebalance execution
        # Create execution engine for rebalance
        execution_engine = execution_engine_factory()
        
        # Get prices from execution config
        price_by_strategy_or_instrument = config.execution_config.get(
            "price_by_strategy_or_instrument", {}
        )
        
        # Create mapper
        mapper = RebalanceSignalMapper(
            rounding_method=config.execution_config.get("rounding_method", "floor"),
            min_quantity=config.execution_config.get("min_quantity", 0.0)
        )
        
        execution_result = execute_rebalance_plan(
            plan=rebalance_plan,
            execution_engine=execution_engine,
            price_by_strategy_or_instrument=price_by_strategy_or_instrument,
            mapper=mapper
        )
        from ..rebalance.executor import persist_rebalance_execution
        rebalance_execution_id = persist_rebalance_execution(execution_result, artifact_store)
        
        # Step 6: Compute cycle summary
        summary = {
            "evaluation_summary": evaluation.summary,
            "allocation_summary": {
                "total_capital": allocation_result.total_capital,
                "allocated_capital": allocation_result.allocated_capital,
                "num_strategies": len(allocation_result.allocations),
                "top_strategy_id": allocation_result.allocations[0].strategy_id if allocation_result.allocations else None,
            },
            "rebalance_summary": rebalance_plan.metrics,
            "execution_summary": execution_result.execution_summary,
        }
        
        return CycleResult(
            cycle_id=cycle_id,
            cycle_timestamp=datetime.now(),
            evaluation_id=evaluation_id,
            allocation_id=allocation_id,
            rebalance_plan_id=rebalance_plan_id,
            rebalance_execution_id=rebalance_execution_id,
            summary=summary
        )
        
    except Exception as e:
        raise CycleError(f"Failed to run portfolio cycle: {e}") from e


def persist_cycle_result(
    result: CycleResult,
    artifact_store: ArtifactStore
) -> str:
    """Persist cycle result to artifact store.
    
    Args:
        result: CycleResult to persist
        artifact_store: ArtifactStore instance
        
    Returns:
        Cycle identifier
        
    Raises:
        CycleError: If persistence fails
    """
    try:
        result_json = json.dumps(result.to_dict(), indent=2).encode('utf-8')
        artifact_store.store(result.cycle_id, "cycle_result.json", result_json)
        return result.cycle_id
    except Exception as e:
        raise CycleError(f"Failed to persist cycle result: {e}") from e


def main():
    """CLI entrypoint for portfolio cycle execution.
    
    Usage:
        python -m src.lifecycle.runner --config <config_path>
    """
    parser = argparse.ArgumentParser(
        description="Run portfolio lifecycle cycle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example cycle_config.json:
{
  "evaluation_config": {
    "strategies": [...],
    "parameter_grid": {...},
    "evaluation_criteria": {...},
    "price_series": [...]
  },
  "allocation_config": {
    "total_capital": 1000000,
    "top_n_strategies": 5,
    "allocation_method": "robustness_weighted"
  },
  "rebalance_config": {
    "rebalance_threshold_pct": 0.05,
    "max_turnover_pct": 0.5
  },
  "execution_config": {
    "price_by_strategy_or_instrument": {
      "strat_1": 150.0,
      "AAPL": 150.0
    },
    "rounding_method": "floor",
    "min_quantity": 1.0
  },
  "current_state": {
    "strategy_allocations": {},
    "total_capital": 1000000,
    "timestamp": "2024-01-01T00:00:00"
  }
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
        config = PortfolioCycleConfig.from_json_file(args.config)
        
        # Create artifact store
        artifact_store = LocalArtifactStore(args.artifacts_dir)
        
        # Create research engine
        research_engine = SimpleResearchEngine(artifact_store=artifact_store)
        
        # Create execution engine factory
        # Extract instrument from first strategy (assumes single instrument cycle)
        if not config.evaluation_config.strategies:
            raise CycleError("Evaluation config must contain at least one strategy")
        
        first_strategy = config.evaluation_config.strategies[0]
        instrument = first_strategy.inputs.get("instrument", "UNKNOWN")
        
        def create_engine():
            return PaperExecutionEngine(
                instrument=instrument,
                artifact_store=artifact_store
            )
        
        # Run cycle
        result = run_portfolio_cycle(
            config=config,
            research_engine=research_engine,
            artifact_store=artifact_store,
            execution_engine_factory=create_engine
        )
        
        # Persist cycle result
        cycle_id = persist_cycle_result(result, artifact_store)
        
        # Print summary
        print(f"Portfolio cycle complete: {cycle_id}")
        print(f"Evaluation ID: {result.evaluation_id}")
        print(f"Allocation ID: {result.allocation_id}")
        print(f"Rebalance Plan ID: {result.rebalance_plan_id}")
        print(f"Rebalance Execution ID: {result.rebalance_execution_id}")
        print(f"Top strategy: {result.summary['allocation_summary']['top_strategy_id']}")
        print(f"Strategies allocated: {result.summary['allocation_summary']['num_strategies']}")
        print(f"Execution success rate: {result.summary['execution_summary']['success_rate']:.1%}")
        
        sys.exit(0)
        
    except CycleError as e:
        print(f"Cycle error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

