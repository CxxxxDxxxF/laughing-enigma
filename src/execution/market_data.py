"""Market Data Provider Interface.

Defines the contract for fetching real-time and historical market data.
In Simulation, this is backed by stored data. 
In Live, this connects to an external provider (e.g. Polygon, Alpaca).
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Protocol
from dataclasses import dataclass

@dataclass
class Bar:
    """OHLCV Bar data."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def get_price(self, instrument: str) -> float:
        """Get the current price for an instrument.
        
        Args:
            instrument: Symbol/Ticker
            
        Returns:
            Current price (float)
            
        Raises:
            MarketDataError: If price unavailable
        """
        raise NotImplementedError

    @abstractmethod
    def get_history(
        self, 
        instrument: str, 
        start: datetime, 
        end: datetime, 
        resolution: str = "1d"
    ) -> List[Bar]:
        """Get historical bars for an instrument.
        
        Args:
            instrument: Symbol
            start: Start datetime (inclusive)
            end: End datetime (inclusive)
            resolution: Bar size (e.g. '1m', '1h', '1d')
            
        Returns:
            List of Bar objects
        """
        raise NotImplementedError

    @abstractmethod
    def get_prices(self, instruments: List[str]) -> Dict[str, float]:
        """Batch get current prices.
        
        Args:
            instruments: List of symbols
            
        Returns:
            Dictionary {symbol: price}
        """
        # Default implementation loops, override for optimization
        return {
            inst: self.get_price(inst) for inst in instruments
        }

class MarketDataError(Exception):
    """Base exception for market data failures."""
    pass
