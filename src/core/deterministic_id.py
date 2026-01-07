"""Deterministic ID generation utilities.

This module provides utilities for generating deterministic IDs based on
input hashing, ensuring reproducibility across runs.
"""

import hashlib
import json
from typing import Any, Dict, Optional


def generate_deterministic_id(
    prefix: str,
    inputs: Dict[str, Any],
    max_length: int = 32
) -> str:
    """Generate a deterministic ID based on input hash.
    
    Process:
    1. Serialize inputs to JSON (sorted keys for determinism)
    2. Compute SHA-256 hash
    3. Return prefix + truncated hash
    
    Args:
        prefix: Prefix for the ID (e.g., "cycle", "alloc", "eval")
        inputs: Dictionary of inputs to hash
        max_length: Maximum length of hash portion (default: 32)
        
    Returns:
        Deterministic ID string
        
    Example:
        >>> inputs = {"strategy_id": "strat_1", "total_capital": 100000}
        >>> generate_deterministic_id("alloc", inputs)
        'alloc_a1b2c3d4e5f6...'
    """
    # Serialize inputs deterministically
    input_json = json.dumps(inputs, sort_keys=True, default=str)
    
    # Compute hash
    hash_bytes = hashlib.sha256(input_json.encode('utf-8')).hexdigest()
    
    # Truncate and combine with prefix
    truncated_hash = hash_bytes[:max_length]
    return f"{prefix}_{truncated_hash}"


def generate_cycle_id(
    portfolio_id: str,
    cycle_timestamp_iso: str,
    config_hash: Optional[str] = None
) -> str:
    """Generate deterministic cycle ID.
    
    Args:
        portfolio_id: Portfolio identifier
        cycle_timestamp_iso: Cycle timestamp in ISO format
        config_hash: Optional hash of cycle configuration
        
    Returns:
        Deterministic cycle ID
    """
    inputs = {
        "portfolio_id": portfolio_id,
        "timestamp": cycle_timestamp_iso,
    }
    if config_hash:
        inputs["config_hash"] = config_hash
    
    return generate_deterministic_id("cycle", inputs, max_length=16)


def generate_allocation_id(
    total_capital: float,
    strategy_ids: list,
    allocation_method: str
) -> str:
    """Generate deterministic allocation ID.
    
    Args:
        total_capital: Total capital for allocation
        strategy_ids: List of strategy IDs
        allocation_method: Allocation method name
        
    Returns:
        Deterministic allocation ID
    """
    inputs = {
        "total_capital": total_capital,
        "strategy_ids": sorted(strategy_ids),
        "method": allocation_method,
    }
    return generate_deterministic_id("alloc", inputs, max_length=16)


def generate_rebalance_id(
    allocation_id: str,
    portfolio_state_hash: str
) -> str:
    """Generate deterministic rebalance plan ID.
    
    Args:
        allocation_id: Allocation ID that triggered rebalance
        portfolio_state_hash: Hash of current portfolio state
        
    Returns:
        Deterministic rebalance plan ID
    """
    inputs = {
        "allocation_id": allocation_id,
        "state_hash": portfolio_state_hash,
    }
    return generate_deterministic_id("rebalance", inputs, max_length=16)


def generate_execution_id(
    plan_id: str,
    execution_timestamp_iso: str
) -> str:
    """Generate deterministic execution ID.
    
    Args:
        plan_id: Rebalance plan ID
        execution_timestamp_iso: Execution timestamp in ISO format
        
    Returns:
        Deterministic execution ID
    """
    inputs = {
        "plan_id": plan_id,
        "timestamp": execution_timestamp_iso,
    }
    return generate_deterministic_id("exec", inputs, max_length=16)
