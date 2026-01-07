"""Alpaca broker integration.

Provides client wrapper and execution engine for Alpaca trading API.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List

from ..core.config import AlpacaConfig, get_alpaca_config


class AlpacaClientError(Exception):
    """Error from Alpaca client operations."""
    pass


@dataclass
class AlpacaAccount:
    """Alpaca account information."""
    account_id: str
    status: str
    currency: str
    buying_power: float
    cash: float
    portfolio_value: float
    is_paper: bool


@dataclass
class AlpacaPosition:
    """Alpaca position information."""
    symbol: str
    qty: float
    avg_entry_price: float
    market_value: float
    unrealized_pl: float
    side: str  # "long" or "short"


@dataclass  
class AlpacaQuote:
    """Alpaca quote information."""
    symbol: str
    bid_price: float
    ask_price: float
    last_price: float
    timestamp: datetime


class AlpacaClient:
    """Client wrapper for Alpaca API.
    
    Provides a simplified interface to Alpaca trading functionality.
    """
    
    def __init__(self, config: Optional[AlpacaConfig] = None):
        """Initialize Alpaca client.
        
        Args:
            config: Alpaca configuration. If None, loads from environment.
        """
        self.config = config or get_alpaca_config()
        self._trading_client = None
        self._data_client = None
        self._connected = False
    
    def connect(self) -> None:
        """Connect to Alpaca API.
        
        Raises:
            AlpacaClientError: If connection fails
        """
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.live import StockDataStream
            
            self._trading_client = TradingClient(
                api_key=self.config.api_key,
                secret_key=self.config.secret_key,
                paper=self.config.is_paper
            )
            self._connected = True
            
        except ImportError:
            raise AlpacaClientError(
                "alpaca-py not installed. Run: pip install alpaca-py"
            )
        except Exception as e:
            raise AlpacaClientError(f"Failed to connect to Alpaca: {e}")
    
    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected
    
    def get_account(self) -> AlpacaAccount:
        """Get account information.
        
        Returns:
            AlpacaAccount with current account state
            
        Raises:
            AlpacaClientError: If not connected or request fails
        """
        if not self._connected:
            raise AlpacaClientError("Not connected. Call connect() first.")
        
        try:
            account = self._trading_client.get_account()
            return AlpacaAccount(
                account_id=account.id,
                status=account.status.value if hasattr(account.status, 'value') else str(account.status),
                currency=account.currency,
                buying_power=float(account.buying_power),
                cash=float(account.cash),
                portfolio_value=float(account.portfolio_value),
                is_paper=self.config.is_paper
            )
        except Exception as e:
            raise AlpacaClientError(f"Failed to get account: {e}")
    
    def get_positions(self) -> List[AlpacaPosition]:
        """Get all open positions.
        
        Returns:
            List of AlpacaPosition objects
            
        Raises:
            AlpacaClientError: If not connected or request fails
        """
        if not self._connected:
            raise AlpacaClientError("Not connected. Call connect() first.")
        
        try:
            positions = self._trading_client.get_all_positions()
            return [
                AlpacaPosition(
                    symbol=pos.symbol,
                    qty=float(pos.qty),
                    avg_entry_price=float(pos.avg_entry_price),
                    market_value=float(pos.market_value),
                    unrealized_pl=float(pos.unrealized_pl),
                    side=pos.side.value if hasattr(pos.side, 'value') else str(pos.side)
                )
                for pos in positions
            ]
        except Exception as e:
            raise AlpacaClientError(f"Failed to get positions: {e}")
    
    def get_quote(self, symbol: str) -> AlpacaQuote:
        """Get latest quote for a symbol.
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            
        Returns:
            AlpacaQuote with latest prices
            
        Raises:
            AlpacaClientError: If not connected or request fails
        """
        if not self._connected:
            raise AlpacaClientError("Not connected. Call connect() first.")
        
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestQuoteRequest
            
            data_client = StockHistoricalDataClient(
                api_key=self.config.api_key,
                secret_key=self.config.secret_key
            )
            
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = data_client.get_stock_latest_quote(request)
            
            quote = quotes[symbol]
            return AlpacaQuote(
                symbol=symbol,
                bid_price=float(quote.bid_price),
                ask_price=float(quote.ask_price),
                last_price=(float(quote.bid_price) + float(quote.ask_price)) / 2,
                timestamp=quote.timestamp
            )
        except Exception as e:
            raise AlpacaClientError(f"Failed to get quote for {symbol}: {e}")
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection and return account summary.
        
        Returns:
            Dictionary with connection status and account info
        """
        try:
            self.connect()
            account = self.get_account()
            return {
                "status": "connected",
                "is_paper": account.is_paper,
                "account_id": account.account_id,
                "account_status": account.status,
                "buying_power": account.buying_power,
                "cash": account.cash,
                "portfolio_value": account.portfolio_value,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
