"""Topstep-style trailing drawdown and daily loss tracking.

This module implements accurate trailing drawdown logic that:
- Tracks intraday and end-of-day equity
- Maintains high-water mark per trading day
- Trails unrealized equity (not starting balance)
- Locks in once equity exceeds initial balance
- Enforces max daily loss based on realized + unrealized PnL

Determinism:
- Same positions + same prices → same drawdown calculation
- No external state or randomness
"""

from typing import Dict, Optional, List, Any, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum

if TYPE_CHECKING:
    from .day_boundary import TradingDayBoundary


class DrawdownState(str, Enum):
    """Drawdown state indicators."""
    ACTIVE = "active"  # Drawdown is active (below high-water mark)
    LOCKED = "locked"  # Drawdown locked in (equity exceeded initial balance)
    RESET = "reset"  # Drawdown reset (new trading day)


@dataclass(frozen=True)
class DrawdownSnapshot:
    """Snapshot of drawdown state at a point in time.
    
    Attributes:
        timestamp: When this snapshot was taken
        equity: Total equity (cash + unrealized PnL)
        initial_balance: Initial balance at start of day/session
        high_water_mark: Highest equity reached since initial balance
        trailing_drawdown: Current trailing drawdown amount (positive number)
        trailing_drawdown_pct: Trailing drawdown as percentage of high-water mark
        realized_pnl: Cumulative realized PnL
        unrealized_pnl: Current unrealized PnL
        state: Drawdown state (active, locked, reset)
    """
    
    timestamp: datetime
    equity: float
    initial_balance: float
    high_water_mark: float
    trailing_drawdown: float
    trailing_drawdown_pct: float
    realized_pnl: float
    unrealized_pnl: float
    state: DrawdownState
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "equity": self.equity,
            "initial_balance": self.initial_balance,
            "high_water_mark": self.high_water_mark,
            "trailing_drawdown": self.trailing_drawdown,
            "trailing_drawdown_pct": self.trailing_drawdown_pct,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "state": self.state.value,
        }


@dataclass
class DrawdownTracker:
    """Tracks trailing drawdown and daily loss for Topstep-style rules.
    
    This tracker maintains:
    - High-water mark (highest equity since initial balance)
    - Trailing drawdown (current equity vs high-water mark)
    - Daily loss tracking (realized + unrealized PnL)
    
    Topstep trailing drawdown logic:
    1. Start with initial balance (day/session start)
    2. As equity increases, high-water mark increases
    3. Once equity > initial_balance, drawdown "locks in" and trails high-water mark
    4. Trailing drawdown = high_water_mark - current_equity (if locked) or 0 (if not locked)
    
    Attributes:
        initial_balance: Starting balance for this trading period
        trading_date: Trading date (for daily reset logic)
        high_water_mark: Highest equity reached since initial balance
        is_locked: Whether drawdown has locked in (equity exceeded initial balance)
        snapshots: List of drawdown snapshots (for audit trail)
    """
    
    initial_balance: float
    trading_date: date
    high_water_mark: float = field(default_factory=lambda: 0.0)
    is_locked: bool = False
    snapshots: List[DrawdownSnapshot] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize tracker."""
        if self.initial_balance <= 0:
            raise ValueError(f"initial_balance must be positive, got: {self.initial_balance}")
        
        # Initialize high-water mark to initial balance
        if self.high_water_mark == 0.0:
            object.__setattr__(self, 'high_water_mark', self.initial_balance)
    
    def update(
        self,
        equity: float,
        realized_pnl: float,
        unrealized_pnl: float,
        timestamp: Optional[datetime] = None,
        day_boundary: Optional['TradingDayBoundary'] = None
    ) -> DrawdownSnapshot:
        """Update drawdown tracker with current equity.
        
        Process:
        1. Calculate current equity (should match equity parameter)
        2. Update high-water mark if equity exceeds it
        3. Check if drawdown should lock in (equity > initial_balance)
        4. Calculate trailing drawdown
        5. Create snapshot and append to history
        
        Args:
            equity: Current total equity (cash + unrealized PnL)
            realized_pnl: Cumulative realized PnL
            unrealized_pnl: Current unrealized PnL
            timestamp: Timestamp for snapshot (defaults to now)
            
        Returns:
            DrawdownSnapshot with current drawdown state
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Check for day rollover and handle if needed
        if day_boundary is not None:
            previous_timestamp = self.snapshots[-1].timestamp if self.snapshots else None
            if day_boundary.has_day_rollover(previous_timestamp, timestamp):
                # Reset daily loss for new day (preserve trailing drawdown)
                from .day_boundary import reset_daily_loss_for_new_day
                new_trading_date = day_boundary.get_trading_date(timestamp)
                # Reset initial_balance to current equity for new day's daily loss calculation
                reset_tracker = reset_daily_loss_for_new_day(
                    self,
                    new_trading_date,
                    new_initial_balance=equity  # Use current equity as new day's starting balance
                )
                # Copy reset state to this instance (preserve high_water_mark and is_locked)
                object.__setattr__(self, 'initial_balance', reset_tracker.initial_balance)
                object.__setattr__(self, 'trading_date', reset_tracker.trading_date)
                # Note: high_water_mark and is_locked are already preserved (they're copied from self to reset_tracker)
        
        # Update high-water mark
        if equity > self.high_water_mark:
            object.__setattr__(self, 'high_water_mark', equity)
        
        # Check if drawdown should lock in
        # Lock in once equity exceeds initial balance
        if equity > self.initial_balance and not self.is_locked:
            object.__setattr__(self, 'is_locked', True)
        
        # Calculate trailing drawdown
        # If locked: trailing drawdown = high_water_mark - equity
        # If not locked: trailing drawdown = 0 (no drawdown until locked)
        if self.is_locked:
            trailing_drawdown = max(0.0, self.high_water_mark - equity)
        else:
            trailing_drawdown = 0.0
        
        # Calculate trailing drawdown percentage
        if self.high_water_mark > 0:
            trailing_drawdown_pct = (trailing_drawdown / self.high_water_mark) * 100.0
        else:
            trailing_drawdown_pct = 0.0
        
        # Determine state
        if self.is_locked:
            state = DrawdownState.LOCKED
        else:
            state = DrawdownState.ACTIVE
        
        snapshot = DrawdownSnapshot(
            timestamp=timestamp,
            equity=equity,
            initial_balance=self.initial_balance,
            high_water_mark=self.high_water_mark,
            trailing_drawdown=trailing_drawdown,
            trailing_drawdown_pct=trailing_drawdown_pct,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            state=state
        )
        
        # Append to history
        self.snapshots.append(snapshot)
        
        return snapshot
    
    def get_current_snapshot(self) -> Optional[DrawdownSnapshot]:
        """Get most recent snapshot.
        
        Returns:
            Latest DrawdownSnapshot, or None if no updates yet
        """
        if not self.snapshots:
            return None
        return self.snapshots[-1]
    
    def get_daily_loss(self, equity: float) -> float:
        """Calculate daily loss from initial balance.
        
        Args:
            equity: Current equity
            
        Returns:
            Daily loss (negative if losing, positive if gaining)
        """
        return equity - self.initial_balance
    
    def reset_for_new_day(self, new_initial_balance: float, new_trading_date: date):
        """Reset tracker for a new trading day.
        
        Args:
            new_initial_balance: Starting balance for new day
            new_trading_date: New trading date
        """
        object.__setattr__(self, 'initial_balance', new_initial_balance)
        object.__setattr__(self, 'trading_date', new_trading_date)
        object.__setattr__(self, 'high_water_mark', new_initial_balance)
        object.__setattr__(self, 'is_locked', False)
        # Keep snapshots for audit trail
    
    def to_dict(self) -> Dict:
        """Serialize tracker to dictionary."""
        return {
            "initial_balance": self.initial_balance,
            "trading_date": self.trading_date.isoformat(),
            "high_water_mark": self.high_water_mark,
            "is_locked": self.is_locked,
            "snapshots": [s.to_dict() for s in self.snapshots],
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'DrawdownTracker':
        """Deserialize tracker from dictionary."""
        from datetime import date as date_class
        
        tracker = cls(
            initial_balance=data["initial_balance"],
            trading_date=date_class.fromisoformat(data["trading_date"]),
            high_water_mark=data.get("high_water_mark", data["initial_balance"]),
            is_locked=data.get("is_locked", False),
        )
        
        # Restore snapshots
        snapshots = []
        for snap_data in data.get("snapshots", []):
            snapshots.append(DrawdownSnapshot(
                timestamp=datetime.fromisoformat(snap_data["timestamp"]),
                equity=snap_data["equity"],
                initial_balance=snap_data["initial_balance"],
                high_water_mark=snap_data["high_water_mark"],
                trailing_drawdown=snap_data["trailing_drawdown"],
                trailing_drawdown_pct=snap_data["trailing_drawdown_pct"],
                realized_pnl=snap_data["realized_pnl"],
                unrealized_pnl=snap_data["unrealized_pnl"],
                state=DrawdownState(snap_data["state"]),
            ))
        object.__setattr__(tracker, 'snapshots', snapshots)
        
        return tracker


def calculate_portfolio_equity(
    initial_cash: float,
    positions: Dict[str, Any],  # Position objects
    current_prices: Dict[str, float],
    realized_pnl: float
) -> tuple[float, float]:
    """Calculate current portfolio equity and unrealized PnL.
    
    Equity = initial_cash + realized_pnl + unrealized_pnl
    Unrealized PnL = sum((current_price - cost_basis) * quantity) for all positions
    
    Args:
        initial_cash: Initial cash balance
        positions: Dictionary of instrument -> Position
        current_prices: Dictionary of instrument -> current price
        realized_pnl: Cumulative realized PnL from closed positions
        
    Returns:
        Tuple of (equity, unrealized_pnl)
    """
    unrealized_pnl = 0.0
    
    for instrument, position in positions.items():
        if position.quantity == 0:
            continue
        
        current_price = current_prices.get(instrument)
        if current_price is None:
            # If price not available, use cost basis (no unrealized PnL)
            continue
        
        # Calculate unrealized PnL for this position
        if position.is_long():
            # Long: (current_price - cost_basis) * quantity
            position_unrealized = (current_price - position.cost_basis) * position.quantity
        else:
            # Short: (cost_basis - current_price) * abs(quantity)
            position_unrealized = (position.cost_basis - current_price) * abs(position.quantity)
        
        unrealized_pnl += position_unrealized
    
    equity = initial_cash + realized_pnl + unrealized_pnl
    
    return equity, unrealized_pnl

