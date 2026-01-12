"""Abstract broker interface for multi-broker support.

Decouples execution logic from broker-specific implementations,
allowing the system to support Alpaca, Interactive Brokers, etc.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


@dataclass
class BrokerOrder:
    """Broker-agnostic order representation."""
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal("0")
    filled_avg_price: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class BrokerPosition:
    """Broker-agnostic position representation."""
    symbol: str
    quantity: Decimal
    avg_cost: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal = Decimal("0")


@dataclass
class BrokerAccount:
    """Broker-agnostic account state."""
    account_id: str
    equity: Decimal
    cash: Decimal
    buying_power: Decimal
    margin_used: Decimal = Decimal("0")
    day_trades_remaining: Optional[int] = None


class BrokerInterface(ABC):
    """Abstract interface for broker implementations.
    
    All broker-specific clients (Alpaca, IBKR, etc.) should implement
    this interface to ensure consistent behavior across the system.
    """
    
    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to broker.
        
        Returns:
            True if connection successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to broker."""
        pass
    
    @abstractmethod
    def get_account(self) -> BrokerAccount:
        """Get current account state.
        
        Returns:
            BrokerAccount with current equity, cash, etc.
        """
        pass
    
    @abstractmethod
    def get_positions(self) -> List[BrokerPosition]:
        """Get all current positions.
        
        Returns:
            List of BrokerPosition objects.
        """
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        """Get position for a specific symbol.
        
        Args:
            symbol: Instrument symbol.
            
        Returns:
            BrokerPosition if exists, None otherwise.
        """
        pass
    
    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None
    ) -> BrokerOrder:
        """Submit an order to the broker.
        
        Args:
            symbol: Instrument symbol.
            side: Buy or sell.
            quantity: Number of shares/contracts.
            order_type: Market, limit, etc.
            limit_price: Price for limit orders.
            stop_price: Price for stop orders.
            
        Returns:
            BrokerOrder with order details and status.
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order.
        
        Args:
            order_id: Broker order ID.
            
        Returns:
            True if cancellation successful.
        """
        pass
    
    @abstractmethod
    def get_order(self, order_id: str) -> Optional[BrokerOrder]:
        """Get order by ID.
        
        Args:
            order_id: Broker order ID.
            
        Returns:
            BrokerOrder if found, None otherwise.
        """
        pass
    
    @abstractmethod
    def get_open_orders(self, symbol: Optional[str] = None) -> List[BrokerOrder]:
        """Get all open orders.
        
        Args:
            symbol: Optional filter by symbol.
            
        Returns:
            List of open BrokerOrder objects.
        """
        pass
    
    @abstractmethod
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote for a symbol.
        
        Args:
            symbol: Instrument symbol.
            
        Returns:
            Dict with bid, ask, last price, etc.
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Broker name for logging."""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected to broker."""
        pass
