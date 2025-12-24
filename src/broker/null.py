"""Null broker adapter for LIVE_DRY mode.

Provides deterministic mock broker behavior for testing and validation.
All operations return predictable, deterministic results.
"""

from datetime import datetime
from typing import List, Optional, Dict

from .adapter import (
    BrokerAdapter,
    AccountMetadata,
    BrokerOrder,
    BrokerFill,
    BrokerAdapterError
)


class NullBrokerAdapter(BrokerAdapter):
    """Null broker adapter for LIVE_DRY mode.
    
    Provides deterministic mock broker behavior:
    - Fixed account metadata
    - Orders are "accepted" but never filled
    - No real broker API calls
    
    Used for:
    - LIVE_DRY testing and validation
    - Deterministic rehearsal runs
    - Architecture validation without broker dependency
    """
    
    def __init__(
        self,
        account_id: str = "null_account",
        balance: float = 50000.0,
        equity: float = 50000.0,
        buying_power: float = 50000.0,
        daily_loss_limit: float = -1000.0
    ):
        """Initialize null broker adapter.
        
        Args:
            account_id: Mock account ID
            balance: Mock account balance
            equity: Mock account equity
            buying_power: Mock buying power
            daily_loss_limit: Mock daily loss limit (negative value)
        """
        self.account_id = account_id
        self.balance = balance
        self.equity = equity
        self.buying_power = buying_power
        self.daily_loss_limit = daily_loss_limit
        
        # Mock state
        self.orders: Dict[str, BrokerOrder] = {}
        self.fills: List[BrokerFill] = []
        self.positions: Dict[str, float] = {}
        self.order_counter = 0
    
    def get_account_metadata(self) -> AccountMetadata:
        """Get mock account metadata.
        
        Returns:
            AccountMetadata with fixed values
        """
        return AccountMetadata(
            account_id=self.account_id,
            balance=self.balance,
            equity=self.equity,
            buying_power=self.buying_power,
            daily_loss_limit=self.daily_loss_limit,
            timestamp=datetime.now()
        )
    
    def submit_order(
        self,
        instrument: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price_limit: Optional[float] = None
    ) -> BrokerOrder:
        """Submit a mock order (accepted but never filled).
        
        Args:
            instrument: Instrument identifier
            side: "buy" or "sell"
            quantity: Order quantity
            order_type: Order type (ignored in null adapter)
            price_limit: Optional price limit (ignored in null adapter)
            
        Returns:
            BrokerOrder with status "pending"
        """
        self.order_counter += 1
        order_id = f"null_order_{self.order_counter}"
        
        order = BrokerOrder(
            order_id=order_id,
            instrument=instrument,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price_limit=price_limit,
            status="pending",
            submitted_at=datetime.now()
        )
        
        self.orders[order_id] = order
        return order
    
    def cancel_order(self, order_id: str) -> BrokerOrder:
        """Cancel a mock order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            Updated BrokerOrder with status "canceled"
            
        Raises:
            BrokerAdapterError: If order not found
        """
        if order_id not in self.orders:
            raise BrokerAdapterError(f"Order {order_id} not found")
        
        order = self.orders[order_id]
        canceled_order = BrokerOrder(
            order_id=order.order_id,
            instrument=order.instrument,
            side=order.side,
            quantity=order.quantity,
            order_type=order.order_type,
            price_limit=order.price_limit,
            status="canceled",
            submitted_at=order.submitted_at
        )
        
        self.orders[order_id] = canceled_order
        return canceled_order
    
    def flatten_positions(self, instrument: Optional[str] = None) -> List[BrokerFill]:
        """Flatten mock positions (returns empty list).
        
        Args:
            instrument: Optional instrument to flatten (ignored in null adapter)
            
        Returns:
            Empty list (no positions to flatten)
        """
        # Null adapter has no positions to flatten
        return []
    
    def poll_fills(self, since: Optional[datetime] = None) -> List[BrokerFill]:
        """Poll for mock fills (returns empty list).
        
        Args:
            since: Optional timestamp (ignored in null adapter)
            
        Returns:
            Empty list (null adapter never fills orders)
        """
        # Null adapter never fills orders
        return []
    
    def get_positions(self) -> Dict[str, float]:
        """Get mock positions (returns empty dict).
        
        Returns:
            Empty dictionary (null adapter has no positions)
        """
        return {}

