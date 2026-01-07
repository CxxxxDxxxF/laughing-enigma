"""Strategy Factory module.

This module provides a factory for creating strategy instances.
It serves as a connection point for future strategy implementations.
"""

from typing import Dict, Any, Type, Optional
from abc import ABC, abstractmethod


class Strategy(ABC):
    """Base class for all strategies."""
    
    @abstractmethod
    def generate_signals(self, market_data: Any) -> Any:
        """Generate signals based on market data."""
        pass


class StrategyFactory:
    """Factory for creating strategy instances."""
    
    _registry: Dict[str, Type[Strategy]] = {}
    
    @classmethod
    def register(cls, name: str, strategy_class: Type[Strategy]) -> None:
        """Register a strategy class.
        
        Args:
            name: Strategy name
            strategy_class: Strategy class
        """
        cls._registry[name] = strategy_class
        
    @classmethod
    def create(cls, name: str, config: Dict[str, Any]) -> Strategy:
        """Create a strategy instance.
        
        Args:
            name: Strategy name
            config: Strategy configuration
            
        Returns:
            Strategy instance
            
        Raises:
            ValueError: If strategy not found
        """
        if name not in cls._registry:
            raise ValueError(f"Strategy '{name}' not found in registry")
            
        strategy_class = cls._registry[name]
        return strategy_class(**config)  # Assume init takes config kwargs
