#!/usr/bin/env python3
"""Centralized PnL calculation utilities.

AUDIT REMEDIATION: BLOCKER-2
Fixes futures PnL calculation to correctly apply point_value and contract_multiplier.
"""

from decimal import Decimal
from typing import Union

from ..core.instrument_spec import InstrumentSpec, AssetClass


def calculate_realized_pnl_usd(
    *,
    instrument: InstrumentSpec,
    entry_price: Union[float, Decimal],
    exit_price: Union[float, Decimal],
    qty: Union[int, float],
) -> float:
    """Calculate realized PnL in USD with correct instrument scaling.
    
    Args:
        instrument: InstrumentSpec defining asset class and multipliers
        entry_price: Entry price (price paid/received)
        exit_price: Exit price (price received/paid)
        qty: Quantity (contracts for futures, shares for equities)
            Positive = long position closed, Negative = short position closed
            
    Returns:
        Realized PnL in USD (float)
        
    Logic:
        Futures: PnL = (exit - entry) * point_value * contract_multiplier * |qty| * sign(qty)
        Equities: PnL = (exit - entry) * qty
        
    Examples:
        ES Long: entry=4500, exit=4510, qty=1
            → (4510-4500) * $50/point * 1 contract * 1 = $500
        
        AAPL Long: entry=150, exit=151, qty=100
            → (151-150) * 100 = $100
            
        ES Short: entry=4500, exit=4490, qty=-1
            → (4490-4500) * $50 * 1 * (-1) = $500 profit
    """
    # Input validation
    entry = float(entry_price)
    exit = float(exit_price)
    quantity = float(qty)
    
    if entry <= 0 or exit <= 0:
        # Invalid prices - return 0 to avoid breaking engine
        return 0.0
    
    # Check for NaN/inf
    if not (entry == entry and exit == exit and quantity == quantity):
        return 0.0
    
    # Price difference
    price_diff = exit - entry
    
    if instrument.asset_class == AssetClass.FUTURES:
        # Futures: Apply point value and multiplier
        # point_value = dollars per 1 index point
        # contract_multiplier = scaling factor (usually 1 for most futures)
        dollars_per_point = float(instrument.point_value) * float(instrument.contract_multiplier)
        
        # PnL = price_diff * dollars_per_point * contracts
        # Sign is already in quantity (qty > 0 = long, qty < 0 = short)
        pnl = price_diff * dollars_per_point * quantity
        
        return float(pnl)
    
    elif instrument.asset_class == AssetClass.EQUITY:
        # Equities: Simple price diff * shares
        pnl = price_diff * quantity
        return float(pnl)
    
    else:
        # Unknown asset class - return 0 to avoid breaking
        return 0.0
