"""Limits provider abstraction for broker-agnostic limit management.

This module provides the abstraction layer for retrieving trading limits
from brokers or deterministic sources, enabling:
- LIVE_DRY: Deterministic testing with fixed limits
- LIVE: Broker API integration (placeholder for now)
- Multi-firm support: Topstep, Apex, etc.
"""

from .provider import LimitsProvider, TradingSession
from .deterministic import DeterministicLimitsProvider
from .broker import BrokerLimitsProvider

__all__ = [
    "LimitsProvider",
    "TradingSession",
    "DeterministicLimitsProvider",
    "BrokerLimitsProvider",
]

