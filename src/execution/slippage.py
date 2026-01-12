#!/usr/bin/env python3
"""Deterministic volatility-scaled slippage model.

Provides realistic slippage estimation for backtest and paper trading:
- Volatility-scaled: higher vol → higher slippage
- Asset-class aware: futures vs equities have different defaults
- Order-type aware: market > stop > limit slippage
- Deterministic: no randomness, same inputs → same outputs
- Bounded: all slippage capped at max_ticks
- Tick-rounded: all price adjustments respect instrument tick_size

Key principles:
1. Conservative but realistic (not overly pessimistic)
2. Monotonic in volatility metric
3. Transparent (returns ticks + price impact)
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional

from ..core.instrument_spec import InstrumentSpec, AssetClass


@dataclass(frozen=True)
class SlippageConfig:
    """Configuration for slippage calculation.
    
    Attributes:
        base_ticks: Minimum slippage in ticks (spread cost)
        vol_sensitivity: Additional ticks per 1.0 unit of vol_metric
        max_ticks: Maximum slippage cap
        order_type_multipliers: Multipliers by order type
        liquidity_penalty_ticks: Additional ticks for low liquidity
    """
    base_ticks: int
    vol_sensitivity: float
    max_ticks: int
    order_type_multipliers: Dict[str, float]
    liquidity_penalty_ticks: int = 0
    
    def __post_init__(self):
        """Validate config."""
        if self.base_ticks < 0:
            raise ValueError(f"base_ticks must be >= 0, got {self.base_ticks}")
        if self.vol_sensitivity < 0:
            raise ValueError(f"vol_sensitivity must be >= 0, got {self.vol_sensitivity}")
        if self.max_ticks < self.base_ticks:
            raise ValueError(f"max_ticks ({self.max_ticks}) must be >= base_ticks ({self.base_ticks})")


# Default configs by asset class
FUTURES_SLIPPAGE_CONFIG = SlippageConfig(
    base_ticks=1,  # Tight spreads for liquid futures
    vol_sensitivity=3.0,  # 3 ticks per 1.0 vol unit
    max_ticks=10,  # Cap at 10 ticks (reasonable for ES)
    order_type_multipliers={
        "MARKET": 1.0,
        "STOP": 0.8,  # Stops slightly better than market
        "LIMIT": 0.0,  # Limits get their price or no fill
    },
)

EQUITY_SLIPPAGE_CONFIG = SlippageConfig(
    base_ticks=2,  # Wider spreads than futures
    vol_sensitivity=5.0,  # 5 ticks per 1.0 vol unit
    max_ticks=20,  # Higher cap for gap scenarios
    order_type_multipliers={
        "MARKET": 1.0,
        "STOP": 0.7,  # Stops better than market (often fill at stop)
        "LIMIT": 0.0,  # Limits get their price
    },
)


def default_slippage_config_for(instrument: InstrumentSpec) -> SlippageConfig:
    """Get default slippage config for instrument.
    
    Args:
        instrument: InstrumentSpec instance
        
    Returns:
        Default SlippageConfig for asset class
    """
    if instrument.asset_class == AssetClass.FUTURES:
        return FUTURES_SLIPPAGE_CONFIG
    elif instrument.asset_class == AssetClass.EQUITY:
        return EQUITY_SLIPPAGE_CONFIG
    else:
        # Conservative default for unknown asset classes
        return EQUITY_SLIPPAGE_CONFIG


def compute_slippage_ticks(
    *,
    instrument: InstrumentSpec,
    order_type: str,
    vol_metric: float = 0.0,
    config: Optional[SlippageConfig] = None,
) -> int:
    """Compute slippage in tick units.
    
    Args:
        instrument: InstrumentSpec for asset-class defaults
        order_type: "MARKET", "STOP", or "LIMIT"
        vol_metric: Volatility metric (>= 0, e.g., ATR% or realized vol)
        config: Optional SlippageConfig (uses defaults if None)
        
    Returns:
        Non-negative integer tick slippage, bounded by config.max_ticks
        
    Formula:
        base = config.base_ticks
        vol_penalty = config.vol_sensitivity * vol_metric
        order_multiplier = config.order_type_multipliers[order_type]
        liquidity_penalty = config.liquidity_penalty_ticks
        
        raw_ticks = (base + vol_penalty + liquidity_penalty) * order_multiplier
        final_ticks = min(raw_ticks, config.max_ticks)
        
    Returns:
        max(0, int(final_ticks))
    """
    if vol_metric < 0:
        raise ValueError(f"vol_metric must be >= 0, got {vol_metric}")
    
    # Get config
    if config is None:
        config = default_slippage_config_for(instrument)
    
    # Normalize order type
    order_type = order_type.upper()
    if order_type not in config.order_type_multipliers:
        raise ValueError(
            f"Unknown order_type: {order_type}. "
            f"Valid: {list(config.order_type_multipliers.keys())}"
        )
    
    # Calculate components
    base = config.base_ticks
    vol_penalty = config.vol_sensitivity * vol_metric
    liquidity_penalty = config.liquidity_penalty_ticks
    order_multiplier = config.order_type_multipliers[order_type]
    
    # Total before cap
    raw_ticks = (base + vol_penalty + liquidity_penalty) * order_multiplier
    
    # Apply cap
    final_ticks = min(raw_ticks, config.max_ticks)
    
    # Ensure non-negative integer
    return max(0, int(final_ticks))


def apply_slippage_to_price(
    *,
    instrument: InstrumentSpec,
    side: str,
    base_price: Decimal,
    slippage_ticks: int,
) -> Decimal:
    """Apply slippage to base price.
    
    Args:
        instrument: InstrumentSpec for tick_size
        side: "BUY" or "SELL"
        base_price: Price before slippage
        slippage_ticks: Slippage in tick units
        
    Returns:
        Tick-rounded adjusted price:
        - BUY: price increases (pay more)
        - SELL: price decreases (receive less)
    """
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be 'BUY' or 'SELL', got {side}")
    
    # Calculate slippage in price units
    slippage_amount = Decimal(slippage_ticks) * instrument.tick_size
    
    # Apply based on side
    if side == "BUY":
        adjusted_price = base_price + slippage_amount
    else:  # SELL
        adjusted_price = base_price - slippage_amount
    
    # Round to tick
    return instrument.round_to_tick(adjusted_price)


def compute_gap_slippage_ticks(
    *,
    instrument: InstrumentSpec,
    order_type: str,
    gap_size_ticks: int,
    vol_metric: float = 0.0,
    config: Optional[SlippageConfig] = None,
) -> int:
    """Compute slippage for gap scenario with additional gap penalty.
    
    For stop orders gapped through, add gap-based penalty on top of vol penalty.
    
    Args:
        instrument: InstrumentSpec
        order_type: "MARKET", "STOP", or "LIMIT"
        gap_size_ticks: Size of gap in ticks
        vol_metric: Volatility metric
        config: Optional SlippageConfig
        
    Returns:
        Total slippage ticks (base + vol + gap penalty)
    """
    # Get base slippage from vol
    base_slippage = compute_slippage_ticks(
        instrument=instrument,
        order_type=order_type,
        vol_metric=vol_metric,
        config=config,
    )
    
    # Add gap penalty (10% of gap size, capped)
    gap_penalty = min(int(gap_size_ticks * 0.1), 5)  # Max 5 tick gap penalty
    
    total_slippage = base_slippage + gap_penalty
    
    # Apply config max
    if config is None:
        config = default_slippage_config_for(instrument)
    
    return min(total_slippage, config.max_ticks)
