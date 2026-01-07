"""Strategy registry module.

Imports and registers all available strategies.
"""
from ..factory import StrategyFactory
from .dual_momentum import DualMomentumStrategy
from .mean_reversion import MeanReversionStrategy

def register_strategies():
    """Register all core strategies."""
    StrategyFactory.register("dual_momentum", DualMomentumStrategy)
    StrategyFactory.register("mean_reversion", MeanReversionStrategy)

# Auto-register on import
register_strategies()
