"""Broker adapter abstraction for broker-agnostic trading.

This module provides the abstraction layer for broker integration,
enabling:
- LIVE_DRY: NullBrokerAdapter (deterministic mock)
- LIVE: Real broker adapters (Topstep, Apex, etc.)

All broker-specific logic is isolated in adapters.
Rules, runner, and limits logic remain broker-agnostic.
"""

from .adapter import BrokerAdapter, AccountMetadata, BrokerAdapterError
from .null import NullBrokerAdapter

__all__ = [
    "BrokerAdapter",
    "AccountMetadata",
    "BrokerAdapterError",
    "NullBrokerAdapter",
]

