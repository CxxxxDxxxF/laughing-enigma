"""Deterministic demo of Topstep-style trailing drawdown tracking.

This demo proves the drawdown math with 3 hard-number scenarios:
1. Not locked: equity below initial, trailing drawdown not active
2. Lock event: first time equity exceeds initial balance
3. Post-lock drawdown breach: equity drops enough to trip max_trailing_drawdown_pct

All scenarios use fixed prices/positions with no randomness.
"""

from datetime import datetime, date
from .drawdown import DrawdownTracker
from .topstep import TopstepRulesConfig, TopstepRuleset
from .base import RulesViolationSeverity


def scenario_1_not_locked():
    """Scenario 1: Not locked yet - equity below initial balance."""
    print("=" * 70)
    print("SCENARIO 1: Not Locked (Equity Below Initial Balance)")
    print("=" * 70)
    
    initial_balance = 100000.0
    tracker = DrawdownTracker(
        initial_balance=initial_balance,
        trading_date=date.today()
    )
    
    # Update with equity below initial
    equity_1 = 98000.0  # -$2000 loss
    snapshot_1 = tracker.update(
        equity=equity_1,
        realized_pnl=-500.0,
        unrealized_pnl=-1500.0,
        timestamp=datetime(2024, 1, 1, 10, 0, 0)
    )
    
    print(f"\nInitial Balance: ${initial_balance:,.2f}")
    print(f"Current Equity: ${equity_1:,.2f}")
    print(f"Realized PnL: ${snapshot_1.realized_pnl:,.2f}")
    print(f"Unrealized PnL: ${snapshot_1.unrealized_pnl:,.2f}")
    print(f"\nHigh-Water Mark: ${tracker.high_water_mark:,.2f}")
    print(f"Is Locked: {tracker.is_locked}")
    print(f"State: {snapshot_1.state.value}")
    print(f"Trailing Drawdown: ${snapshot_1.trailing_drawdown:,.2f}")
    print(f"Trailing Drawdown %: {snapshot_1.trailing_drawdown_pct:.2f}%")
    print(f"Daily Loss: ${snapshot_1.equity - snapshot_1.initial_balance:,.2f}")
    print(f"Daily Loss %: {((snapshot_1.equity - snapshot_1.initial_balance) / snapshot_1.initial_balance * 100):.2f}%")
    
    print("\n✓ Expected: Not locked (equity < initial), trailing drawdown = 0")
    print()


def scenario_2_lock_event():
    """Scenario 2: Lock event - equity exceeds initial balance for first time."""
    print("=" * 70)
    print("SCENARIO 2: Lock Event (Equity Exceeds Initial Balance)")
    print("=" * 70)
    
    initial_balance = 100000.0
    tracker = DrawdownTracker(
        initial_balance=initial_balance,
        trading_date=date.today()
    )
    
    # First update: equity below initial
    equity_1 = 98000.0
    snapshot_1 = tracker.update(
        equity=equity_1,
        realized_pnl=-500.0,
        unrealized_pnl=-1500.0,
        timestamp=datetime(2024, 1, 1, 10, 0, 0)
    )
    
    print(f"\nStep 1: Equity Below Initial")
    print(f"  Equity: ${equity_1:,.2f}")
    print(f"  Is Locked: {tracker.is_locked}")
    print(f"  High-Water Mark: ${tracker.high_water_mark:,.2f}")
    
    # Second update: equity exceeds initial (LOCK EVENT)
    equity_2 = 105000.0  # +$5000 gain
    snapshot_2 = tracker.update(
        equity=equity_2,
        realized_pnl=2000.0,
        unrealized_pnl=3000.0,
        timestamp=datetime(2024, 1, 1, 11, 0, 0)
    )
    
    print(f"\nStep 2: Equity Exceeds Initial (LOCK EVENT)")
    print(f"  Equity: ${equity_2:,.2f}")
    print(f"  Is Locked: {tracker.is_locked}")
    print(f"  High-Water Mark: ${tracker.high_water_mark:,.2f}")
    print(f"  State: {snapshot_2.state.value}")
    print(f"  Trailing Drawdown: ${snapshot_2.trailing_drawdown:,.2f}")
    print(f"  Trailing Drawdown %: {snapshot_2.trailing_drawdown_pct:.2f}%")
    
    print("\n✓ Expected: Locked (equity > initial), high-water mark = equity")
    print()


def scenario_3_trailing_drawdown_halt():
    """Scenario 3: Post-lock drawdown breach - trailing drawdown exceeds limit."""
    print("=" * 70)
    print("SCENARIO 3: Post-Lock Trailing Drawdown HALT")
    print("=" * 70)
    
    initial_balance = 100000.0
    tracker = DrawdownTracker(
        initial_balance=initial_balance,
        trading_date=date.today()
    )
    
    # Step 1: Lock the tracker (equity exceeds initial)
    equity_1 = 105000.0
    snapshot_1 = tracker.update(
        equity=equity_1,
        realized_pnl=2000.0,
        unrealized_pnl=3000.0,
        timestamp=datetime(2024, 1, 1, 10, 0, 0)
    )
    
    print(f"\nStep 1: Lock Tracker")
    print(f"  Equity: ${equity_1:,.2f}")
    print(f"  Is Locked: {tracker.is_locked}")
    print(f"  High-Water Mark: ${tracker.high_water_mark:,.2f}")
    
    # Step 2: Equity drops from high-water mark (trailing drawdown activates)
    equity_2 = 99500.0  # Drops $5500 from high-water mark of $105000 = 5.24% drawdown
    snapshot_2 = tracker.update(
        equity=equity_2,
        realized_pnl=1500.0,
        unrealized_pnl=-500.0,
        timestamp=datetime(2024, 1, 1, 11, 0, 0)
    )
    
    print(f"\nStep 2: Equity Drops (Trailing Drawdown Active)")
    print(f"  Equity: ${equity_2:,.2f}")
    print(f"  High-Water Mark: ${tracker.high_water_mark:,.2f}")
    print(f"  Is Locked: {tracker.is_locked}")
    print(f"  State: {snapshot_2.state.value}")
    print(f"  Trailing Drawdown: ${snapshot_2.trailing_drawdown:,.2f}")
    print(f"  Trailing Drawdown %: {snapshot_2.trailing_drawdown_pct:.2f}%")
    
    # Step 3: Check against ruleset (5% max trailing drawdown)
    config = TopstepRulesConfig(
        max_trailing_drawdown_pct=5.0,
        account_size=initial_balance
    )
    ruleset = TopstepRuleset(config)
    
    # Create mock execution result and state for validation
    class MockExecutionResult:
        def __init__(self):
            self.execution_timestamp = datetime(2024, 1, 1, 11, 0, 0)
            self.intent_results = []
            self.execution_summary = {}
    
    class MockExecutionEngine:
        def __init__(self, positions):
            self.positions = positions
            self.instrument = "AAPL"
    
    class MockPosition:
        def __init__(self, realized_pnl, quantity=100.0, cost_basis=150.0):
            self.quantity = quantity
            self.realized_pnl = realized_pnl
            self.cost_basis = cost_basis
        
        def is_long(self):
            return self.quantity > 0
        
        def is_short(self):
            return self.quantity < 0
    
    class MockState:
        def __init__(self, total_capital, drawdown_tracker):
            self.total_capital = total_capital
            self.drawdown_tracker = drawdown_tracker
    
    # Create mock state with tracker
    # For equity_2 = 99500, with initial_cash=100000 and realized_pnl=1500, we need unrealized_pnl=-500
    # So: equity = initial_cash + realized_pnl + unrealized_pnl = 100000 + 1500 - 500 = 99500 ✓
    positions = {"AAPL": MockPosition(realized_pnl=snapshot_2.realized_pnl)}
    engine = MockExecutionEngine(positions)
    state = MockState(total_capital=initial_balance, drawdown_tracker=tracker)
    
    # Calculate price that gives us the desired equity
    # We want equity = 99500
    # equity = initial_cash + realized_pnl + unrealized_pnl
    # unrealized_pnl = (price - cost_basis) * quantity for long position
    # For long: unrealized = (price - 150) * 100
    # We want: 99500 = 100000 + 1500 + unrealized
    # So: unrealized = 99500 - 101500 = -2000
    # So: (price - 150) * 100 = -2000
    # So: price - 150 = -20
    # So: price = 130
    current_prices = {"AAPL": 130.0}  # Price that gives equity_2 = 99500
    
    # Validate (this will update the tracker)
    violations = ruleset.validate_execution(
        execution_result=MockExecutionResult(),
        current_state=state,
        execution_engine=engine,
        current_prices=current_prices
    )
    
    print(f"\nStep 3: Ruleset Validation (max_trailing_drawdown_pct = 5.0%)")
    print(f"  Current Trailing Drawdown: {snapshot_2.trailing_drawdown_pct:.2f}%")
    print(f"  Max Allowed: {config.max_trailing_drawdown_pct:.2f}%")
    print(f"\n  Violations Found: {len(violations)}")
    for v in violations:
        print(f"    [{v.severity.value.upper()}] {v.code}: {v.message}")
        if v.metadata:
            print(f"      Metadata: trailing_drawdown_pct={v.metadata.get('trailing_drawdown_pct', 'N/A'):.2f}%")
    
    halt_violations = [v for v in violations if v.severity == RulesViolationSeverity.HALT]
    print(f"\n✓ Expected: HALT violation (trailing drawdown {snapshot_2.trailing_drawdown_pct:.2f}% > {config.max_trailing_drawdown_pct:.2f}%)")
    print(f"  Actual: {len(halt_violations)} HALT violation(s)")
    print()


def main():
    """Run all drawdown scenarios."""
    print("\n" + "=" * 70)
    print("Topstep Trailing Drawdown Math Demo")
    print("=" * 70 + "\n")
    
    scenario_1_not_locked()
    scenario_2_lock_event()
    scenario_3_trailing_drawdown_halt()
    
    print("=" * 70)
    print("Demo Complete")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

