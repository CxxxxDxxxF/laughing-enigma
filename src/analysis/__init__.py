"""Analysis modules for strategy evaluation and survivability."""

from .divergence import (
    DivergenceAnalysis,
    DivergenceMetrics,
    DivergencePoint,
    DivergenceCause,
    analyze_backtest_vs_paper,
    persist_divergence_analysis,
    DivergenceAnalysisError,
)
from .survivability import (
    SurvivabilityMetrics,
    analyze_survivability,
)

__all__ = [
    "DivergenceAnalysis",
    "DivergenceMetrics",
    "DivergencePoint",
    "DivergenceCause",
    "analyze_backtest_vs_paper",
    "persist_divergence_analysis",
    "DivergenceAnalysisError",
    "SurvivabilityMetrics",
    "analyze_survivability",
]
