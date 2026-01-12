#!/usr/bin/env python3
"""Position sizing and risk enforcement for entry orders.

Provides margin-based sizing for futures and exposure-based sizing for equities:
- Futures: margin requirement checks with buffer
- Equities: gross exposure limits + per-position caps + no leverage
- Session-aware: respects MarketSessionEngine forced-flat windows
- Deterministic: same inputs → same decisions
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Any

from ..core.instrument_spec import InstrumentSpec, AssetClass
from ..core.market_session import MarketSessionEngine


class PositionDecision(str, Enum):
    """Decision on whether position can be opened."""
    ALLOWED = "allowed"
    INSUFFICIENT_MARGIN = "insufficient_margin"
    EXCEEDS_GROSS_EXPOSURE = "exceeds_gross_exposure"
    EXCEEDS_POSITION_CAP = "exceeds_position_cap"
    INSUFFICIENT_CASH = "insufficient_cash"
    SESSION_BLOCKED = "session_blocked"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class AccountState:
    """Account state for position sizing."""
    equity: Decimal  # Total account equity
    cash: Decimal  # Available cash
    margin_used: Decimal = Decimal("0")  # Margin currently in use (futures)
    
    def __post_init__(self):
        """Validate account state."""
        if self.equity < 0:
            raise ValueError(f"equity must be >= 0, got {self.equity}")
        if self.cash < 0:
            raise ValueError(f"cash must be >= 0, got {self.cash}")
        if self.margin_used < 0:
            raise ValueError(f"margin_used must be >= 0, got {self.margin_used}")


@dataclass(frozen=True)
class PositionState:
    """Current position state for a symbol."""
    symbol: str
    quantity: int
    cost_basis: Decimal
    notional_value: Decimal  # Current market value


@dataclass(frozen=True)
class PortfolioState:
    """Portfolio holdings state."""
    gross_exposure: Decimal  # Sum of abs(notional) for all positions
    positions: Dict[str, PositionState]  # By symbol
    
    def __post_init__(self):
        """Validate portfolio state."""
        if self.gross_exposure < 0:
            raise ValueError(f"gross_exposure must be >= 0, got {self.gross_exposure}")


@dataclass(frozen=True)
class RiskPolicy:
    """Risk limits policy."""
    # Equities
    max_gross_exposure: float = 0.95  # As fraction of equity (default: 95%)
    max_position_fraction: float = 0.20  # Max single position as fraction of equity
    allow_short: bool = False  # Allow short positions for equities
    
    # Futures
    margin_buffer_fraction: float = 0.10  # Extra margin buffer (default: 10%)
    max_contracts_per_symbol: int = 10  # Max contracts for single symbol
    
    def __post_init__(self):
        """Validate policy."""
        if self.max_gross_exposure <= 0 or self.max_gross_exposure > 1.0:
            raise ValueError(f"max_gross_exposure must be in (0, 1], got {self.max_gross_exposure}")
        if self.max_position_fraction <= 0 or self.max_position_fraction > 1.0:
            raise ValueError(f"max_position_fraction must be in (0, 1], got {self.max_position_fraction}")
        if self.margin_buffer_fraction < 0:
            raise ValueError(f"margin_buffer_fraction must be >= 0, got {self.margin_buffer_fraction}")
        if self.max_contracts_per_symbol <= 0:
            raise ValueError(f"max_contracts_per_symbol must be > 0, got {self.max_contracts_per_symbol}")


# Default conservative policy
DEFAULT_RISK_POLICY = RiskPolicy(
    max_gross_exposure=0.95,
    max_position_fraction=0.20,
    allow_short=False,
    margin_buffer_fraction=0.10,
    max_contracts_per_symbol=5,
)


@dataclass(frozen=True)
class SizingResult:
    """Result of position sizing check."""
    allowed: bool
    decision: PositionDecision
    reason: str
    max_quantity: int = 0  # Maximum quantity allowed
    debug: Dict[str, Any] = None
    
    def __post_init__(self):
        """Initialize debug dict if None."""
        if self.debug is None:
            object.__setattr__(self, 'debug', {})


def can_open_position(
    *,
    instrument: InstrumentSpec,
    quantity: int,
    price: Decimal,
    account: AccountState,
    portfolio: PortfolioState,
    policy: RiskPolicy = DEFAULT_RISK_POLICY,
    session_engine: Optional[MarketSessionEngine] = None,
    timestamp: Optional[datetime] = None,
) -> SizingResult:
    """Check if position can be opened given risk constraints.
    
    Args:
        instrument: InstrumentSpec for asset being traded
        quantity: Desired position quantity (signed: +buy, -sell)
        price: Entry price
        account: Current account state
        portfolio: Current portfolio state
        policy: Risk policy (uses default if None)
        session_engine: Optional session engine for session checks
        timestamp: Optional timestamp for session checks
        
    Returns:
        SizingResult with decision and debug info
        
    Checks (in order):
    1. Input validation (no NaN/inf/negative price)
    2. Session check (if engines provided)
    3. Futures margin check (if futures)
    4. Equity exposure checks (if equity)
    """
    debug = {}
    
    # 1. Input validation
    if quantity == 0:
        return SizingResult(
            allowed=False,
            decision=PositionDecision.INVALID_INPUT,
            reason="quantity is zero",
            debug=debug,
        )
    
    if price <= 0:
        return SizingResult(
            allowed=False,
            decision=PositionDecision.INVALID_INPUT,
            reason=f"price must be > 0, got {price}",
            debug=debug,
        )
    
    # Check for NaN/inf
    try:
        float(price)
        if not (price == price):  # NaN check
            raise ValueError("price is NaN")
    except (ValueError, TypeError) as e:
        return SizingResult(
            allowed=False,
            decision=PositionDecision.INVALID_INPUT,
            reason=f"invalid price: {e}",
            debug=debug,
        )
    
    # 2. Session check
    if session_engine and timestamp:
        session_result = session_engine.is_trading_allowed(timestamp, allow_entry=True)
        if not session_result.allowed:
            return SizingResult(
                allowed=False,
                decision=PositionDecision.SESSION_BLOCKED,
                reason=f"Session blocked: {session_result.reason}",
                debug=debug,
            )
    
    # Build debug info
    debug["quantity"] = quantity
    debug["price"] = float(price)
    debug["equity"] = float(account.equity)
    debug["cash"] = float(account.cash)
    
    # 3. Asset-specific checks
    if instrument.asset_class == AssetClass.FUTURES:
        return _check_futures_sizing(
            instrument, quantity, price, account, portfolio, policy, debug
        )
    elif instrument.asset_class == AssetClass.EQUITY:
        return _check_equity_sizing(
            instrument, quantity, price, account, portfolio, policy, debug
        )
    else:
        return SizingResult(
            allowed=False,
            decision=PositionDecision.INVALID_INPUT,
            reason=f"Unknown asset class: {instrument.asset_class}",
            debug=debug,
        )


def _check_futures_sizing(
    instrument: InstrumentSpec,
    quantity: int,
    price: Decimal,
    account: AccountState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    debug: Dict[str, Any],
) -> SizingResult:
    """Check futures-specific sizing constraints."""
    abs_qty = abs(quantity)
    
    # Calculate required margin with buffer
    required_margin = Decimal(abs_qty) * instrument.margin_requirement
    margin_buffer = required_margin * Decimal(str(policy.margin_buffer_fraction))
    total_required = required_margin + margin_buffer
    
    debug["required_margin"] = float(required_margin)
    debug["margin_buffer"] = float(margin_buffer)
    debug["total_required_margin"] = float(total_required)
    debug["margin_used"] = float(account.margin_used)
    
    # Check available margin
    available_margin = account.cash - account.margin_used
    debug["available_margin"] = float(available_margin)
    
    if total_required > available_margin:
        # Calculate max contracts that would fit
        max_contracts = int(available_margin / (instrument.margin_requirement * (1 + Decimal(str(policy.margin_buffer_fraction)))))
        return SizingResult(
            allowed=False,
            decision=PositionDecision.INSUFFICIENT_MARGIN,
            reason=f"Required margin ${total_required:.2f} exceeds available ${available_margin:.2f}",
            max_quantity=max(0, max_contracts),
            debug=debug,
        )
    
    # Check max contracts per symbol
    if abs_qty > policy.max_contracts_per_symbol:
        return SizingResult(
            allowed=False,
            decision=PositionDecision.EXCEEDS_POSITION_CAP,
            reason=f"Quantity {abs_qty} exceeds max {policy.max_contracts_per_symbol} contracts",
            max_quantity=policy.max_contracts_per_symbol,
            debug=debug,
        )
    
    # All checks passed
    return SizingResult(
        allowed=True,
        decision=PositionDecision.ALLOWED,
        reason="Position allowed",
        max_quantity=abs_qty,
        debug=debug,
    )


def _check_equity_sizing(
    instrument: InstrumentSpec,
    quantity: int,
    price: Decimal,
    account: AccountState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    debug: Dict[str, Any],
) -> SizingResult:
    """Check equity-specific sizing constraints."""
    # Only allow longs for equities by default
    if quantity < 0 and not policy.allow_short:
        return SizingResult(
            allowed=False,
            decision=PositionDecision.INVALID_INPUT,
            reason="Short selling not allowed for equities",
            debug=debug,
        )
    
    # Calculate notional value
    notional = abs(Decimal(quantity) * price)
    debug["notional"] = float(notional)
    
    # 1. Check cash sufficiency (no leverage)
    if notional > account.cash:
        max_shares = int(account.cash / price)
        return SizingResult(
            allowed=False,
            decision=PositionDecision.INSUFFICIENT_CASH,
            reason=f"Notional ${notional:.2f} exceeds cash ${account.cash:.2f}",
            max_quantity=max(0, max_shares),
            debug=debug,
        )
    
    # 2. Check per-position limit
    max_position_value = account.equity * Decimal(str(policy.max_position_fraction))
    debug["max_position_value"] = float(max_position_value)
    
    if notional > max_position_value:
        max_shares = int(max_position_value / price)
        return SizingResult(
            allowed=False,
            decision=PositionDecision.EXCEEDS_POSITION_CAP,
            reason=f"Notional ${notional:.2f} exceeds max position ${max_position_value:.2f} ({policy.max_position_fraction:.1%} of equity)",
            max_quantity=max(0, max_shares),
            debug=debug,
        )
    
    # 3. Check gross exposure limit
    projected_gross = portfolio.gross_exposure + notional
    max_gross = account.equity * Decimal(str(policy.max_gross_exposure))
    
    debug["current_gross_exposure"] = float(portfolio.gross_exposure)
    debug["projected_gross_exposure"] = float(projected_gross)
    debug["max_gross_exposure"] = float(max_gross)
    
    if projected_gross > max_gross:
        # Calculate max shares that would fit within gross limit
        available_exposure = max_gross - portfolio.gross_exposure
        max_shares = int(available_exposure / price) if available_exposure > 0 else 0
        
        return SizingResult(
            allowed=False,
            decision=PositionDecision.EXCEEDS_GROSS_EXPOSURE,
            reason=f"Projected gross ${projected_gross:.2f} exceeds max ${max_gross:.2f} ({policy.max_gross_exposure:.1%} of equity)",
            max_quantity=max(0, max_shares),
            debug=debug,
        )
    
    # All checks passed
    return SizingResult(
        allowed=True,
        decision=PositionDecision.ALLOWED,
        reason="Position allowed",
        max_quantity=abs(quantity),
        debug=debug,
    )
