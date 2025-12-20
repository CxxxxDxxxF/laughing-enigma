"""Execution engine interface for paper trading.

The ExecutionEngine orchestrates order execution, position management,
and risk checks. It is engine-agnostic and can be implemented with
different execution strategies (immediate, delayed, limit-only, etc.).
"""

from typing import Dict, List, Optional
from abc import ABC, abstractmethod
from datetime import datetime

from .signal import Signal
from .order import Order
from .fill import Fill
from .position import Position


class RiskLimits:
    """Risk limits configuration for execution engine.
    
    Attributes:
        max_position_size: Maximum position size per instrument (in units)
        max_daily_loss: Maximum daily loss in dollars (negative number or None)
        max_leverage: Maximum leverage ratio (1.0 = no leverage)
        allowed_instruments: Optional list of allowed instruments (None = all allowed)
        
    Note:
        - max_daily_loss is measured from start of trading day
        - max_position_size applies to absolute quantity
        - Risk limits are checked before order acceptance
    """
    
    def __init__(
        self,
        max_position_size: Optional[float] = None,
        max_daily_loss: Optional[float] = None,
        max_leverage: float = 1.0,
        allowed_instruments: Optional[List[str]] = None
    ):
        if max_position_size is not None and max_position_size <= 0:
            raise ValueError(f"max_position_size must be positive, got: {max_position_size}")
        
        if max_daily_loss is not None and max_daily_loss >= 0:
            raise ValueError(f"max_daily_loss must be negative, got: {max_daily_loss}")
        
        if max_leverage <= 0:
            raise ValueError(f"max_leverage must be positive, got: {max_leverage}")
        
        self.max_position_size = max_position_size
        self.max_daily_loss = max_daily_loss
        self.max_leverage = max_leverage
        self.allowed_instruments = allowed_instruments
    
    def is_instrument_allowed(self, instrument: str) -> bool:
        """Check if instrument is allowed.
        
        Args:
            instrument: Instrument identifier
            
        Returns:
            True if instrument is in allowed list (or list is None)
        """
        if self.allowed_instruments is None:
            return True
        return instrument in self.allowed_instruments


class ExecutionEngineError(Exception):
    """Base exception for execution engine errors."""
    pass


class OrderRejectionError(ExecutionEngineError):
    """Exception raised when an order is rejected."""
    pass


class RiskLimitExceededError(ExecutionEngineError):
    """Exception raised when risk limits would be exceeded."""
    pass


class ExecutionEngine(ABC):
    """Abstract base class for execution engines.
    
    Execution engines orchestrate the execution domain:
    - Convert Signals to Orders
    - Validate orders against risk limits
    - Execute orders (deterministically for paper trading)
    - Manage positions
    - Track fills
    
    Key requirements:
    - Deterministic: Same inputs produce same outputs
    - Stateful: Maintains order and position state
    - Risk-aware: Enforces risk limits before execution
    - Engine-agnostic: Interface allows different execution strategies
    """
    
    @abstractmethod
    def submit_order(self, signal: Signal) -> Order:
        """Submit an order from a signal.
        
        Process:
        1. Convert Signal to Order
        2. Validate against risk limits
        3. Accept or reject order
        4. Return Order with appropriate status
        
        Args:
            signal: Signal to convert to order
            
        Returns:
            Order with status ACCEPTED or REJECTED
            
        Raises:
            ExecutionEngineError: If order cannot be processed
            RiskLimitExceededError: If risk limits would be exceeded
        """
        raise NotImplementedError
    
    @abstractmethod
    def execute_order(self, order: Order, current_price: float, timestamp: Optional[datetime] = None) -> List[Fill]:
        """Execute an order (for paper trading simulation).
        
        For paper trading, execution is deterministic based on:
        - Order type (MARKET, LIMIT, etc.)
        - Current price
        - Order parameters
        
        Args:
            order: Order to execute (must be ACCEPTED or PARTIALLY_FILLED)
            current_price: Current market price for the instrument
            timestamp: Optional timestamp for execution (defaults to now)
            
        Returns:
            List of Fills (may be empty if order cannot be filled)
            
        Raises:
            ExecutionEngineError: If order cannot be executed
            ValueError: If order is not in executable state
        """
        raise NotImplementedError
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> Order:
        """Cancel an active order.
        
        Args:
            order_id: ID of order to cancel
            
        Returns:
            Updated Order with status CANCELED
            
        Raises:
            ExecutionEngineError: If order cannot be canceled
            ValueError: If order is not in cancellable state
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_position(self, instrument: str) -> Position:
        """Get current position for an instrument.
        
        Args:
            instrument: Instrument identifier
            
        Returns:
            Position (quantity=0 if no position exists)
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID.
        
        Args:
            order_id: Order identifier
            
        Returns:
            Order if found, None otherwise
        """
        raise NotImplementedError
    
    @abstractmethod
    def list_orders(self, instrument: Optional[str] = None, status: Optional[str] = None) -> List[Order]:
        """List orders with optional filters.
        
        Args:
            instrument: Filter by instrument (None = all instruments)
            status: Filter by status (None = all statuses)
            
        Returns:
            List of matching orders
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_fills(self, order_id: str) -> List[Fill]:
        """Get all fills for an order.
        
        Args:
            order_id: Order identifier
            
        Returns:
            List of fills (may be empty)
        """
        raise NotImplementedError
    
    @abstractmethod
    def reset(self) -> None:
        """Reset engine state (for testing/new sessions).
        
        Clears all orders, positions, and fills.
        """
        raise NotImplementedError

