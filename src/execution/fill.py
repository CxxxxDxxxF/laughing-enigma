"""Fill definition for execution results.

A Fill represents what actually happened when an order was executed.
Multiple Fills can satisfy a single Order (partial fills).
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Fill:
    """Immutable fill record.
    
    A Fill represents the execution of part or all of an Order.
    One Order can have multiple Fills (partial execution).
    
    Attributes:
        id: Unique fill identifier
        order_id: ID of the Order this fill belongs to
        instrument: Instrument identifier
        side: "buy" or "sell" (must match order side)
        quantity: Quantity filled (positive number, <= order quantity)
        price: Execution price
        fee: Transaction fee/cost (non-negative)
        filled_at: Timestamp when fill occurred
        execution_id: Optional execution engine identifier
        
    Note:
        - Quantity is always positive
        - Price must be positive
        - Fee is non-negative (can be zero)
        - Sum of fill quantities for an order should not exceed order quantity
    """
    
    id: str
    order_id: str
    instrument: str
    side: str  # "buy" or "sell"
    quantity: float
    price: float
    fee: float = 0.0
    filled_at: datetime = None
    execution_id: Optional[str] = None
    
    def __post_init__(self):
        """Validate fill after initialization."""
        if self.filled_at is None:
            object.__setattr__(self, 'filled_at', datetime.now())
        
        if self.side not in ("buy", "sell"):
            raise ValueError(f"Fill side must be 'buy' or 'sell', got: {self.side}")
        
        if self.quantity <= 0:
            raise ValueError(f"Fill quantity must be positive, got: {self.quantity}")
        
        if self.price <= 0:
            raise ValueError(f"Fill price must be positive, got: {self.price}")
        
        if self.fee < 0:
            raise ValueError(f"Fill fee must be non-negative, got: {self.fee}")
    
    @property
    def timestamp(self) -> datetime:
        """Canonical timestamp property (maps to filled_at).
        
        Returns:
            Timestamp when fill occurred (same as filled_at)
        """
        return self.filled_at if self.filled_at else datetime.now()
    
    def gross_value(self) -> float:
        """Compute gross value of fill (before fees).
        
        Returns:
            quantity * price
        """
        return self.quantity * self.price
    
    def net_value(self) -> float:
        """Compute net value of fill (after fees).
        
        Returns:
            gross_value() - fee
            
        Note:
            For BUY: net_value is what was paid (including fee)
            For SELL: net_value is what was received (minus fee)
        """
        return self.gross_value() - self.fee if self.side == "sell" else self.gross_value() + self.fee
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize fill to dictionary.
        
        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            "id": self.id,
            "order_id": self.order_id,
            "instrument": self.instrument,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "fee": self.fee,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "execution_id": self.execution_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Fill':
        """Deserialize fill from dictionary.
        
        Args:
            data: Dictionary representation (from to_dict)
            
        Returns:
            Fill instance
        """
        return cls(
            id=data["id"],
            order_id=data["order_id"],
            instrument=data["instrument"],
            side=data["side"],
            quantity=data["quantity"],
            price=data["price"],
            fee=data.get("fee", 0.0),
            filled_at=datetime.fromisoformat(data["filled_at"]) if data.get("filled_at") else None,
            execution_id=data.get("execution_id"),
        )

