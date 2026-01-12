#!/usr/bin/env python3
"""Gap-aware fill simulation for realistic backtest execution.

This module simulates realistic fill behavior when price gaps occur:
- Overnight gaps (equities)
- Weekend gaps (futures)
- CME daily break gaps (4-5 PM CT)
- Intraday gaps (halts, limit moves)

Key principles:
1. Session-aware: respects MarketSessionEngine for valid trading windows
2. Tick-rounded: all fill prices respect InstrumentSpec.tick_size
3. Worst-case fills: gaps trigger stops at open (unfavorable to trader)
4. Deterministic: same bar data → same fills every time
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from enum import Enum

from ..core.instrument_spec import InstrumentSpec
from ..core.market_session import MarketSessionEngine, SessionDecision
from .slippage import (
    compute_slippage_ticks,
    compute_gap_slippage_ticks,
    apply_slippage_to_price,
    SlippageConfig,
)


class OrderType(str, Enum):
    """Order types for fill simulation."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class FillReason(str, Enum):
    """Reason for fill or no-fill."""
    MARKET_OPEN = "market_opened"  # Market order filled at open
    STOP_TRIGGERED = "stop_triggered"  # Stop price crossed
    LIMIT_HIT = "limit_hit"  # Limit price reached
    SESSION_CLOSED = "session_closed"  # Market closed, no fill
    PRICE_NOT_REACHED = "price_not_reached"  # Limit/stop not hit
    GAP_THROUGH_STOP = "gap_through_stop"  # Gap crossed stop, filled at open
    GAP_THROUGH_LIMIT = "gap_through_limit"  # Gap crossed limit favorably


@dataclass
class BarData:
    """OHLC bar with timestamp."""
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": self.volume,
        }


@dataclass
class GapFillResult:
    """Result of gap-aware fill simulation."""
    filled: bool
    fill_price: Optional[Decimal]
    fill_timestamp: Optional[datetime]
    fill_reason: FillReason
    slippage_ticks: int = 0  # Slippage in tick units
    gap_detected: bool = False
    gap_size_ticks: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "filled": self.filled,
            "fill_price": float(self.fill_price) if self.fill_price else None,
            "fill_timestamp": self.fill_timestamp.isoformat() if self.fill_timestamp else None,
            "fill_reason": self.fill_reason.value,
            "slippage_ticks": self.slippage_ticks,
            "gap_detected": self.gap_detected,
            "gap_size_ticks": self.gap_size_ticks,
        }


def detect_gap(
    previous_close: Decimal,
    current_open: Decimal,
    tick_size: Decimal,
    min_gap_ticks: int = 2
) -> tuple[bool, int]:
    """Detect if a gap exists between bars.
    
    Args:
        previous_close: Previous bar's close price
        current_open: Current bar's open price
        tick_size: Instrument tick size
        min_gap_ticks: Minimum ticks to consider a gap (default=2)
        
    Returns:
        (gap_detected, gap_size_in_ticks)
    """
    gap_size = abs(current_open - previous_close)
    gap_ticks = int(gap_size / tick_size)
    
    return (gap_ticks >= min_gap_ticks, gap_ticks)


def simulate_gap_fill(
    order_type: OrderType,
    side: str,  # "buy" or "sell"
    quantity: float,
    limit_price: Optional[Decimal] = None,
    stop_price: Optional[Decimal] = None,
    current_bar: BarData = None,
    previous_bar: Optional[BarData] = None,
    instrument: InstrumentSpec = None,
    session_engine: Optional[MarketSessionEngine] = None,
    vol_metric: float = 0.0,
    slippage_config: Optional[SlippageConfig] = None,
) -> GapFillResult:
    """Simulate fill considering gaps and session boundaries.
    
    Args:
        order_type: OrderType enum
        side: "buy" or "sell"
        quantity: Order quantity
        limit_price: Limit price (required for LIMIT, STOP_LIMIT)
        stop_price: Stop price (required for STOP, STOP_LIMIT)
        current_bar: Current bar data
        previous_bar: Previous bar data (for gap detection)
        instrument: InstrumentSpec for tick rounding
        session_engine: MarketSessionEngine for session checks
        
    Returns:
        GapFillResult with fill decision
        
    Logic:
    1. Check if session is open at current_bar.timestamp
    2. Detect gap if previous_bar provided
    3. For MARKET: fill at open (or close if no gap)
    4. For STOP: check if stop triggered by gap or bar range
    5. For LIMIT: check if limit hit by gap or bar range
    6. Apply tick rounding to all fill prices
    """
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got: {side}")
    
    if not current_bar:
        raise ValueError("current_bar is required")
    
    if not instrument:
        raise ValueError("instrument is required for tick rounding")
    
    # 1. Check session
    if session_engine:
        session_result = session_engine.is_trading_allowed(
            current_bar.timestamp,
            allow_entry=True,
        )
        if not session_result.allowed:
            return GapFillResult(
                filled=False,
                fill_price=None,
                fill_timestamp=None,
                fill_reason=FillReason.SESSION_CLOSED,
            )
    
    # 2. Detect gap
    gap_detected = False
    gap_ticks = 0
    if previous_bar:
        gap_detected, gap_ticks = detect_gap(
            previous_bar.close,
            current_bar.open,
            instrument.tick_size,
        )
    
    # 3. Simulate fill based on order type
    if order_type == OrderType.MARKET:
        # Market orders fill at current open with slippage
        base_price = current_bar.open
        
        # Apply slippage
        slippage_ticks = compute_slippage_ticks(
            instrument=instrument,
            order_type="MARKET",
            vol_metric=vol_metric,
            config=slippage_config,
        )
        
        # Adjust price for slippage
        fill_price = apply_slippage_to_price(
            instrument=instrument,
            side=side.upper(),
            base_price=base_price,
            slippage_ticks=slippage_ticks,
        )
        
        return GapFillResult(
            filled=True,
            fill_price=fill_price,
            fill_timestamp=current_bar.timestamp,
            fill_reason=FillReason.MARKET_OPEN,
            slippage_ticks=slippage_ticks,
            gap_detected=gap_detected,
            gap_size_ticks=gap_ticks,
        )
    
    elif order_type == OrderType.STOP:
        if not stop_price:
            raise ValueError("stop_price required for STOP order")
        
        return _simulate_stop_fill(
            side, stop_price, current_bar, previous_bar,
            instrument, gap_detected, gap_ticks,
            vol_metric, slippage_config
        )
    
    elif order_type == OrderType.LIMIT:
        if not limit_price:
            raise ValueError("limit_price required for LIMIT order")
        
        return _simulate_limit_fill(
            side, limit_price, current_bar, previous_bar,
            instrument, gap_detected, gap_ticks
        )
    
    elif order_type == OrderType.STOP_LIMIT:
        if not stop_price or not limit_price:
            raise ValueError("stop_price and limit_price required for STOP_LIMIT order")
        
        # TODO: Implement stop-limit logic (Phase 3)
        raise NotImplementedError("STOP_LIMIT orders not yet implemented")
    
    else:
        raise ValueError(f"Unknown order_type: {order_type}")


def _simulate_stop_fill(
    side: str,
    stop_price: Decimal,
    current_bar: BarData,
    previous_bar: Optional[BarData],
    instrument: InstrumentSpec,
    gap_detected: bool,
    gap_ticks: int,
    vol_metric: float = 0.0,
    slippage_config: Optional[SlippageConfig] = None,
) -> GapFillResult:
    """Simulate stop order fill.
    
    Stop logic:
    - BUY STOP: triggered when price >= stop_price
    - SELL STOP: triggered when price <= stop_price
    
    If gap crosses stop:
    - Fill at open (worst case for trader)
    - Slippage = distance from stop to open in ticks
    """
    # Check if gap crossed stop price
    if gap_detected and previous_bar:
        if side == "buy":
            # Buy stop: triggered if price went above stop
            if previous_bar.close < stop_price <= current_bar.open:
                # Gap up through stop
                fill_price = instrument.round_to_tick(current_bar.open)
                slippage_ticks = int((current_bar.open - stop_price) / instrument.tick_size)
                return GapFillResult(
                    filled=True,
                    fill_price=fill_price,
                    fill_timestamp=current_bar.timestamp,
                    fill_reason=FillReason.GAP_THROUGH_STOP,
                    slippage_ticks=slippage_ticks,
                    gap_detected=True,
                    gap_size_ticks=gap_ticks,
                )
        else:  # sell
            # Sell stop: triggered if price went below stop
            if previous_bar.close > stop_price >= current_bar.open:
                # Gap down through stop
                fill_price = instrument.round_to_tick(current_bar.open)
                slippage_ticks = int((stop_price - current_bar.open) / instrument.tick_size)
                return GapFillResult(
                    filled=True,
                    fill_price=fill_price,
                    fill_timestamp=current_bar.timestamp,
                    fill_reason=FillReason.GAP_THROUGH_STOP,
                    slippage_ticks=slippage_ticks,
                    gap_detected=True,
                    gap_size_ticks=gap_ticks,
                )
    
    # Check if stop triggered during bar (no gap or gap didn't cross)
    if side == "buy":
        # Buy stop: triggered if high >= stop_price
        if current_bar.high >= stop_price:
            # Assume fill at stop price (best case)
            fill_price = instrument.round_to_tick(stop_price)
            return GapFillResult(
                filled=True,
                fill_price=fill_price,
                fill_timestamp=current_bar.timestamp,
                fill_reason=FillReason.STOP_TRIGGERED,
                slippage_ticks=0,
                gap_detected=gap_detected,
                gap_size_ticks=gap_ticks,
            )
    else:  # sell
        # Sell stop: triggered if low <= stop_price
        if current_bar.low <= stop_price:
            fill_price = instrument.round_to_tick(stop_price)
            return GapFillResult(
                filled=True,
                fill_price=fill_price,
                fill_timestamp=current_bar.timestamp,
                fill_reason=FillReason.STOP_TRIGGERED,
                slippage_ticks=0,
                gap_detected=gap_detected,
                gap_size_ticks=gap_ticks,
            )
    
    # Stop not triggered
    return GapFillResult(
        filled=False,
        fill_price=None,
        fill_timestamp=None,
        fill_reason=FillReason.PRICE_NOT_REACHED,
        gap_detected=gap_detected,
        gap_size_ticks=gap_ticks,
    )


def _simulate_limit_fill(
    side: str,
    limit_price: Decimal,
    current_bar: BarData,
    previous_bar: Optional[BarData],
    instrument: InstrumentSpec,
    gap_detected: bool,
    gap_ticks: int,
) -> GapFillResult:
    """Simulate limit order fill.
    
    Limit logic:
    - BUY LIMIT: fill when price <= limit_price (buy at or below limit)
    - SELL LIMIT: fill when price >= limit_price (sell at or above limit)
    
    If gap crosses limit favorably:
    - Fill at limit price (favorable to trader)
    """
    # Check if gap crossed limit favorably
    if gap_detected and previous_bar:
        if side == "buy":
            # Buy limit: want to buy at or below limit
            if previous_bar.close > limit_price >= current_bar.open:
                # Gap down through limit - fill at limit (best case)
                fill_price = instrument.round_to_tick(limit_price)
                return GapFillResult(
                    filled=True,
                    fill_price=fill_price,
                    fill_timestamp=current_bar.timestamp,
                    fill_reason=FillReason.GAP_THROUGH_LIMIT,
                    slippage_ticks=0,
                    gap_detected=True,
                    gap_size_ticks=gap_ticks,
                )
        else:  # sell
            # Sell limit: want to sell at or above limit
            if previous_bar.close < limit_price <= current_bar.open:
                # Gap up through limit - fill at limit (best case)
                fill_price = instrument.round_to_tick(limit_price)
                return GapFillResult(
                    filled=True,
                    fill_price=fill_price,
                    fill_timestamp=current_bar.timestamp,
                    fill_reason=FillReason.GAP_THROUGH_LIMIT,
                    slippage_ticks=0,
                    gap_detected=True,
                    gap_size_ticks=gap_ticks,
                )
    
    # Check if limit hit during bar
    if side == "buy":
        # Buy limit: fill if low <= limit_price
        if current_bar.low <= limit_price:
            fill_price = instrument.round_to_tick(limit_price)
            return GapFillResult(
                filled=True,
                fill_price=fill_price,
                fill_timestamp=current_bar.timestamp,
                fill_reason=FillReason.LIMIT_HIT,
                slippage_ticks=0,
                gap_detected=gap_detected,
                gap_size_ticks=gap_ticks,
            )
    else:  # sell
        # Sell limit: fill if high >= limit_price
        if current_bar.high >= limit_price:
            fill_price = instrument.round_to_tick(limit_price)
            return GapFillResult(
                filled=True,
                fill_price=fill_price,
                fill_timestamp=current_bar.timestamp,
                fill_reason=FillReason.LIMIT_HIT,
                slippage_ticks=0,
                gap_detected=gap_detected,
                gap_size_ticks=gap_ticks,
            )
    
    # Limit not hit
    return GapFillResult(
        filled=False,
        fill_price=None,
        fill_timestamp=None,
        fill_reason=FillReason.PRICE_NOT_REACHED,
        gap_detected=gap_detected,
        gap_size_ticks=gap_ticks,
    )
