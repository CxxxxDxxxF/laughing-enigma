#!/usr/bin/env python3
"""Minimal deterministic backtest runner for testing."""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from zoneinfo import ZoneInfo

from src.execution.gap_fills import BarData, simulate_gap_fill, OrderType, GapFillResult
from src.execution import PaperExecutionEngine, Signal, SignalType, Order, Fill
from src.core.instrument_spec import InstrumentSpec, register_instrument
from src.core.market_session import MarketSessionEngine


@dataclass
class TradeRecord:
    """Record of a completed trade."""
    timestamp: str
    side: str
    quantity: int
    fill_price: float
    fill_reason: str
    slippage_ticks: int
    gap_detected: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BacktestResult:
    """Result of a deterministic backtest."""
    trades: List[TradeRecord]
    final_pnl: Decimal
    final_position_qty: int
    total_fills: int
    total_rejections: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trades": [t.to_dict() for t in self.trades],
            "final_pnl": float(self.final_pnl),
            "final_position_qty": self.final_position_qty,
            "total_fills": self.total_fills,
            "total_rejections": self.total_rejections,
        }


def load_bars_from_json(filepath: Path) -> List[BarData]:
    """Load bar data from JSON fixture file.
    
    Args:
        filepath: Path to JSON file
        
    Returns:
        List of BarData objects
    """
    with open(filepath, 'r') as f:
        bars_json = json.load(f)
    
    bars = []
    for bar_dict in bars_json:
        # Parse timestamp
        timestamp_str = bar_dict["timestamp"]
        timestamp = datetime.fromisoformat(timestamp_str)
        
        bar = BarData(
            timestamp=timestamp,
            open=Decimal(str(bar_dict["open"])),
            high=Decimal(str(bar_dict["high"])),
            low=Decimal(str(bar_dict["low"])),
            close=Decimal(str(bar_dict["close"])),
            volume=bar_dict.get("volume"),
        )
        bars.append(bar)
    
    return bars


class MicroBacktest:
    """Minimal deterministic backtest runner.
    
    Steps through bars, executes scripted orders at specific timestamps,
    and records exact fills for assertion.
    """
    
    def __init__(
        self,
        instrument: InstrumentSpec,
        bars: List[BarData],
        initial_cash: Decimal = Decimal("100000"),
        session_engine: Optional[MarketSessionEngine] = None,
    ):
        """Initialize micro backtest.
        
        Args:
            instrument: Instrument specification
            bars: List of bars to step through
            initial_cash: Initial account cash
            session_engine: Optional session engine for session checks
        """
        self.instrument = instrument
        self.bars = bars
        self.session_engine = session_engine
        
        # Register instrument
        register_instrument(instrument)
        
        # Initialize engine
        self.engine = PaperExecutionEngine(
            instrument=instrument.symbol,
            account_cash=initial_cash,
            account_equity=initial_cash,
        )
        
        # Track trades
        self.trades: List[TradeRecord] = []
        self.rejections: List[Order] = []
        
        # Account state (simplified - PaperEngine doesn't track cash/equity)
        self.cash = initial_cash
        self.equity = initial_cash
    
    def execute_order_at_bar(
        self,
        bar_index: int,
        side: str,
        quantity: int,
        order_type: str = "MARKET",
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        vol_metric: float = 0.0,
    ) -> Optional[Fill]:
        """Execute order at a specific bar.
        
        Args:
            bar_index: Index of bar to execute at
            side: "BUY" or "SELL"
            quantity: Order quantity
            order_type: "MARKET", "STOP", or "LIMIT"
            limit_price: Limit price (for LIMIT orders)
            stop_price: Stop price (for STOP orders)
            vol_metric: Volatility metric for slippage
            
        Returns:
            Fill if order executed, None if rejected or not filled
        """
        if bar_index >= len(self.bars):
            raise ValueError(f"Bar index {bar_index} out of range")
        
        current_bar = self.bars[bar_index]
        previous_bar = self.bars[bar_index - 1] if bar_index > 0 else None
        
        # Submit signal to engine
        signal_type = SignalType.BUY if side.upper() == "BUY" else SignalType.SELL
        signal = Signal(
            timestamp=current_bar.timestamp,
            instrument=self.instrument.symbol,
            signal_type=signal_type,
            quantity=quantity,
        )
        
        # Submit order
        order = self.engine.submit_order(signal)
        
        # Check if rejected
        if order.status.value == "rejected":
            self.rejections.append(order)
            return None
        
        # Simulate fill using gap_fills
        order_type_enum = {
            "MARKET": OrderType.MARKET,
            "STOP": OrderType.STOP,
            "LIMIT": OrderType.LIMIT,
        }[order_type.upper()]
        
        fill_result = simulate_gap_fill(
            order_type=order_type_enum,
            side=side.lower(),
            quantity=quantity,
            limit_price=limit_price,
            stop_price=stop_price,
            current_bar=current_bar,
            previous_bar=previous_bar,
            instrument=self.instrument,
            session_engine=self.session_engine,
            vol_metric=vol_metric,
        )
        
        # If filled, execute in engine
        if fill_result.filled:
            fills = self.engine.execute_order(
                order=order,
                current_price=float(fill_result.fill_price),
                timestamp=current_bar.timestamp,
            )
            
            fill = fills[0]  # Assume full fill
            
            # Record trade
            trade = TradeRecord(
                timestamp=current_bar.timestamp.isoformat(),
                side=side,
                quantity=quantity,
                fill_price=float(fill_result.fill_price),
                fill_reason=fill_result.fill_reason.value,
                slippage_ticks=fill_result.slippage_ticks,
                gap_detected=fill_result.gap_detected,
            )
            self.trades.append(trade)
            
            return fill
        
        return None
    
    def get_result(self) -> BacktestResult:
        """Get backtest result.
        
        Returns:
            BacktestResult with trades and PnL
        """
        # Get final position
        position = self.engine.get_position(self.instrument.symbol)
        
        return BacktestResult(
            trades=self.trades,
            final_pnl=Decimal(str(position.realized_pnl)),
            final_position_qty=int(position.quantity),
            total_fills=len(self.trades),
            total_rejections=len(self.rejections),
        )
