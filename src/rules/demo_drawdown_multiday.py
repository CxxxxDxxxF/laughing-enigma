"""Two-day drawdown regression demo.

This demo simulates:
Day 1:
- Equity rises → lock drawdown
- Small loss within limits
Day 2:
- Daily loss resets
- Equity drops from high-water mark
- Trailing drawdown HALT triggers

Expected behavior:
- daily_loss = 0 on Day 2 start
- high_water_mark unchanged
- is_locked = true
- HALT only from trailing drawdown, not daily loss
"""

from datetime import datetime, date, timedelta
from .drawdown import DrawdownTracker
from .day_boundary import TradingDayBoundary
from .topstep import TopstepRulesConfig, TopstepRuleset
from .base import RulesViolationSeverity


def main():
    """Run two-day drawdown demo."""
    print("=" * 70)
    print("Two-Day Drawdown Tracker Demo")
    print("=" * 70)
    
    # Day boundary config (use UTC for simplicity)
    from datetime import timezone as tz
    day_boundary = TradingDayBoundary(timezone=tz.utc)
    
    # Initial setup
    initial_balance = 100000.0
    trading_date_day1 = date.today()
    
    tracker = DrawdownTracker(
        initial_balance=initial_balance,
        trading_date=trading_date_day1
    )
    
    print(f"\nInitial Balance: ${initial_balance:,.2f}")
    print(f"Day 1 Date: {trading_date_day1}")
    
    # ===== DAY 1 =====
    print("\n" + "=" * 70)
    print("DAY 1")
    print("=" * 70)
    
    # Step 1: Equity rises above initial (LOCK EVENT)
    day1_time1 = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    equity_day1_step1 = 105000.0  # +$5000 gain
    
    snapshot1 = tracker.update(
        equity=equity_day1_step1,
        realized_pnl=2000.0,
        unrealized_pnl=3000.0,
        timestamp=day1_time1,
        day_boundary=day_boundary
    )
    
    print(f"\nStep 1: Equity Rises Above Initial (LOCK EVENT)")
    print(f"  Timestamp: {day1_time1}")
    print(f"  Equity: ${equity_day1_step1:,.2f}")
    print(f"  High-Water Mark: ${tracker.high_water_mark:,.2f}")
    print(f"  Is Locked: {tracker.is_locked}")
    print(f"  Daily Loss: ${snapshot1.equity - snapshot1.initial_balance:,.2f}")
    print(f"  Trailing Drawdown: ${snapshot1.trailing_drawdown:,.2f} ({snapshot1.trailing_drawdown_pct:.2f}%)")
    
    # Step 2: Small loss within limits
    day1_time2 = day1_time1 + timedelta(hours=2)
    equity_day1_step2 = 103000.0  # Drops $2000 from high-water mark
    
    snapshot2 = tracker.update(
        equity=equity_day1_step2,
        realized_pnl=1500.0,
        unrealized_pnl=-500.0,
        timestamp=day1_time2,
        day_boundary=day_boundary
    )
    
    print(f"\nStep 2: Small Loss (Within Limits)")
    print(f"  Timestamp: {day1_time2}")
    print(f"  Equity: ${equity_day1_step2:,.2f}")
    print(f"  High-Water Mark: ${tracker.high_water_mark:,.2f}")
    print(f"  Is Locked: {tracker.is_locked}")
    print(f"  Daily Loss: ${snapshot2.equity - snapshot2.initial_balance:,.2f}")
    print(f"  Trailing Drawdown: ${snapshot2.trailing_drawdown:,.2f} ({snapshot2.trailing_drawdown_pct:.2f}%)")
    
    # End of Day 1 state
    print(f"\n✓ Day 1 Complete:")
    print(f"  High-Water Mark: ${tracker.high_water_mark:,.2f}")
    print(f"  Is Locked: {tracker.is_locked}")
    print(f"  Final Equity: ${equity_day1_step2:,.2f}")
    
    # ===== DAY 2 =====
    print("\n" + "=" * 70)
    print("DAY 2 (Day Rollover)")
    print("=" * 70)
    
    # Day 2 starts - daily loss should reset
    trading_date_day2 = trading_date_day1 + timedelta(days=1)
    day2_time1 = (day1_time2 + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    
    # Equity drops further (triggers trailing drawdown HALT)
    equity_day2_step1 = 99500.0  # Drops $5500 from high-water mark (5.24% drawdown)
    
    print(f"\nDay 2 Date: {trading_date_day2}")
    print(f"Day 2 Start Timestamp: {day2_time1}")
    
    print(f"\nBefore Day 2 Update:")
    print(f"  Initial Balance: ${tracker.initial_balance:,.2f}")
    print(f"  High-Water Mark: ${tracker.high_water_mark:,.2f}")
    print(f"  Is Locked: {tracker.is_locked}")
    print(f"  Trading Date: {tracker.trading_date}")
    
    # Update on Day 2 (should trigger day rollover reset)
    snapshot3 = tracker.update(
        equity=equity_day2_step1,
        realized_pnl=1000.0,
        unrealized_pnl=-500.0,
        timestamp=day2_time1,
        day_boundary=day_boundary
    )
    
    print(f"\nAfter Day 2 Update (Day Rollover Detected):")
    print(f"  Initial Balance (reset for daily loss): ${tracker.initial_balance:,.2f}")
    print(f"  High-Water Mark (preserved): ${tracker.high_water_mark:,.2f}")
    print(f"  Is Locked (preserved): {tracker.is_locked}")
    print(f"  Trading Date: {tracker.trading_date}")
    print(f"  Current Equity: ${equity_day2_step1:,.2f}")
    print(f"  Daily Loss (from new day's initial): ${snapshot3.equity - snapshot3.initial_balance:,.2f}")
    print(f"  Trailing Drawdown (from high-water mark): ${snapshot3.trailing_drawdown:,.2f} ({snapshot3.trailing_drawdown_pct:.2f}%)")
    
    # Verify expectations
    print(f"\n✓ Day 2 Verification:")
    print(f"  Daily Loss Reset: {snapshot3.equity - snapshot3.initial_balance:.2f} (should be negative, from new day's start)")
    print(f"  High-Water Mark Preserved: {tracker.high_water_mark == 105000.0}")
    print(f"  Lock State Preserved: {tracker.is_locked}")
    print(f"  Trailing Drawdown Active: {snapshot3.trailing_drawdown > 0}")
    
    # Check against ruleset (5% max trailing drawdown)
    config = TopstepRulesConfig(
        max_trailing_drawdown_pct=5.0,
        max_daily_loss=-5000.0,
        account_size=initial_balance
    )
    ruleset = TopstepRuleset(config)
    
    # Create mock execution result and state for validation
    class MockExecutionResult:
        def __init__(self, ts):
            self.execution_timestamp = ts
            self.intent_results = []
            self.execution_summary = {}
    
    class MockExecutionEngine:
        def __init__(self):
            self.positions = {}
            self.instrument = "AAPL"
    
    class MockPosition:
        def __init__(self, realized_pnl):
            self.quantity = 100.0
            self.realized_pnl = realized_pnl
            self.cost_basis = 150.0
        def is_long(self):
            return True
        def is_short(self):
            return False
    
    class MockState:
        def __init__(self, total_capital, drawdown_tracker):
            self.total_capital = total_capital
            self.drawdown_tracker = drawdown_tracker
    
    positions = {"AAPL": MockPosition(realized_pnl=snapshot3.realized_pnl)}
    engine = MockExecutionEngine()
    state = MockState(total_capital=initial_balance, drawdown_tracker=tracker)
    current_prices = {"AAPL": 130.0}  # Price that gives equity_day2_step1
    
    violations = ruleset.validate_execution(
        execution_result=MockExecutionResult(day2_time1),
        current_state=state,
        execution_engine=engine,
        current_prices=current_prices
    )
    
    print(f"\n" + "=" * 70)
    print("Ruleset Validation (Day 2)")
    print("=" * 70)
    print(f"  Max Trailing Drawdown: {config.max_trailing_drawdown_pct:.2f}%")
    print(f"  Current Trailing Drawdown: {snapshot3.trailing_drawdown_pct:.2f}%")
    print(f"  Max Daily Loss: ${config.max_daily_loss:,.2f}")
    print(f"  Current Daily Loss: ${snapshot3.equity - snapshot3.initial_balance:,.2f}")
    print(f"\n  Violations Found: {len(violations)}")
    for v in violations:
        print(f"    [{v.severity.value.upper()}] {v.code}: {v.message}")
    
    halt_violations = [v for v in violations if v.severity == RulesViolationSeverity.HALT]
    trailing_dd_violations = [v for v in violations if 'TRAILING_DRAWDOWN' in v.code]
    
    print(f"\n✓ Expected Behavior:")
    print(f"  HALT from trailing drawdown (not daily loss): {len(trailing_dd_violations) > 0}")
    print(f"  Total HALT violations: {len(halt_violations)}")
    print(f"  Daily loss within limit: {snapshot3.equity - snapshot3.initial_balance >= config.max_daily_loss}")
    
    print("\n" + "=" * 70)
    print("Demo Complete")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

