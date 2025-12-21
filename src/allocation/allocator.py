"""Capital allocation engine.

This module provides deterministic capital allocation across strategies based on
batch evaluation rankings and portfolio-level risk constraints.

Determinism guarantees:
- Same evaluation results → same allocation
- Deterministic tie-breaking for strategies with equal scores
- Portfolio constraints enforced deterministically
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from ..evaluation import StrategyEvaluation, EvaluationResult
from ..core.artifacts import ArtifactStore


class AllocationError(Exception):
    """Error raised when capital allocation fails."""
    pass


@dataclass
class AllocationConfig:
    """Configuration for capital allocation.
    
    Attributes:
        total_capital: Total capital to allocate
        top_n_strategies: Maximum number of strategies to include (None = all)
        min_robustness_score: Minimum robustness score to include strategy (default: 0.0)
        max_allocation_per_strategy: Maximum allocation per strategy as fraction (default: 1.0 = 100%)
        min_allocation_per_strategy: Minimum allocation per strategy as fraction (default: 0.0)
        allocation_method: Allocation method ("equal", "robustness_weighted", "score_ranked")
        max_total_leverage: Maximum total leverage (sum of allocations, default: 1.0)
        require_all_passed: If True, only allocate to strategies that passed evaluation (default: False)
        
    Note:
        - allocation_method "equal": Equal allocation across selected strategies
        - allocation_method "robustness_weighted": Weight by robustness score
        - allocation_method "score_ranked": Exponential decay by rank
    """
    
    total_capital: float
    top_n_strategies: Optional[int] = None
    min_robustness_score: float = 0.0
    max_allocation_per_strategy: float = 1.0
    min_allocation_per_strategy: float = 0.0
    allocation_method: str = "robustness_weighted"
    max_total_leverage: float = 1.0
    require_all_passed: bool = False
    
    def __post_init__(self):
        """Validate allocation config."""
        if self.total_capital <= 0:
            raise ValueError(f"total_capital must be positive, got: {self.total_capital}")
        
        if self.top_n_strategies is not None and self.top_n_strategies < 1:
            raise ValueError(f"top_n_strategies must be >= 1, got: {self.top_n_strategies}")
        
        if not (0.0 <= self.min_robustness_score <= 1.0):
            raise ValueError(
                f"min_robustness_score must be between 0.0 and 1.0, got: {self.min_robustness_score}"
            )
        
        if not (0.0 <= self.max_allocation_per_strategy <= 1.0):
            raise ValueError(
                f"max_allocation_per_strategy must be between 0.0 and 1.0, "
                f"got: {self.max_allocation_per_strategy}"
            )
        
        if not (0.0 <= self.min_allocation_per_strategy <= 1.0):
            raise ValueError(
                f"min_allocation_per_strategy must be between 0.0 and 1.0, "
                f"got: {self.min_allocation_per_strategy}"
            )
        
        if self.min_allocation_per_strategy > self.max_allocation_per_strategy:
            raise ValueError(
                f"min_allocation_per_strategy ({self.min_allocation_per_strategy}) must be <= "
                f"max_allocation_per_strategy ({self.max_allocation_per_strategy})"
            )
        
        if self.allocation_method not in ("equal", "robustness_weighted", "score_ranked"):
            raise ValueError(
                f"allocation_method must be 'equal', 'robustness_weighted', or 'score_ranked', "
                f"got: {self.allocation_method}"
            )
        
        if self.max_total_leverage <= 0:
            raise ValueError(
                f"max_total_leverage must be positive, got: {self.max_total_leverage}"
            )


@dataclass
class PortfolioAllocation:
    """Allocation for a single strategy in the portfolio.
    
    Attributes:
        strategy_id: Strategy identifier
        experiment_name: Experiment name
        experiment_version: Experiment version
        allocated_capital: Capital allocated to this strategy
        allocation_fraction: Fraction of total capital (0.0 to 1.0)
        robustness_score: Robustness score used for allocation
        rank: Rank in evaluation (1 = best)
    """
    
    strategy_id: str
    experiment_name: str
    experiment_version: str
    allocated_capital: float
    allocation_fraction: float
    robustness_score: float
    rank: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return asdict(self)


@dataclass
class AllocationResult:
    """Result of capital allocation.
    
    Attributes:
        allocation_id: Unique identifier for this allocation
        allocation_timestamp: When allocation was computed
        config: Allocation configuration used
        total_capital: Total capital available
        allocated_capital: Total capital allocated
        unallocated_capital: Capital not allocated
        allocations: List of strategy allocations
        metrics: Allocation metrics
    """
    
    allocation_id: str
    allocation_timestamp: datetime
    config: AllocationConfig
    total_capital: float
    allocated_capital: float
    unallocated_capital: float
    allocations: List[PortfolioAllocation]
    metrics: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "allocation_id": self.allocation_id,
            "allocation_timestamp": self.allocation_timestamp.isoformat(),
            "config": {
                "total_capital": self.config.total_capital,
                "top_n_strategies": self.config.top_n_strategies,
                "min_robustness_score": self.config.min_robustness_score,
                "max_allocation_per_strategy": self.config.max_allocation_per_strategy,
                "min_allocation_per_strategy": self.config.min_allocation_per_strategy,
                "allocation_method": self.config.allocation_method,
                "max_total_leverage": self.config.max_total_leverage,
                "require_all_passed": self.config.require_all_passed,
            },
            "total_capital": self.total_capital,
            "allocated_capital": self.allocated_capital,
            "unallocated_capital": self.unallocated_capital,
            "allocations": [a.to_dict() for a in self.allocations],
            "metrics": self.metrics,
        }


def _filter_strategies(
    evaluation: StrategyEvaluation,
    config: AllocationConfig
) -> List[EvaluationResult]:
    """Filter strategies based on allocation config criteria.
    
    Args:
        evaluation: Strategy evaluation results
        config: Allocation configuration
        
    Returns:
        Filtered list of evaluation results, in ranking order
    """
    candidates = evaluation.ranked_results
    
    # Filter by passed status
    if config.require_all_passed:
        candidates = [r for r in candidates if r.passed]
    
    # Filter by minimum robustness score
    candidates = [
        r for r in candidates
        if r.evaluation_metrics.execution_robustness_score >= config.min_robustness_score
    ]
    
    # Take top N
    if config.top_n_strategies is not None:
        candidates = candidates[:config.top_n_strategies]
    
    return candidates


def _compute_weights(
    candidates: List[EvaluationResult],
    method: str
) -> List[float]:
    """Compute allocation weights for candidates.
    
    Args:
        candidates: List of evaluation results (already filtered and ranked)
        method: Allocation method ("equal", "robustness_weighted", "score_ranked")
        
    Returns:
        List of weights (will be normalized to sum to 1.0)
    """
    if not candidates:
        return []
    
    if method == "equal":
        # Equal weights
        return [1.0] * len(candidates)
    
    elif method == "robustness_weighted":
        # Weight by robustness score
        scores = [r.evaluation_metrics.execution_robustness_score for r in candidates]
        # Normalize by sum (handled later, but ensure non-negative)
        return [max(0.0, score) for score in scores]
    
    elif method == "score_ranked":
        # Exponential decay by rank (rank 1 gets highest weight)
        weights = []
        for i, _ in enumerate(candidates):
            # Exponential decay: weight = 0.5^(rank-1), so rank 1 gets weight 1.0
            weight = 0.5 ** i
            weights.append(weight)
        return weights
    
    else:
        raise AllocationError(f"Unknown allocation method: {method}")


def _normalize_weights(weights: List[float]) -> List[float]:
    """Normalize weights to sum to 1.0.
    
    Args:
        weights: Raw weights
        
    Returns:
        Normalized weights that sum to 1.0
        
    Raises:
        AllocationError: If all weights are zero
    """
    total = sum(weights)
    
    if total == 0.0:
        raise AllocationError("Cannot normalize weights: all weights are zero")
    
    return [w / total for w in weights]


def _apply_constraints(
    weights: List[float],
    config: AllocationConfig,
    total_capital: float
) -> List[float]:
    """Apply portfolio-level constraints to weights.
    
    Args:
        weights: Normalized weights (fractions)
        config: Allocation configuration
        total_capital: Total capital
        
    Returns:
        Constrained weights (may sum to less than 1.0 if constraints bind)
    """
    constrained_weights = []
    
    for weight in weights:
        # Apply per-strategy constraints
        constrained = max(
            config.min_allocation_per_strategy,
            min(weight, config.max_allocation_per_strategy)
        )
        constrained_weights.append(constrained)
    
    # Check total leverage constraint
    total_allocation = sum(constrained_weights)
    
    if total_allocation > config.max_total_leverage:
        # Scale down proportionally to meet leverage constraint
        scale_factor = config.max_total_leverage / total_allocation
        constrained_weights = [w * scale_factor for w in constrained_weights]
    
    return constrained_weights


def _compute_allocation_metrics(
    allocations: List[PortfolioAllocation],
    total_capital: float,
    evaluation: StrategyEvaluation
) -> Dict[str, Any]:
    """Compute allocation metrics.
    
    Args:
        allocations: List of portfolio allocations
        total_capital: Total capital
        evaluation: Original evaluation results
        
    Returns:
        Dictionary of metrics
    """
    if not allocations:
        return {
            "num_strategies": 0,
            "total_allocation_fraction": 0.0,
            "average_robustness_score": 0.0,
            "weighted_average_robustness": 0.0,
            "min_allocation": 0.0,
            "max_allocation": 0.0,
        }
    
    allocation_fractions = [a.allocation_fraction for a in allocations]
    robustness_scores = [a.robustness_score for a in allocations]
    allocated_capitals = [a.allocated_capital for a in allocations]
    
    # Weighted average robustness (by allocation)
    weighted_avg_robustness = sum(
        a.robustness_score * a.allocation_fraction
        for a in allocations
    )
    
    return {
        "num_strategies": len(allocations),
        "total_allocation_fraction": sum(allocation_fractions),
        "average_robustness_score": sum(robustness_scores) / len(robustness_scores),
        "weighted_average_robustness": weighted_avg_robustness,
        "min_allocation": min(allocated_capitals),
        "max_allocation": max(allocated_capitals),
        "concentration_ratio": max(allocation_fractions),  # Largest allocation fraction
    }


def allocate_capital(
    evaluation: StrategyEvaluation,
    config: AllocationConfig,
    allocation_id: Optional[str] = None
) -> AllocationResult:
    """Allocate capital across strategies based on evaluation results.
    
    Process:
    1. Filter strategies by criteria (passed, robustness score, top N)
    2. Compute allocation weights based on method
    3. Apply portfolio constraints (per-strategy limits, leverage)
    4. Compute final allocations
    5. Calculate metrics
    
    Determinism guarantees:
    - Same evaluation + same config → same allocation
    - Deterministic tie-breaking (uses ranking order)
    
    Args:
        evaluation: Strategy evaluation results
        config: Allocation configuration
        allocation_id: Optional allocation identifier (auto-generated if not provided)
        
    Returns:
        AllocationResult with allocations and metrics
        
    Raises:
        AllocationError: If allocation fails
        
    Example:
        >>> config = AllocationConfig(
        ...     total_capital=1000000,
        ...     top_n_strategies=5,
        ...     allocation_method="robustness_weighted"
        ... )
        >>> result = allocate_capital(evaluation, config)
        >>> print(f"Allocated {result.allocated_capital} across {len(result.allocations)} strategies")
    """
    if allocation_id is None:
        allocation_id = f"alloc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    try:
        # Step 1: Filter strategies
        candidates = _filter_strategies(evaluation, config)
        
        if not candidates:
            # No strategies meet criteria - return empty allocation
            return AllocationResult(
                allocation_id=allocation_id,
                allocation_timestamp=datetime.now(),
                config=config,
                total_capital=config.total_capital,
                allocated_capital=0.0,
                unallocated_capital=config.total_capital,
                allocations=[],
                metrics=_compute_allocation_metrics([], config.total_capital, evaluation)
            )
        
        # Step 2: Compute weights
        raw_weights = _compute_weights(candidates, config.allocation_method)
        
        # Step 3: Normalize weights
        normalized_weights = _normalize_weights(raw_weights)
        
        # Step 4: Apply constraints
        constrained_weights = _apply_constraints(
            normalized_weights,
            config,
            config.total_capital
        )
        
        # Step 5: Compute final allocations
        allocations = []
        for i, (result, weight) in enumerate(zip(candidates, constrained_weights)):
            allocated_capital = weight * config.total_capital
            
            allocation = PortfolioAllocation(
                strategy_id=result.strategy_id,
                experiment_name=result.experiment_name,
                experiment_version=result.experiment_version,
                allocated_capital=allocated_capital,
                allocation_fraction=weight,
                robustness_score=result.evaluation_metrics.execution_robustness_score,
                rank=i + 1  # Rank in filtered list (1-indexed)
            )
            allocations.append(allocation)
        
        # Step 6: Compute metrics
        allocated_capital = sum(a.allocated_capital for a in allocations)
        metrics = _compute_allocation_metrics(allocations, config.total_capital, evaluation)
        
        return AllocationResult(
            allocation_id=allocation_id,
            allocation_timestamp=datetime.now(),
            config=config,
            total_capital=config.total_capital,
            allocated_capital=allocated_capital,
            unallocated_capital=config.total_capital - allocated_capital,
            allocations=allocations,
            metrics=metrics
        )
        
    except Exception as e:
        raise AllocationError(f"Failed to allocate capital: {e}") from e


def persist_allocation(
    allocation: AllocationResult,
    artifact_store: ArtifactStore
) -> str:
    """Persist allocation result to artifact store.
    
    Args:
        allocation: AllocationResult to persist
        artifact_store: ArtifactStore instance
        
    Returns:
        Allocation identifier
        
    Raises:
        AllocationError: If persistence fails
    """
    try:
        allocation_json = json.dumps(allocation.to_dict(), indent=2).encode('utf-8')
        artifact_store.store(
            allocation.allocation_id,
            "allocation.json",
            allocation_json
        )
        return allocation.allocation_id
    except Exception as e:
        raise AllocationError(f"Failed to persist allocation: {e}") from e

