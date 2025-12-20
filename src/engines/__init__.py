"""Research engines for backtest execution."""

from .base import BaseResearchEngine, BacktestResult, BacktestError
from .simple import SimpleResearchEngine, SimpleResearchEngineError, RawReturns

__all__ = [
    "BaseResearchEngine",
    "BacktestResult",
    "BacktestError",
    "SimpleResearchEngine",
    "SimpleResearchEngineError",
    "RawReturns",
]

