#!/usr/bin/env python3
"""Instrument Specification for Multi-Asset Trading.

Defines instrument metadata for proper handling of futures, equities, and other
asset classes. Each InstrumentSpec contains:
- Symbol identification and exchange
- Precision (tick_size, point_value, contract_multiplier)
- Margin requirements
- Session hours and trading rules
- Position sizing constraints

This abstraction enables deterministic backtesting and production trading
across asset classes without hardcoded assumptions.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from enum import Enum


class AssetClass(str, Enum):
    """Asset class classification."""
    FUTURES = "futures"
    EQUITY = "equity"
    OPTION = "option"


class Exchange(str, Enum):
    """Supported exchanges."""
    CME = "CME"           # Chicago Mercantile Exchange
    CBOT = "CBOT"         # Chicago Board of Trade
    NYMEX = "NYMEX"       # New York Mercantile Exchange
    COMEX = "COMEX"       # Commodity Exchange
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
    ARCA = "ARCA"


@dataclass(frozen=True)
class InstrumentSpec:
    """Immutable instrument specification.
    
    Attributes:
        symbol: Instrument symbol (e.g., "ES", "AAPL")
        exchange: Primary exchange
        asset_class: Asset type
        tick_size: Minimum price increment (e.g., 0.25 for ES)
        point_value: Dollar value per point (e.g., 50 for ES)
        contract_multiplier: Shares/units per contract (100 for equity, 1 for futures)
        min_order_size: Minimum order quantity
        margin_requirement: Initial margin per contract (dollars)
        session_name: Reference to TradingSession (e.g., "cme_futures", "us_equities")
        description: Human-readable description
    """
    
    symbol: str
    exchange: Exchange
    asset_class: AssetClass
    tick_size: Decimal
    point_value: Decimal
    contract_multiplier: int = 1
    min_order_size: int = 1
    margin_requirement: Optional[Decimal] = None
    session_name: str = "us_equities"
    description: str = ""
    
    def __post_init__(self):
        """Validate instrument specification."""
        if self.tick_size <= 0:
            raise ValueError(f"tick_size must be > 0, got {self.tick_size}")
        if self.point_value <= 0:
            raise ValueError(f"point_value must be > 0, got {self.point_value}")
        if self.contract_multiplier <= 0:
            raise ValueError(f"contract_multiplier must be > 0, got {self.contract_multiplier}")
        if self.min_order_size <= 0:
            raise ValueError(f"min_order_size must be > 0, got {self.min_order_size}")
        if self.margin_requirement is not None and self.margin_requirement < 0:
            raise ValueError(f"margin_requirement must be >= 0, got {self.margin_requirement}")
    
    def round_to_tick(self, price: Decimal) -> Decimal:
        """Round price to nearest valid tick.
        
        Args:
            price: Raw price
            
        Returns:
            Price rounded to tick_size increment
        """
        return (price / self.tick_size).quantize(Decimal('1')) * self.tick_size
    
    def calculate_notional_value(self, price: Decimal, quantity: int) -> Decimal:
        """Calculate notional value of a position.
        
        Args:
            price: Current price
            quantity: Number of contracts/shares
            
        Returns:
            Notional value in dollars
        """
        return price * Decimal(quantity) * Decimal(self.contract_multiplier)
    
    def calculate_pnl_per_tick(self, quantity: int) -> Decimal:
        """Calculate P&L for a 1-tick move.
        
        Args:
            quantity: Number of contracts/shares
            
        Returns:
            Dollar P&L for 1 tick move
        """
        return self.tick_size * self.point_value * Decimal(quantity)


# ============================================================
# CME FUTURES PRESETS
# ============================================================

ES_FUTURE = InstrumentSpec(
    symbol="ES",
    exchange=Exchange.CME,
    asset_class=AssetClass.FUTURES,
    tick_size=Decimal("0.25"),
    point_value=Decimal("50"),
    contract_multiplier=1,
    min_order_size=1,
    margin_requirement=Decimal("12000"),  # Approximate, varies by broker
    session_name="cme_futures",
    description="E-mini S&P 500 Futures"
)

NQ_FUTURE = InstrumentSpec(
    symbol="NQ",
    exchange=Exchange.CME,
    asset_class=AssetClass.FUTURES,
    tick_size=Decimal("0.25"),
    point_value=Decimal("20"),
    contract_multiplier=1,
    min_order_size=1,
    margin_requirement=Decimal("15000"),
    session_name="cme_futures",
    description="E-mini Nasdaq-100 Futures"
)

CL_FUTURE = InstrumentSpec(
    symbol="CL",
    exchange=Exchange.NYMEX,
    asset_class=AssetClass.FUTURES,
    tick_size=Decimal("0.01"),
    point_value=Decimal("1000"),  # $10 per tick (0.01 per barrel * 1000 barrels)
    contract_multiplier=1,
    min_order_size=1,
    margin_requirement=Decimal("6000"),
    session_name="cme_futures",
    description="Crude Oil Futures (1000 barrels)"
)

GC_FUTURE = InstrumentSpec(
    symbol="GC",
    exchange=Exchange.COMEX,
    asset_class=AssetClass.FUTURES,
    tick_size=Decimal("0.10"),
    point_value=Decimal("100"),  # $10 per tick (0.10 per oz * 100 oz)
    contract_multiplier=1,
    min_order_size=1,
    margin_requirement=Decimal("8000"),
    session_name="cme_futures",
    description="Gold Futures (100 troy oz)"
)

ZN_FUTURE = InstrumentSpec(
    symbol="ZN",
    exchange=Exchange.CBOT,
    asset_class=AssetClass.FUTURES,
    tick_size=Decimal("0.015625"),  # 1/64 of a point
    point_value=Decimal("1000"),
    contract_multiplier=1,
    min_order_size=1,
    margin_requirement=Decimal("2000"),
    session_name="cme_futures",
    description="10-Year Treasury Note Futures"
)


# ============================================================
# US EQUITY PRESETS
# ============================================================

def create_equity_spec(
    symbol: str,
    exchange: Exchange = Exchange.NASDAQ,
    description: str = ""
) -> InstrumentSpec:
    """Factory for US equity specs.
    
    Args:
        symbol: Stock ticker (e.g., "AAPL")
        exchange: Primary exchange
        description: Optional description
        
    Returns:
        InstrumentSpec for equity
    """
    return InstrumentSpec(
        symbol=symbol,
        exchange=exchange,
        asset_class=AssetClass.EQUITY,
        tick_size=Decimal("0.01"),  # Penny increment
        point_value=Decimal("1"),    # 1:1 dollar value
        contract_multiplier=1,       # 1 share per unit
        min_order_size=1,
        margin_requirement=None,     # Varies by broker and account type
        session_name="us_equities",
        description=description or f"{symbol} Stock"
    )


# Common equity presets
AAPL_EQUITY = create_equity_spec("AAPL", Exchange.NASDAQ, "Apple Inc.")
SPY_EQUITY = create_equity_spec("SPY", Exchange.ARCA, "SPDR S&P 500 ETF")
QQQ_EQUITY = create_equity_spec("QQQ", Exchange.NASDAQ, "Invesco QQQ Trust")


# ============================================================
# REGISTRY
# ============================================================

_INSTRUMENT_REGISTRY = {}



def get_instrument(symbol: str) -> InstrumentSpec:
    """Get instrument spec by symbol.
    
    Args:
        symbol: Instrument symbol
        
    Returns:
        InstrumentSpec instance
        
    Raises:
        KeyError: If symbol not found in registry
    """
    if symbol not in _INSTRUMENT_REGISTRY:
        raise KeyError(
            f"Instrument {symbol} not found. "
            f"Available: {list(_INSTRUMENT_REGISTRY.keys())}"
        )
    return _INSTRUMENT_REGISTRY[symbol]


def register_instrument(spec: InstrumentSpec):
    """Add custom instrument to registry.
    
    Args:
        spec: InstrumentSpec to register
    """
    _INSTRUMENT_REGISTRY[spec.symbol] = spec
