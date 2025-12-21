"""Capital allocation layer.

This module provides deterministic capital allocation across strategies based on
batch evaluation results and portfolio-level constraints.
"""

from .allocator import (
    AllocationConfig,
    PortfolioAllocation,
    AllocationResult,
    allocate_capital,
    persist_allocation,
    AllocationError,
)

__all__ = [
    "AllocationConfig",
    "PortfolioAllocation",
    "AllocationResult",
    "allocate_capital",
    "persist_allocation",
    "AllocationError",
]

