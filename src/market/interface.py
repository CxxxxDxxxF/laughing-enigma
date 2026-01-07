"""Market Data Provider Interface.

Defines the contract for retrieving market data in a dependency-injected manner.
This interface isolates the trading system from specific data sources (historical, live, or simulated).
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List


class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def get_mark_price(self, instrument: str, as_of: datetime) -> Optional[float]:
        """Get the mark price for an instrument at a specific time.
        
        The mark price is used for:
        - Portfolio valuation (mark-to-market)
        - Margin calculations
        - Risk checks (e.g., drawdown)
        
        Args:
            instrument: Instrument identifier (e.g., "AAPL")
            as_of: Timestamp for the price query
            
        Returns:
            Price as float, or None if data unavailable.
        """
        pass

    @abstractmethod
    def get_execution_price(
        self, 
        instrument: str, 
        as_of: datetime, 
        side: str, 
        quantity: float
    ) -> Optional[float]:
        """Get the estimated execution price for a trade.
        
        Used for:
        - Simulating execution fills
        - Estimating slippage
        - Determining limit prices
        
        Args:
            instrument: Instrument identifier
            as_of: Timestamp for the execution
            side: "buy" or "sell"
            quantity: Amount to trade (absolute value)
            
        Returns:
            Estimated execution price, or None if unavailable.
        """
        pass

    @abstractmethod
    def get_bid_ask(self, instrument: str, as_of: datetime) -> Optional[Tuple[float, float]]:
        """Get the bid and ask prices.
        
        Used for:
        - Spread calculations
        - Detailed PnL analysis
        
        Args:
            instrument: Instrument identifier
            as_of: Timestamp for the query
            
        Returns:
            Tuple of (bid, ask), or None if unavailable.
        """
        pass

    def get_historical_prices(
        self, 
        instrument: str, 
        start_time: datetime, 
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get a range of historical prices.
        
        Optional method. Default implementation returns empty list.
        
        Args:
            instrument: Instrument identifier
            start_time: Start of range
            end_time: End of range
            
        Returns:
            List of price records (dictionaries).
        """
        return []

    def get_latest_prices(self, instruments: List[str]) -> Dict[str, float]:
        """Batch fetch latest prices for multiple instruments.
        
        Args:
            instruments: List of instrument identifiers
            
        Returns:
            Dictionary mapping instrument -> price.
            Missing instruments are omitted.
        """
        results = {}
        now = datetime.now()  # Note: Implementations should override to use appropriate clock
        for inst in instruments:
            price = self.get_mark_price(inst, now)
            if price is not None:
                results[inst] = price
        return results
