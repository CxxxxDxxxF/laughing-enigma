"""LIVE trading invariants and requirements.

This module documents and stubs the "must-have" LIVE invariants
based on verified funded account rules.

These are NOT yet implemented - they are pinned as contracts
to prevent architectural leaks before broker integration.

Status: TODO - Implementation blocked on broker integration
"""

from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class ProtectiveStopRequirement:
    """Protective stop requirement for LIVE accounts.
    
    TODO: Implement protective stop enforcement.
    
    Based on verified rules:
    - All positions must have protective stops
    - Stops must be set before or immediately after entry
    - Stop levels must be within firm-defined limits
    
    Status: NOT IMPLEMENTED
    """
    pass


@dataclass
class AutoFlattenRequirement:
    """Pre-3:10 PM CT auto-flatten requirement.
    
    TODO: Implement auto-flatten logic.
    
    Based on verified rules:
    - All positions must be flattened before 3:10 PM CT
    - System must automatically close positions if not manually closed
    - This prevents overnight risk
    
    Status: NOT IMPLEMENTED
    """
    pass


@dataclass
class HolidaySchedule:
    """Holiday schedule for trading days.
    
    TODO: Implement holiday calendar.
    
    Based on verified rules:
    - Trading is not allowed on firm-defined holidays
    - Holiday schedule may vary by firm (Topstep, Apex, etc.)
    - System must check holidays before allowing trades
    
    Status: NOT IMPLEMENTED
    """
    pass


def check_protective_stops_required(timestamp: datetime) -> bool:
    """Check if protective stops are required at this timestamp.
    
    TODO: Implement based on firm rules.
    
    Args:
        timestamp: Current timestamp
        
    Returns:
        True if protective stops are required
        
    Raises:
        NotImplementedError: Until broker integration
    """
    raise NotImplementedError(
        "Protective stop enforcement not yet implemented. "
        "Blocked on broker integration."
    )


def check_auto_flatten_required(timestamp: datetime) -> bool:
    """Check if auto-flatten is required at this timestamp.
    
    TODO: Implement based on firm rules (e.g., before 3:10 PM CT).
    
    Args:
        timestamp: Current timestamp
        
    Returns:
        True if positions must be flattened
        
    Raises:
        NotImplementedError: Until broker integration
    """
    raise NotImplementedError(
        "Auto-flatten enforcement not yet implemented. "
        "Blocked on broker integration."
    )


def is_trading_holiday(date: datetime.date, firm: str) -> bool:
    """Check if a date is a trading holiday for the given firm.
    
    TODO: Implement holiday calendar per firm.
    
    Args:
        date: Date to check
        firm: Firm name (e.g., "topstep", "apex")
        
    Returns:
        True if date is a holiday (no trading)
        
    Raises:
        NotImplementedError: Until holiday calendar implementation
    """
    raise NotImplementedError(
        f"Holiday calendar not yet implemented for {firm}. "
        "Blocked on firm-specific calendar data."
    )


def get_auto_flatten_deadline(timestamp: datetime, firm: str) -> Optional[datetime]:
    """Get the auto-flatten deadline for the current trading session.
    
    TODO: Implement based on firm rules (e.g., 3:10 PM CT for Topstep).
    
    Args:
        timestamp: Current timestamp
        firm: Firm name
        
    Returns:
        Datetime when positions must be flattened, or None if not applicable
        
    Raises:
        NotImplementedError: Until firm-specific rules implementation
    """
    raise NotImplementedError(
        f"Auto-flatten deadline calculation not yet implemented for {firm}. "
        "Blocked on firm-specific rules."
    )

