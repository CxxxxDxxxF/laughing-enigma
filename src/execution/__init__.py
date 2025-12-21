"""Execution domain for paper trading.

This module defines the execution domain primitives:
- Signal: Strategy output/intent
- Order: Trade request
- Fill: Execution result
- Position: Current holdings state
- ExecutionEngine: Execution orchestration

These concepts are separate from the research domain and handle
"what actually happened" vs "what should I do".
"""

from .signal import Signal, SignalType
from .order import Order, OrderStatus, OrderType
from .fill import Fill
from .position import Position
from .engine import ExecutionEngine, ExecutionEngineError, RiskLimitExceededError, OrderRejectionError, RiskLimits
from .paper_engine import PaperExecutionEngine

__all__ = [
    "Signal",
    "SignalType",
    "Order",
    "OrderStatus",
    "OrderType",
    "Fill",
    "Position",
    "ExecutionEngine",
    "ExecutionEngineError",
    "RiskLimitExceededError",
    "OrderRejectionError",
    "RiskLimits",
    "PaperExecutionEngine",
]

