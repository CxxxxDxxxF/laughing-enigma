"""Divergence analysis between backtest and paper execution results.

This module provides deterministic analysis to compare what backtests predicted
vs what actually happened in paper trading execution.
"""

from .divergence import (
    DivergenceAnalysis,
    DivergenceMetrics,
    DivergencePoint,
    analyze_backtest_vs_paper,
    DivergenceAnalysisError,
)

__all__ = [
    "DivergenceAnalysis",
    "DivergenceMetrics",
    "DivergencePoint",
    "analyze_backtest_vs_paper",
    "DivergenceAnalysisError",
]

