"""Alpaca market data provider implementation.

Provides live market data from Alpaca API.
"""

from typing import Optional, Tuple
from datetime import datetime
import logging

from ..market.interface import MarketDataProvider
from ..execution.alpaca_client import AlpacaClient, AlpacaClientError

logger = logging.getLogger(__name__)


class AlpacaMarketDataProvider(MarketDataProvider):
    """Live market data provider using Alpaca API.
    
    Fetches real-time quotes for execution prices.
    """
    
    def __init__(self, alpaca_client: Optional[AlpacaClient] = None):
        """Initialize provider.
        
        Args:
            alpaca_client: AlpacaClient instance
        """
        self.client = alpaca_client or AlpacaClient()
        
        # Ensure connection
        if not self.client.is_connected:
            try:
                self.client.connect()
            except AlpacaClientError as e:
                logger.warning(f"Failed to connect to Alpaca on init: {e}")

    def get_mark_price(self, instrument: str, as_of: datetime) -> Optional[float]:
        """Get latest mark price (midpoint).
        
        Args:
            instrument: Symbol
            as_of: Timestamp (ignored for live data, we get latest)
            
        Returns:
            Latest mid price
        """
        try:
            quote = self.client.get_quote(instrument)
            return quote.last_price
        except Exception as e:
            logger.error(f"Failed to get mark price for {instrument}: {e}")
            return None

    def get_execution_price(self, instrument: str, as_of: datetime, side: str, quantity: float) -> Optional[float]:
        """Estimate execution price.
        
        For BUY, returns ASK price.
        For SELL, returns BID price.
        """
        try:
            quote = self.client.get_quote(instrument)
            if side.upper() == "BUY":
                return quote.ask_price
            else:
                return quote.bid_price
        except Exception as e:
            logger.error(f"Failed to get execution price for {instrument}: {e}")
            return None

    def get_bid_ask(self, instrument: str, as_of: datetime) -> Optional[Tuple[float, float]]:
        """Get current bid/ask spread."""
        try:
            quote = self.client.get_quote(instrument)
            return (quote.bid_price, quote.ask_price)
        except Exception as e:
            logger.error(f"Failed to get bid/ask for {instrument}: {e}")
            return None
