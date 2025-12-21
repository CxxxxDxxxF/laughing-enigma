"""Simple signal consumer implementation.

This module provides a minimal SignalConsumer that submits Signals
directly to an ExecutionEngine.
"""

import uuid
from typing import Dict, Any, Optional

from .consumer import SignalConsumer
from ..execution import Signal, ExecutionEngine, Order, ExecutionEngineError, OrderRejectionError


class SimpleSignalConsumer(SignalConsumer):
    """Simple signal consumer that submits Signals to ExecutionEngine.
    
    This consumer:
    - Receives validated Signals
    - Submits to ExecutionEngine immediately (synchronous)
    - Tracks signal → order mapping
    - Returns created Orders
    
    This is a minimal implementation for testing the signal pipeline.
    
    Attributes:
        signal_order_map: Dictionary mapping signal identifiers to order IDs
    """
    
    def __init__(self):
        """Initialize simple signal consumer."""
        self.signal_order_map: Dict[str, str] = {}
    
    def consume_signal(
        self,
        signal: Signal,
        execution_engine: ExecutionEngine,
        execution_context: Optional[Dict[str, Any]] = None
    ) -> Order:
        """Consume a Signal and submit to ExecutionEngine.
        
        Process:
        1. Submit Signal to ExecutionEngine
        2. Track signal → order mapping (using signal timestamp as key)
        3. Return created Order
        
        Args:
            signal: Validated Signal from SignalAdapter
            execution_engine: ExecutionEngine to submit to
            execution_context: Optional context (currently unused for simple consumer)
            
        Returns:
            Order created from Signal
            
        Raises:
            ExecutionEngineError: If order submission fails
            OrderRejectionError: If order is rejected by engine
        """
        # Submit signal to execution engine
        try:
            order = execution_engine.submit_order(signal)
        except Exception as e:
            raise ExecutionEngineError(f"Failed to submit signal to execution engine: {e}") from e
        
        # Track signal → order mapping
        # Use a combination of timestamp and instrument as signal identifier
        # (since Signal doesn't have an explicit ID, we generate one)
        signal_id = f"{signal.timestamp.isoformat()}_{signal.instrument}_{signal.signal_type.value}"
        self.signal_order_map[signal_id] = order.id
        
        return order
    
    def get_signal_order_mapping(self, signal_id: Optional[str] = None) -> Dict[str, str]:
        """Get mapping of signal identifiers to order identifiers.
        
        Args:
            signal_id: Optional signal ID to filter by
            
        Returns:
            Dictionary mapping signal_id → order_id
            If signal_id provided, returns single-item dict if found, empty dict otherwise
        """
        if signal_id is None:
            return self.signal_order_map.copy()
        
        if signal_id in self.signal_order_map:
            return {signal_id: self.signal_order_map[signal_id]}
        
        return {}
    
    def reset(self) -> None:
        """Reset consumer state (for testing/new sessions).
        
        Clears signal → order mappings.
        """
        self.signal_order_map.clear()

