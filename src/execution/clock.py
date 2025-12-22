"""Execution clock abstraction for deterministic timestamp generation.

This module provides clock abstractions that allow execution engines to
use deterministic timestamps in LIVE mode while preserving flexibility
in SIMULATION mode.

In LIVE mode, all timestamps (order creation, fill execution) must come
from a single source of truth (the cycle_timestamp) to avoid clock skew
and ensure deterministic replay.

In SIMULATION mode, engines can use system time for realistic behavior.
"""

from abc import ABC, abstractmethod
from datetime import datetime


class ExecutionClock(ABC):
    """Abstract clock interface for execution timestamp generation.
    
    Execution engines call clock.now() instead of datetime.now() to get
    timestamps. This allows deterministic timestamp control in LIVE mode.
    """
    
    @abstractmethod
    def now(self) -> datetime:
        """Get current timestamp.
        
        Returns:
            Current timestamp according to this clock's implementation
        """
        raise NotImplementedError


class SimulationClock(ExecutionClock):
    """Clock that uses system time (for SIMULATION mode).
    
    Returns datetime.now() on each call, providing realistic timestamp
    behavior for backtesting and simulation.
    """
    
    def now(self) -> datetime:
        """Get current system time.
        
        Returns:
            Current system datetime
        """
        return datetime.now()


class FixedClock(ExecutionClock):
    """Clock that returns a fixed timestamp (for LIVE mode).
    
    Always returns the same timestamp, ensuring deterministic execution
    and preventing clock skew in LIVE mode. All order and fill timestamps
    within a cycle will be identical, which is acceptable for paper trading
    and ensures replayability.
    
    Attributes:
        timestamp: Fixed timestamp to return
    """
    
    def __init__(self, timestamp: datetime):
        """Initialize fixed clock with a timestamp.
        
        Args:
            timestamp: Fixed timestamp to return on all now() calls
        """
        self.timestamp = timestamp
    
    def now(self) -> datetime:
        """Get the fixed timestamp.
        
        Returns:
            The fixed timestamp set at initialization
        """
        return self.timestamp

