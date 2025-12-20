"""Position definition for current holdings state.

A Position represents the current state of holdings for an instrument.
Positions are updated by Fills.
"""

from typing import Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Position:
    """Immutable position record.
    
    A Position represents the current holdings state for an instrument.
    Positions are updated deterministically by applying Fills.
    
    Attributes:
        instrument: Instrument identifier
        quantity: Current quantity held (positive = long, negative = short, zero = flat)
        cost_basis: Average cost per unit (always positive, even for shorts)
        realized_pnl: Cumulative realized profit/loss (can be negative)
        updated_at: Timestamp of last position update
        
    Note:
        - Quantity can be positive (long), negative (short), or zero (flat)
        - Cost basis is always positive (represents average entry price)
        - Realized PnL accumulates as positions are closed
        - Unrealized PnL is not stored (computed from current price)
    """
    
    instrument: str
    quantity: float
    cost_basis: float
    realized_pnl: float = 0.0
    updated_at: datetime = None
    
    def __post_init__(self):
        """Validate position after initialization."""
        if self.updated_at is None:
            object.__setattr__(self, 'updated_at', datetime.now())
        
        if self.cost_basis <= 0:
            raise ValueError(f"Cost basis must be positive, got: {self.cost_basis}")
    
    def is_long(self) -> bool:
        """Check if position is long.
        
        Returns:
            True if quantity > 0
        """
        return self.quantity > 0
    
    def is_short(self) -> bool:
        """Check if position is short.
        
        Returns:
            True if quantity < 0
        """
        return self.quantity < 0
    
    def is_flat(self) -> bool:
        """Check if position is flat (no holdings).
        
        Returns:
            True if quantity == 0
        """
        return self.quantity == 0
    
    def absolute_quantity(self) -> float:
        """Get absolute value of quantity.
        
        Returns:
            abs(quantity)
        """
        return abs(self.quantity)
    
    def total_cost(self) -> float:
        """Compute total cost basis.
        
        Returns:
            abs(quantity) * cost_basis
            
        Note:
            This is the total capital allocated to this position,
            regardless of whether it's long or short.
        """
        return self.absolute_quantity() * self.cost_basis
    
    def apply_fill(self, fill: 'Fill') -> 'Position':
        """Create new position by applying a fill.
        
        This is a pure function that computes the new position state
        after a fill. Used for deterministic position updates.
        
        Args:
            fill: Fill to apply to this position
            
        Returns:
            New Position with updated state
            
        Raises:
            ValueError: If fill instrument doesn't match position instrument
            
        Note:
            This method implements the position update logic:
            - Long positions increase with BUY fills, decrease with SELL fills
            - Cost basis is updated using weighted average
            - Realized PnL is computed when closing or reversing positions
        """
        if fill.instrument != self.instrument:
            raise ValueError(
                f"Fill instrument {fill.instrument} does not match position instrument {self.instrument}"
            )
        
        # Determine new quantity
        if fill.side == "buy":
            new_quantity = self.quantity + fill.quantity
        else:  # sell
            new_quantity = self.quantity - fill.quantity
        
        # Compute new cost basis and realized PnL
        if new_quantity == 0:
            # Position closed: compute realized PnL on all shares
            if self.is_long():
                # Closing long: sold at fill.price
                realized_pnl_delta = (fill.price - self.cost_basis) * abs(self.quantity)
            else:
                # Closing short: bought at fill.price
                realized_pnl_delta = (self.cost_basis - fill.price) * abs(self.quantity)
            
            new_cost_basis = self.cost_basis  # Keep for reference, not used
            new_realized_pnl = self.realized_pnl + realized_pnl_delta
            
        elif (self.quantity > 0 and new_quantity > 0) or (self.quantity < 0 and new_quantity < 0):
            # Same direction (adding to position): update cost basis using weighted average
            # For reducing position, we need to realize PnL on the closed portion
            old_abs_qty = abs(self.quantity)
            new_abs_qty = abs(new_quantity)
            
            if new_abs_qty < old_abs_qty:
                # Reducing position: realize PnL on closed portion, keep cost basis for remainder
                closed_qty = old_abs_qty - new_abs_qty
                if self.is_long():
                    realized_pnl_delta = (fill.price - self.cost_basis) * closed_qty
                else:
                    realized_pnl_delta = (self.cost_basis - fill.price) * closed_qty
                new_cost_basis = self.cost_basis  # Cost basis unchanged for remaining shares
                new_realized_pnl = self.realized_pnl + realized_pnl_delta
            else:
                # Adding to position: weighted average cost basis
                total_cost = self.total_cost() + fill.gross_value()
                new_cost_basis = total_cost / new_abs_qty
                new_realized_pnl = self.realized_pnl
            
        else:
            # Position reversed: close old position, open new
            closed_quantity = abs(self.quantity)
            if self.is_long():
                # Closing long position, opening short
                realized_pnl_delta = (fill.price - self.cost_basis) * closed_quantity
            else:
                # Closing short position, opening long
                realized_pnl_delta = (self.cost_basis - fill.price) * closed_quantity
            
            # New position cost basis is fill price
            new_cost_basis = fill.price
            new_realized_pnl = self.realized_pnl + realized_pnl_delta
        
        return Position(
            instrument=self.instrument,
            quantity=new_quantity,
            cost_basis=new_cost_basis,
            realized_pnl=new_realized_pnl,
            updated_at=datetime.now()
        )

