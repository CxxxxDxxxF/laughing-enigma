"""Signal consumer for routing Signals to ExecutionEngine.

This module defines the interface for consuming validated Signals and
routing them to execution engines.
"""

from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
from datetime import datetime

from ..execution import Signal, ExecutionEngine, Order


class SignalConsumer(ABC):
    """Abstract interface for consuming Signals and routing to ExecutionEngine.
    
    SignalConsumer receives validated Signals from SignalAdapter and
    submits them to ExecutionEngine. It maintains the signal → order
    mapping for auditability.
    
    Responsibilities:
    1. Receive Signals from adapter
    2. Route to appropriate ExecutionEngine
    3. Track signal → order mapping
    4. Handle execution results
    
    Characteristics:
    - Synchronous consumption (no async queues)
    - Deterministic routing
    - Maintains signal provenance
    """
    
    @abstractmethod
    def consume_signal(
        self,
        signal: Signal,
        execution_engine: ExecutionEngine,
        execution_context: Optional[Dict[str, Any]] = None
    ) -> Order:
        """Consume a Signal and submit to ExecutionEngine.
        
        Process:
        1. Receive validated Signal
        2. Submit to ExecutionEngine (converts to Order)
        3. Track signal → order mapping
        4. Return created Order
        
        Args:
            signal: Validated Signal from SignalAdapter
            execution_engine: ExecutionEngine to submit to
            execution_context: Optional context (e.g., current price for execution)
            
        Returns:
            Order created from Signal
            
        Raises:
            ExecutionEngineError: If order submission fails
            OrderRejectionError: If order is rejected by engine
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_signal_order_mapping(self, signal_id: Optional[str] = None) -> Dict[str, str]:
        """Get mapping of signal identifiers to order identifiers.
        
        Args:
            signal_id: Optional signal ID to filter by
            
        Returns:
            Dictionary mapping signal_id → order_id
            
        Note:
            Used for auditability and tracing execution back to research.
        """
        raise NotImplementedError
    
    @abstractmethod
    def reset(self) -> None:
        """Reset consumer state (for testing/new sessions).
        
        Clears signal → order mappings.
        """
        raise NotImplementedError

