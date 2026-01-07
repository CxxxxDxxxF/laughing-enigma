"""Order definition for trade requests.

An Order represents a request to execute a trade. Orders go through
a lifecycle: CREATED → ACCEPTED → FILLED/CANCELED.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderStatus(Enum):
    """Status of an order in its lifecycle."""
    CREATED = "created"      # Order created, not yet submitted
    ACCEPTED = "accepted"    # Order accepted by execution engine
    PARTIALLY_FILLED = "partially_filled"  # Partially executed
    FILLED = "filled"        # Fully executed
    CANCELED = "canceled"    # Canceled before execution
    REJECTED = "rejected"    # Rejected by execution engine


class OrderType(Enum):
    """Type of order."""
    MARKET = "market"        # Execute at current market price
    LIMIT = "limit"          # Execute only at limit price or better
    STOP = "stop"            # Triggered when price reaches stop level
    STOP_LIMIT = "stop_limit"  # Stop order with limit price


class OrderSide(Enum):
    """Side of the order."""
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Order:
    """Immutable order record.
    
    An Order represents a request to trade. Orders are created from
    Signals and go through a deterministic lifecycle.
    
    Attributes:
        id: Unique order identifier
        signal_id: Optional reference to the Signal that created this order
        instrument: Instrument identifier
        order_type: Type of order (MARKET, LIMIT, etc.)
        side: "buy" or "sell"
        quantity: Quantity to trade (always positive)
        price_limit: Limit price (required for LIMIT orders, optional for MARKET)
        status: Current order status
        created_at: When order was created
        accepted_at: When order was accepted (if accepted)
        filled_at: When order was fully filled (if filled)
        canceled_at: When order was canceled (if canceled)
        rejection_reason: Reason for rejection (if rejected)
        
    Lifecycle:
        CREATED → ACCEPTED → (PARTIALLY_FILLED →) FILLED
        CREATED → ACCEPTED → CANCELED
        CREATED → REJECTED
        
    Note:
        - Quantity is always positive (side determines buy vs sell)
        - Only one of filled_at, canceled_at, rejection_reason should be set
        - Status must match the timestamp fields (filled → filled_at set, etc.)
    """
    
    id: str
    signal_id: Optional[str]
    instrument: str
    order_type: OrderType
    side: str  # "buy" or "sell"
    quantity: float
    price_limit: Optional[float] = None
    status: OrderStatus = OrderStatus.CREATED
    created_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    
    def __post_init__(self):
        """Validate order after initialization."""
        if self.created_at is None:
            object.__setattr__(self, 'created_at', datetime.now())
        
        if self.side not in ("buy", "sell"):
            raise ValueError(f"Order side must be 'buy' or 'sell', got: {self.side}")
        
        if self.quantity <= 0:
            raise ValueError(f"Order quantity must be positive, got: {self.quantity}")
        
        if self.order_type == OrderType.LIMIT and self.price_limit is None:
            raise ValueError("LIMIT orders require price_limit")
        
        if self.order_type == OrderType.STOP_LIMIT and self.price_limit is None:
            raise ValueError("STOP_LIMIT orders require price_limit")
        
        # Validate status consistency
        if self.status == OrderStatus.FILLED and self.filled_at is None:
            raise ValueError("FILLED orders must have filled_at timestamp")
        
        if self.status == OrderStatus.CANCELED and self.canceled_at is None:
            raise ValueError("CANCELED orders must have canceled_at timestamp")
        
        if self.status == OrderStatus.REJECTED and self.rejection_reason is None:
            raise ValueError("REJECTED orders must have rejection_reason")
        
        if self.status in (OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            if self.accepted_at is None:
                raise ValueError(f"{self.status.value} orders must have accepted_at timestamp")
    
    def is_active(self) -> bool:
        """Check if order is still active (can be filled or canceled).
        
        Returns:
            True if order status is CREATED, ACCEPTED, or PARTIALLY_FILLED
        """
        return self.status in (
            OrderStatus.CREATED,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED
        )
    
    def is_terminal(self) -> bool:
        """Check if order has reached a terminal state.
        
        Returns:
            True if order is FILLED, CANCELED, or REJECTED
        """
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize order to dictionary.
        
        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            "id": self.id,
            "signal_id": self.signal_id,
            "instrument": self.instrument,
            "order_type": self.order_type.value,
            "side": self.side,
            "quantity": self.quantity,
            "price_limit": self.price_limit,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "canceled_at": self.canceled_at.isoformat() if self.canceled_at else None,
            "rejection_reason": self.rejection_reason,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Order':
        """Deserialize order from dictionary.
        
        Args:
            data: Dictionary representation (from to_dict)
            
        Returns:
            Order instance
        """
        return cls(
            id=data["id"],
            signal_id=data.get("signal_id"),
            instrument=data["instrument"],
            order_type=OrderType(data["order_type"]),
            side=data["side"],
            quantity=data["quantity"],
            price_limit=data.get("price_limit"),
            status=OrderStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            accepted_at=datetime.fromisoformat(data["accepted_at"]) if data.get("accepted_at") else None,
            filled_at=datetime.fromisoformat(data["filled_at"]) if data.get("filled_at") else None,
            canceled_at=datetime.fromisoformat(data["canceled_at"]) if data.get("canceled_at") else None,
            rejection_reason=data.get("rejection_reason"),
        )

