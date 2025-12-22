"""ID provider abstraction for deterministic ID generation.

This module provides ID generation abstractions that allow execution engines
to use deterministic IDs in LIVE mode while preserving flexibility in SIMULATION mode.

In LIVE mode, all IDs (order IDs, fill IDs) should be deterministic to ensure
replayability and audit trail consistency.

In SIMULATION mode, engines can use UUIDs for realistic behavior.
"""

from abc import ABC, abstractmethod
import uuid
from typing import Optional, Dict


class IDProvider(ABC):
    """Abstract ID provider interface for execution ID generation.
    
    Execution engines call provider methods to generate IDs instead of
    using uuid.uuid4() directly. This allows deterministic ID control in LIVE mode.
    """
    
    @abstractmethod
    def new_order_id(self, signal_id: Optional[str] = None) -> str:
        """Generate a new order ID.
        
        Args:
            signal_id: Optional signal ID to derive order ID from
            
        Returns:
            Order ID string
        """
        raise NotImplementedError
    
    @abstractmethod
    def new_fill_id(self, order_id: str) -> str:
        """Generate a new fill ID for an order.
        
        Args:
            order_id: Order ID this fill belongs to
            
        Returns:
            Fill ID string
        """
        raise NotImplementedError
    
    @abstractmethod
    def new_session_id(self) -> str:
        """Generate a new session ID.
        
        Returns:
            Session ID string
        """
        raise NotImplementedError


class SimulationIDProvider(IDProvider):
    """ID provider that uses UUIDs (for SIMULATION mode).
    
    Generates random UUIDs for all IDs, providing realistic behavior
    for backtesting and simulation.
    """
    
    def new_order_id(self, signal_id: Optional[str] = None) -> str:
        """Generate random UUID for order ID.
        
        Args:
            signal_id: Ignored (uses UUID)
            
        Returns:
            Random UUID string
        """
        return str(uuid.uuid4())
    
    def new_fill_id(self, order_id: str) -> str:
        """Generate random UUID for fill ID.
        
        Args:
            order_id: Ignored (uses UUID)
            
        Returns:
            Random UUID string
        """
        return str(uuid.uuid4())
    
    def new_session_id(self) -> str:
        """Generate random UUID for session ID.
        
        Returns:
            Random UUID string
        """
        return str(uuid.uuid4())


class DeterministicIDProvider(IDProvider):
    """ID provider that generates deterministic IDs (for LIVE mode).
    
    Generates deterministic IDs based on seed and namespace counters, ensuring
    identical inputs produce identical IDs.
    
    Format:
    - order_id: {seed}_order_{counter:06d}
    - fill_id: {order_id}_fill_{fill_counter:03d}
    - session_id: {seed}_session
    """
    
    def __init__(self, seed: str):
        """Initialize deterministic ID provider.
        
        Args:
            seed: Seed for generated IDs (typically cycle_id or cycle_timestamp.isoformat())
        """
        self.seed = seed
        self._order_counter = 0
        self._fill_counters: Dict[str, int] = {}  # order_id -> fill counter
    
    def new_order_id(self, signal_id: Optional[str] = None) -> str:
        """Generate deterministic order ID.
        
        Args:
            signal_id: Optional signal ID (ignored, uses counter for determinism)
            
        Returns:
            Deterministic order ID string: {seed}_order_{counter:06d}
        """
        self._order_counter += 1
        return f"{self.seed}_order_{self._order_counter:06d}"
    
    def new_fill_id(self, order_id: str) -> str:
        """Generate deterministic fill ID.
        
        Args:
            order_id: Order ID this fill belongs to
            
        Returns:
            Deterministic fill ID string: {order_id}_fill_{counter:03d}
        """
        if order_id not in self._fill_counters:
            self._fill_counters[order_id] = 0
        self._fill_counters[order_id] += 1
        fill_counter = self._fill_counters[order_id]
        return f"{order_id}_fill_{fill_counter:03d}"
    
    def new_session_id(self) -> str:
        """Generate deterministic session ID.
        
        Returns:
            Deterministic session ID string: {seed}_session
        """
        return f"{self.seed}_session"

