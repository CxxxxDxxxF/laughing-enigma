"""Integration layer between research and execution domains.

This module provides interfaces and adapters that connect research outputs
(strategy signals) to execution inputs (execution-ready signals).

Key components:
- SignalEmitter: Interface for emitting raw strategy outputs
- SignalAdapter: Transforms raw outputs into execution-ready Signals
- SignalConsumer: Routes validated Signals to ExecutionEngine
"""

from .emitter import SignalEmitter, RawStrategyOutput
from .adapter import SignalAdapter, SignalAdapterError, AdapterConfig, InvalidSignalError, RiskCheckError
from .consumer import SignalConsumer
from .simple_emitter import SimpleSignalEmitter
from .simple_adapter import SimpleSignalAdapter
from .simple_consumer import SimpleSignalConsumer
from .pipeline import execute_signals_from_raw_returns

__all__ = [
    "SignalEmitter",
    "RawStrategyOutput",
    "SignalAdapter",
    "SignalAdapterError",
    "InvalidSignalError",
    "RiskCheckError",
    "AdapterConfig",
    "SignalConsumer",
    "SimpleSignalEmitter",
    "SimpleSignalAdapter",
    "SimpleSignalConsumer",
    "execute_signals_from_raw_returns",
]

