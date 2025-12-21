"""Strategy evaluation loop.

This module provides automated evaluation of strategies by running backtests,
paper trading sessions, and divergence analysis to produce ranked evaluations.
"""

from .evaluator import (
    StrategyEvaluation,
    EvaluationResult,
    EvaluationMetrics,
    evaluate_strategy,
    compare_strategies,
    EvaluationError,
)

__all__ = [
    "StrategyEvaluation",
    "EvaluationResult",
    "EvaluationMetrics",
    "evaluate_strategy",
    "compare_strategies",
    "EvaluationError",
]

