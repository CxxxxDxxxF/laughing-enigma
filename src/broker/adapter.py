"""Broker adapter interface for broker-agnostic trading.

This abstraction enables:
- LIVE_DRY: NullBrokerAdapter (deterministic mock)
- LIVE: Real broker adapters (Topstep, Apex, etc.)

All broker-specific logic is isolated in adapters.
Rules, runner, and limits logic remain broker-agnostic.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass(frozen=True)
class AccountMetadata:
    """Account metadata from broker.
    
    Attributes:
        account_id: Account identifier
        balance: Current account balance
        equity: Current account equity (balance + unrealized PnL)
        buying_power: Available buying power
        daily_loss_limit: Current daily loss limit (negative value)
        timestamp: Timestamp when metadata was retrieved
    """
    account_id: str
    balance: float
    equity: float
    buying_power: float
    daily_loss_limit: float
    timestamp: datetime


@dataclass(frozen=True)
class BrokerOrder:
    """Order submitted to broker.
    
    Attributes:
        order_id: Broker-assigned order ID
        instrument: Instrument identifier
        side: "buy" or "sell"
        quantity: Order quantity
        order_type: Order type (e.g., "market", "limit")
        price_limit: Optional price limit for limit orders
        status: Order status (e.g., "pending", "filled", "canceled")
        submitted_at: Timestamp when order was submitted
    """
    order_id: str
    instrument: str
    side: str
    quantity: float
    order_type: str
    price_limit: Optional[float] = None
    status: str = "pending"
    submitted_at: datetime = None


@dataclass(frozen=True)
class BrokerFill:
    """Fill received from broker.
    
    Attributes:
        fill_id: Broker-assigned fill ID
        order_id: Order ID this fill belongs to
        instrument: Instrument identifier
        side: "buy" or "sell"
        quantity: Filled quantity
        price: Fill price
        fee: Transaction fee
        filled_at: Timestamp when fill occurred
    """
    fill_id: str
    order_id: str
    instrument: str
    side: str
    quantity: float
    price: float
    fee: float
    filled_at: datetime


class BrokerAdapter(ABC):
    """Abstract interface for broker integration.
    
    This abstraction separates broker-specific operations from
    execution logic, enabling:
    - Deterministic testing (NullBrokerAdapter)
    - Real broker integration (TopstepAdapter, ApexAdapter, etc.)
    - Multi-broker support without code duplication
    
    All broker operations are async-ready (though sync for now).
    """
    
    @abstractmethod
    def get_account_metadata(self) -> AccountMetadata:
        """Get current account metadata from broker.
        
        Returns:
            AccountMetadata with balance, equity, limits, etc.
            
        Raises:
            BrokerAdapterError: If metadata cannot be retrieved
        """
        raise NotImplementedError
    
    @abstractmethod
    def submit_order(
        self,
        instrument: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price_limit: Optional[float] = None
    ) -> BrokerOrder:
        """Submit an order to the broker.
        
        Args:
            instrument: Instrument identifier
            side: "buy" or "sell"
            quantity: Order quantity
            order_type: Order type (e.g., "market", "limit")
            price_limit: Optional price limit for limit orders
            
        Returns:
            BrokerOrder with broker-assigned order_id
            
        Raises:
            BrokerAdapterError: If order cannot be submitted
        """
        raise NotImplementedError
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> BrokerOrder:
        """Cancel an active order.
        
        Args:
            order_id: Broker-assigned order ID
            
        Returns:
            Updated BrokerOrder with status "canceled"
            
        Raises:
            BrokerAdapterError: If order cannot be canceled
        """
        raise NotImplementedError
    
    @abstractmethod
    def flatten_positions(self, instrument: Optional[str] = None) -> List[BrokerFill]:
        """Flatten all positions (close all open positions).
        
        Args:
            instrument: Optional instrument to flatten (None = all instruments)
            
        Returns:
            List of BrokerFills from closing positions
            
        Raises:
            BrokerAdapterError: If positions cannot be flattened
        """
        raise NotImplementedError
    
    @abstractmethod
    def poll_fills(self, since: Optional[datetime] = None) -> List[BrokerFill]:
        """Poll for new fills since a timestamp.
        
        Args:
            since: Optional timestamp to get fills since (None = all fills)
            
        Returns:
            List of BrokerFills since the timestamp
            
        Raises:
            BrokerAdapterError: If fills cannot be retrieved
        """
        raise NotImplementedError
    
    def get_positions(self) -> Dict[str, float]:
        """Get current positions from broker.
        
        Default implementation uses account metadata.
        Override if broker provides direct position API.
        
        Returns:
            Dictionary of instrument -> quantity (positive for long, negative for short)
        """
        # Default: empty positions (broker adapters should override)
        return {}


class BrokerAdapterError(Exception):
    """Error raised when broker adapter operations fail."""
    pass

