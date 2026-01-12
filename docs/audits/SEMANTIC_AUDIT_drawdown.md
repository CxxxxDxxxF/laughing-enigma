# Semantic Audit: src/rules/drawdown.py

## 1) File Purpose

This module implements Topstep-style trailing drawdown and daily loss tracking that maintains high-water marks per trading day, trails unrealized equity, locks in once equity exceeds initial balance, and enforces max daily loss based on realized + unrealized PnL.

## 2) Data Model

### 2.1 `DrawdownState` [L24-L29]
- **Type**: Enum (str-based)
- **Purpose**: Drawdown state indicators
- **Values**: 
  - `ACTIVE = "active"` - Drawdown is active (below high-water mark)
  - `LOCKED = "locked"` - Drawdown locked in (equity exceeded initial balance)
  - `RESET = "reset"` - Drawdown reset (new trading day)

### 2.2 `DrawdownSnapshot` [L31-L69]
- **Type**: dataclass (frozen=True, immutable)
- **Purpose**: Snapshot of drawdown state at a point in time

**Fields:**

- `timestamp: datetime` [L47]
  - **When set**: Constructor (from `update()` method [L187])
  - **When read**: Serialization `to_dict()` [L60], deserialization from dict
  - **Mutates**: No (frozen dataclass)
  - **Persisted**: Yes, via `to_dict()` [L60] (ISO format)

- `equity: float` [L48]
  - **When set**: Constructor (from `update()` parameter [L188])
  - **When read**: Used for calculations in `update()` [L158, L163, L170], serialization [L61]
  - **Mutates**: No (frozen dataclass)
  - **Persisted**: Yes, via `to_dict()` [L61]

- `initial_balance: float` [L49]
  - **When set**: Constructor (from tracker's `initial_balance` [L189])
  - **When read**: Used for daily loss calculation in `get_daily_loss()` [L222], serialization [L62]
  - **Mutates**: No (frozen dataclass)
  - **Persisted**: Yes, via `to_dict()` [L62]

- `high_water_mark: float` [L50]
  - **When set**: Constructor (from tracker's `high_water_mark` [L190])
  - **When read**: Used for trailing drawdown calculation [L170, L176], serialization [L63]
  - **Mutates**: No (frozen dataclass)
  - **Persisted**: Yes, via `to_dict()` [L63]

- `trailing_drawdown: float` [L51]
  - **When set**: Constructor (calculated in `update()` [L170, L172, L191])
  - **When read**: Serialization [L64], used in validation/rulesets
  - **Mutates**: No (frozen dataclass)
  - **Persisted**: Yes, via `to_dict()` [L64]

- `trailing_drawdown_pct: float` [L52]
  - **When set**: Constructor (calculated in `update()` [L176, L178, L192])
  - **When read**: Serialization [L65], used in validation/rulesets
  - **Mutates**: No (frozen dataclass)
  - **Persisted**: Yes, via `to_dict()` [L65]

- `realized_pnl: float` [L53]
  - **When set**: Constructor (from `update()` parameter [L193])
  - **When read**: Serialization [L66]
  - **Mutates**: No (frozen dataclass)
  - **Persisted**: Yes, via `to_dict()` [L66]

- `unrealized_pnl: float` [L54]
  - **When set**: Constructor (from `update()` parameter [L194])
  - **When read**: Serialization [L67]
  - **Mutates**: No (frozen dataclass)
  - **Persisted**: Yes, via `to_dict()` [L67]

- `state: DrawdownState` [L55]
  - **When set**: Constructor (determined in `update()` [L181-L184, L195])
  - **When read**: Serialization [L68] (as `.value` string), deserialization
  - **Mutates**: No (frozen dataclass)
  - **Persisted**: Yes, via `to_dict()` [L68] (as string value)

### 2.3 `DrawdownTracker` [L72-L275]
- **Type**: dataclass (mutable)
- **Purpose**: Tracks trailing drawdown and daily loss for Topstep-style rules

**Fields:**

- `initial_balance: float` [L95]
  - **When set**: Constructor [L95, L252], `__post_init__()` validation [L103-L104], `update()` via day boundary reset [L153], `reset_for_new_day()` [L231]
  - **When read**: 
    - `__post_init__()` validation [L103]
    - `update()` for lock check [L163], snapshot creation [L189], day boundary reset [L146]
    - `get_daily_loss()` [L222]
    - `reset_for_new_day()` [L229]
    - `to_dict()` [L240]
  - **Mutates**: Yes (via `object.__setattr__()` in `update()` [L153], `reset_for_new_day()` [L231])
  - **Persisted**: Yes, via `to_dict()` [L240], restored in `from_dict()` [L253]

- `trading_date: date` [L96]
  - **When set**: Constructor [L96, L254], `update()` via day boundary reset [L154], `reset_for_new_day()` [L232]
  - **When read**: 
    - `update()` for day boundary check [L145]
    - `to_dict()` [L241] (ISO format)
  - **Mutates**: Yes (via `object.__setattr__()` in `update()` [L154], `reset_for_new_day()` [L232])
  - **Persisted**: Yes, via `to_dict()` [L241], restored in `from_dict()` [L254] (from ISO format)

- `high_water_mark: float` [L97]
  - **When set**: 
    - `__post_init__()` if 0.0 [L107-L108] (initialized to `initial_balance`)
    - Constructor default [L97] (default_factory=lambda: 0.0)
    - `update()` if equity > high_water_mark [L158-L159]
    - `reset_for_new_day()` [L233] (reset to new_initial_balance)
    - `from_dict()` [L255]
  - **When read**: 
    - `update()` for comparison [L158], trailing drawdown calculation [L170], percentage calculation [L175, L176], snapshot creation [L190]
    - `reset_for_new_day()` [L233]
    - `to_dict()` [L242]
  - **Mutates**: Yes (via `object.__setattr__()` in `update()` [L159], `reset_for_new_day()` [L233])
  - **Persisted**: Yes, via `to_dict()` [L242], restored in `from_dict()` [L255]

- `is_locked: bool` [L98]
  - **When set**: 
    - Constructor default [L98] (False)
    - `update()` if equity > initial_balance [L163-L164]
    - `reset_for_new_day()` [L234] (reset to False)
    - `from_dict()` [L256]
  - **When read**: 
    - `update()` for lock check [L163], trailing drawdown calculation [L169], state determination [L181], snapshot creation [L195]
    - `to_dict()` [L243]
  - **Mutates**: Yes (via `object.__setattr__()` in `update()` [L164], `reset_for_new_day()` [L234])
  - **Persisted**: Yes, via `to_dict()` [L243], restored in `from_dict()` [L256]

- `snapshots: List[DrawdownSnapshot]` [L99]
  - **When set**: 
    - Constructor default [L99] (default_factory=list, empty list)
    - `update()` appends snapshot [L199]
    - `from_dict()` restores list [L273]
  - **When read**: 
    - `update()` for day boundary check [L141] (last snapshot timestamp)
    - `get_current_snapshot()` [L209, L211]
    - `to_dict()` [L244] (converts each snapshot to dict)
    - `reset_for_new_day()` preserves (comment [L235])
  - **Mutates**: Yes (appended to in `update()` [L199], never cleared)
  - **Persisted**: Yes, via `to_dict()` [L244] (list of snapshot dicts), restored in `from_dict()` [L261-L272]

**Note**: Dataclass uses `object.__setattr__()` for mutations because fields are not explicitly marked as mutable in dataclass definition, but mutations occur for frozen=False dataclass.

### 2.4 Function: `calculate_portfolio_equity()` [L278-L321]
- **Type**: Module-level function
- **Purpose**: Calculate current portfolio equity and unrealized PnL from positions and prices

## 3) DrawdownTracker Lifecycle

### 3.1 Initial Construction [L101-L109]

**Constructor parameters**:
- `initial_balance: float` (required) [L95]
- `trading_date: date` (required) [L96]
- `high_water_mark: float` (optional, default 0.0) [L97]
- `is_locked: bool` (optional, default False) [L98]
- `snapshots: List[DrawdownSnapshot]` (optional, default empty list) [L99]

**`__post_init__()` validation [L101-L109]**:
1. Validates `initial_balance > 0` [L103-L104] (raises ValueError if violated)
2. Initializes `high_water_mark` to `initial_balance` if it's 0.0 [L107-L108]

**Result**: Tracker starts with:
- `high_water_mark = initial_balance`
- `is_locked = False`
- `snapshots = []` (empty)

### 3.2 Update Semantics [L110-L201]

**Method**: `update(equity, realized_pnl, unrealized_pnl, timestamp=None, day_boundary=None)`

**Process flow**:

1. **Timestamp handling [L136-L137]**: If `timestamp` is None, uses `datetime.now()` (non-deterministic)

2. **Day boundary check [L139-L155]**:
   - If `day_boundary` provided and day rollover detected [L141-L142]:
     - Calls `reset_daily_loss_for_new_day()` [L147-L151] (UNKNOWN: depends on day_boundary.py implementation)
     - Updates `initial_balance` and `trading_date` [L153-L154]
     - Preserves `high_water_mark` and `is_locked` (copied from self to reset_tracker, then preserved)

3. **High-water mark update [L157-L159]**:
   - If `equity > high_water_mark`: updates `high_water_mark = equity`

4. **Lock-in check [L161-L164]**:
   - If `equity > initial_balance` AND `not is_locked`: sets `is_locked = True`
   - **Note**: Lock is permanent (never reverts to False except via `reset_for_new_day()`)

5. **Trailing drawdown calculation [L166-L172]**:
   - If `is_locked`: `trailing_drawdown = max(0.0, high_water_mark - equity)`
   - If not locked: `trailing_drawdown = 0.0`

6. **Trailing drawdown percentage [L174-L178]**:
   - If `high_water_mark > 0`: `trailing_drawdown_pct = (trailing_drawdown / high_water_mark) * 100.0`
   - Otherwise: `trailing_drawdown_pct = 0.0`

7. **State determination [L180-L184]**:
   - If `is_locked`: `state = DrawdownState.LOCKED`
   - Otherwise: `state = DrawdownState.ACTIVE`
   - **Note**: `DrawdownState.RESET` is never set in this method

8. **Snapshot creation [L186-L196]**:
   - Creates `DrawdownSnapshot` with all calculated values

9. **Snapshot append [L198-L199]**:
   - Appends snapshot to `self.snapshots` list
   - **Note**: Snapshots are never removed (history grows indefinitely)

10. **Return [L201]**: Returns the created snapshot

**Side effects**:
- Mutates `high_water_mark` (if equity exceeds it)
- Mutates `is_locked` (once, when equity > initial_balance)
- Mutates `initial_balance` and `trading_date` (if day rollover detected)
- Mutates `snapshots` list (appends new snapshot)

### 3.3 Snapshot Semantics [L203-L211]

**Method**: `get_current_snapshot() -> Optional[DrawdownSnapshot]`

**Behavior**:
- Returns `self.snapshots[-1]` if snapshots exist [L211]
- Returns `None` if no snapshots [L210]

**Purpose**: Provides access to latest snapshot without requiring `update()` call

**Note**: Snapshots are immutable (frozen dataclass), but list continues to grow

### 3.4 Reset Semantics [L224-L235]

**Method**: `reset_for_new_day(new_initial_balance, new_trading_date)`

**Process**:
1. Sets `initial_balance = new_initial_balance` [L231]
2. Sets `trading_date = new_trading_date` [L232]
3. Sets `high_water_mark = new_initial_balance` [L233] (**RESETS high-water mark**)
4. Sets `is_locked = False` [L234] (**UNLOCKS drawdown**)
5. Preserves `snapshots` list (comment [L235], no mutation)

**Purpose**: Reset tracker for new trading day/session

**Note**: This is a **FULL RESET** (resets high-water mark and lock state), not a partial reset. This differs from day boundary reset in `update()` which preserves high-water mark and lock state.

**Contradiction with documentation**: Documentation says "preserve trailing drawdown" but this method resets `high_water_mark`. The day boundary reset in `update()` preserves it, but this method does not.

### 3.5 Day Boundary Behavior [L139-L155]

**Trigger**: Day rollover detected via `day_boundary.has_day_rollover()` [L142]

**Process**:
1. Gets previous timestamp from last snapshot [L141]
2. Checks rollover via `day_boundary.has_day_rollover()` [L142] (UNKNOWN: depends on day_boundary.py)
3. Gets new trading date [L145]
4. Calls `reset_daily_loss_for_new_day()` [L147-L151] (UNKNOWN: implementation in day_boundary.py)
   - Preserves `high_water_mark` (trailing drawdown persists)
   - Preserves `is_locked` (lock state persists)
   - Preserves `snapshots` (history persists)
   - Updates `initial_balance` to current equity (daily loss resets)
   - Updates `trading_date` to new date

**Result**: Daily loss calculation resets (new `initial_balance`), but trailing drawdown persists (high-water mark and lock state preserved)

**Difference from `reset_for_new_day()`**: Day boundary reset in `update()` preserves trailing drawdown, while `reset_for_new_day()` resets everything.

## 4) Determinism Analysis

### 4.1 Identical Equity Sequences

**Question**: For identical equity sequences, does tracker evolve identically?

**Answer**: **PARTIALLY** - Depends on timestamp handling and day boundary logic.

**Deterministic components**:
- High-water mark updates [L158-L159]: Same equity sequence → same high_water_mark evolution
- Lock-in logic [L163-L164]: Same equity sequence → same lock timing
- Trailing drawdown calculation [L169-L172]: Pure computation, deterministic
- Trailing drawdown percentage [L175-L178]: Pure computation, deterministic

**Non-deterministic components**:
- **Timestamp handling [L136-L137]**: If `timestamp=None`, uses `datetime.now()` → different timestamps on each call → different snapshot timestamps
- **Day boundary detection [L139-L155]**: Depends on timestamps (UNKNOWN: if timestamps differ, day boundary detection may differ)
- **Day rollover behavior**: If day rollover detected differently, `initial_balance` reset timing differs

**Conclusion**: Given **identical equity sequences AND identical timestamps**, tracker evolves identically. If timestamps differ (e.g., `timestamp=None`), behavior may differ due to day boundary detection.

### 4.2 Floating-Point Instability Risks

**Risk 1: Equity comparison [L158]**
- **Location**: `if equity > self.high_water_mark`
- **Risk**: Floating-point precision errors may cause `equity == high_water_mark` to be misclassified as `equity > high_water_mark` or vice versa
- **Impact**: High-water mark may not update when it should, or may update when it shouldn't
- **Mitigation**: Uses `>` (strict greater), not `>=`, so exact equality is safe

**Risk 2: Trailing drawdown calculation [L170]**
- **Location**: `trailing_drawdown = max(0.0, self.high_water_mark - equity)`
- **Risk**: If `high_water_mark - equity` is slightly negative due to floating-point error, `max(0.0, ...)` corrects it
- **Impact**: Minimal (protected by max)

**Risk 3: Percentage calculation [L176]**
- **Location**: `trailing_drawdown_pct = (trailing_drawdown / self.high_water_mark) * 100.0`
- **Risk**: Division by zero protected [L175] (`if self.high_water_mark > 0`), but floating-point division may introduce precision errors
- **Impact**: Percentage may have small precision errors (unlikely to affect business logic)

**Risk 4: Initial balance comparison [L163]**
- **Location**: `if equity > self.initial_balance and not self.is_locked`
- **Risk**: Floating-point precision may cause lock-in timing to differ
- **Impact**: Lock-in may occur one update earlier/later than expected

**Risk 5: Daily loss calculation [L222]**
- **Location**: `return equity - self.initial_balance`
- **Risk**: Standard subtraction, floating-point precision errors possible but minimal

**Overall assessment**: Low to moderate risk. Most comparisons are protected (max, zero checks), but strict equality comparisons could be affected by floating-point precision.

### 4.3 Time Dependence

**Explicit time dependence**:
1. **`timestamp` parameter [L115, L136-L137]**: If None, uses `datetime.now()` (non-deterministic)
2. **Day boundary detection [L142]**: Depends on timestamps to detect day rollover
3. **Trading date [L145]**: Derived from timestamp via `day_boundary.get_trading_date()`

**Implicit time dependence**:
- None (no system clock reads beyond timestamp parameter)

**Determinism guarantee**: If `timestamp` is always provided explicitly (not None), and `day_boundary` is deterministic, then tracker is deterministic for same inputs.

## 5) Invariants

### 5.1 Explicit Invariants Enforced

**Invariant 1: Positive Initial Balance [L103-L104]**
- **Statement**: `initial_balance > 0`
- **Enforcement**: `__post_init__()` raises `ValueError` if violated
- **Violation handling**: Constructor fails with ValueError

**Invariant 2: High-Water Mark Initialization [L107-L108]**
- **Statement**: If `high_water_mark == 0.0` at construction, set it to `initial_balance`
- **Enforcement**: `__post_init__()` sets it
- **Violation handling**: N/A (enforced automatically)

**Invariant 3: Trailing Drawdown Non-Negative [L170]**
- **Statement**: `trailing_drawdown >= 0.0`
- **Enforcement**: Uses `max(0.0, ...)` to ensure non-negative
- **Violation handling**: Clamped to 0.0

**Invariant 4: Percentage Calculation Safety [L175]**
- **Statement**: Avoid division by zero in `trailing_drawdown_pct` calculation
- **Enforcement**: Checks `if self.high_water_mark > 0` before division
- **Violation handling**: Sets `trailing_drawdown_pct = 0.0` if high_water_mark is 0

### 5.2 Implicit Invariants Assumed

**Assumed Invariant 1: High-Water Mark Monotonicity**
- **Statement**: `high_water_mark` only increases (never decreases except via reset methods)
- **Enforcement**: None (only updated when `equity > high_water_mark` [L158])
- **What breaks if violated**: Trailing drawdown calculation incorrect, lock state may be inconsistent

**Assumed Invariant 2: Lock State Monotonicity (Once Locked, Never Unlocked)**
- **Statement**: `is_locked` transitions False → True once, never True → False except via `reset_for_new_day()`
- **Enforcement**: None (only set to True in `update()` [L164], reset to False in `reset_for_new_day()` [L234])
- **What breaks if violated**: Trailing drawdown logic breaks (assumes lock is permanent within a session)
- **Note**: `topstep.py` enforces this invariant [L251-L263] by checking that lock state never reverts

**Assumed Invariant 3: Equity Consistency**
- **Statement**: `equity` parameter in `update()` represents current total equity (cash + realized_pnl + unrealized_pnl)
- **Enforcement**: None (caller responsibility)
- **What breaks if violated**: All calculations incorrect (high-water mark, trailing drawdown, daily loss)

**Assumed Invariant 4: Snapshot Ordering**
- **Statement**: `snapshots` list is chronologically ordered (by timestamp)
- **Enforcement**: None (appends in order, but no validation)
- **What breaks if violated**: Day boundary detection may fail (uses `snapshots[-1].timestamp` [L141])

**Assumed Invariant 5: Trading Date Consistency**
- **Statement**: `trading_date` matches the date of the trading session
- **Enforcement**: None (caller responsibility)
- **What breaks if violated**: Day boundary detection may fail, daily loss calculations incorrect

**Assumed Invariant 6: Realized/Unrealized PnL Consistency**
- **Statement**: `realized_pnl` and `unrealized_pnl` parameters are consistent with positions and equity
- **Enforcement**: None (caller responsibility)
- **What breaks if violated**: Snapshot data incorrect, but doesn't affect drawdown calculations (which use equity directly)

## 6) Serialization Contract

### 6.1 `DrawdownSnapshot.to_dict()` Format [L57-L69]

**Output structure**:
```python
{
    "timestamp": str,  # ISO format datetime string
    "equity": float,
    "initial_balance": float,
    "high_water_mark": float,
    "trailing_drawdown": float,
    "trailing_drawdown_pct": float,
    "realized_pnl": float,
    "unrealized_pnl": float,
    "state": str  # "active", "locked", or "reset" (DrawdownState.value)
}
```

**Fields**: All 9 fields are serialized

**Determinism**: Yes (same snapshot → same dict, no randomness)

### 6.2 `DrawdownTracker.to_dict()` Format [L237-L245]

**Output structure**:
```python
{
    "initial_balance": float,
    "trading_date": str,  # ISO format date string
    "high_water_mark": float,
    "is_locked": bool,
    "snapshots": [  # List of DrawdownSnapshot.to_dict() results
        {
            "timestamp": str,
            "equity": float,
            "initial_balance": float,
            "high_water_mark": float,
            "trailing_drawdown": float,
            "trailing_drawdown_pct": float,
            "realized_pnl": float,
            "unrealized_pnl": float,
            "state": str
        },
        ...
    ]
}
```

**Fields**: All 5 fields are serialized

**Determinism**: Yes (same tracker → same dict, no randomness)

### 6.3 `DrawdownTracker.from_dict()` Expectations [L247-L275]

**Input expectations**:
- `data["initial_balance"]`: float (required)
- `data["trading_date"]`: ISO format date string (required, parsed via `date.fromisoformat()`)
- `data["high_water_mark"]`: float (optional, defaults to `initial_balance` [L255])
- `data["is_locked"]`: bool (optional, defaults to False [L256])
- `data["snapshots"]`: list of snapshot dicts (optional, defaults to empty list [L261])

**Snapshot dict expectations** (for each in `data["snapshots"]`):
- `snap_data["timestamp"]`: ISO format datetime string (required, parsed via `datetime.fromisoformat()`)
- `snap_data["equity"]`: float (required)
- `snap_data["initial_balance"]`: float (required)
- `snap_data["high_water_mark"]`: float (required)
- `snap_data["trailing_drawdown"]`: float (required)
- `snap_data["trailing_drawdown_pct"]`: float (required)
- `snap_data["realized_pnl"]`: float (required)
- `snap_data["unrealized_pnl"]`: float (required)
- `snap_data["state"]`: string ("active", "locked", or "reset") (required, parsed via `DrawdownState()`)

**Failure modes**:
- `KeyError` if required fields missing (not caught, will raise)
- `ValueError` if date/datetime parsing fails (not caught, will raise)
- `ValueError` if state string invalid (not caught, will raise)

### 6.4 Round-Trip Safety Guarantees

**Guarantee**: `tracker == DrawdownTracker.from_dict(tracker.to_dict())` is **NOT GUARANTEED** because:
1. `DrawdownSnapshot` is not compared for equality (no `__eq__` defined, uses default dataclass comparison)
2. Floating-point precision may differ after serialization
3. Tracker state is restored, but snapshots list is reconstructed (new list object, but contents should be equal)

**Functional equivalence**: After round-trip, tracker should be **functionally equivalent** (same field values, same behavior), but object identity differs.

**Missing validation**: `from_dict()` does not validate that restored snapshots are consistent with tracker state (e.g., that snapshot high_water_mark matches tracker high_water_mark at that point).

## 7) Interaction Points

### 7.1 Where lifecycle.runner Mutates or Reads Tracker

**Reading tracker state**:

1. **runner.py:389** - Reads `current_state.drawdown_tracker` to preserve in state_before snapshot
2. **runner.py:903, 922-923** - Reads `current_state.drawdown_tracker` to check if exists, then reads `is_locked` and `high_water_mark` for debug prints
3. **runner.py:1075-1076, 1098-1099** - Reads `current_state.drawdown_tracker` to preserve in new state (normal and hold-quantity modes)

**Mutating tracker state**:

1. **runner.py:908-914** - Calls `current_state.drawdown_tracker.update()` with computed equity (hold-quantity mode)
   - Updates tracker in-place
   - Mutates `high_water_mark`, `is_locked`, `snapshots` list
   - May mutate `initial_balance` and `trading_date` if day rollover detected

**Preserving tracker**:

- Tracker is preserved across state saves/loads via `state_store.py` (serialization/deserialization)

### 7.2 Where Rulesets Depend on Tracker State

**topstep.py usage** (UNKNOWN: exact implementation, but based on grep results):

1. **Initialization [L185, L217-L226]**: Gets or creates tracker from `current_state.drawdown_tracker`
2. **Equity calculation [L209-L214]**: Uses `calculate_portfolio_equity()` function
3. **Tracker update [L236-L242]**: Calls `drawdown_tracker.update()` with equity, PnL, timestamp, day_boundary
4. **State preservation [L225-L226]**: Stores tracker back in `current_state.drawdown_tracker`
5. **Lock state check [L252-L263]**: Validates that lock state never reverts (invariant enforcement)
6. **Daily loss check [L266-L269]**: Uses `snapshot.equity - snapshot.initial_balance` for daily loss calculation
7. **Trailing drawdown check [L271-L283]**: Uses `snapshot.trailing_drawdown_pct` to check against max_trailing_drawdown_pct

**Dependencies**:
- Ruleset validation depends on `snapshot.trailing_drawdown_pct` [L271-L283] (UNKNOWN: exact implementation)
- Ruleset validation depends on daily loss calculation [L266-L269]
- Ruleset enforces lock state monotonicity [L252-L263]

## 8) Unknowns

### UNKNOWN: Line 142 - `day_boundary.has_day_rollover()` implementation
- **Symbol**: `day_boundary.has_day_rollover()`
- **What must be inspected**: `src/rules/day_boundary.py` - `TradingDayBoundary.has_day_rollover()` method
- **Reason**: Cannot determine exact day rollover detection logic, timezone handling, edge cases

### UNKNOWN: Line 144 - `reset_daily_loss_for_new_day()` implementation
- **Symbol**: `reset_daily_loss_for_new_day()`
- **What must be inspected**: `src/rules/day_boundary.py` - `reset_daily_loss_for_new_day()` function
- **Reason**: Cannot determine exact reset logic, what state is preserved vs reset, return value structure

### UNKNOWN: Line 145 - `day_boundary.get_trading_date()` implementation
- **Symbol**: `day_boundary.get_trading_date()`
- **What must be inspected**: `src/rules/day_boundary.py` - `TradingDayBoundary.get_trading_date()` method
- **Reason**: Cannot determine timezone conversion logic, date calculation, edge cases

### UNKNOWN: Line 147-151 - Return value from `reset_daily_loss_for_new_day()`
- **Symbol**: `reset_tracker` object structure and field values
- **What must be inspected**: `src/rules/day_boundary.py` - `reset_daily_loss_for_new_day()` return value
- **Reason**: Cannot determine what fields are set in returned tracker, how state is preserved

### UNKNOWN: Line 300-321 - `calculate_portfolio_equity()` Position interface
- **Symbol**: `position.is_long()`, `position.cost_basis`, `position.quantity`
- **What must be inspected**: `src/execution/position.py` - `Position` class methods and attributes
- **Reason**: Cannot determine exact Position API, what methods/attributes are available, behavior of `is_long()` vs checking `quantity > 0`

### UNKNOWN: Line 304 - `current_prices.get()` behavior with missing keys
- **Symbol**: `current_prices.get(instrument)` return value when key missing
- **What must be inspected**: Python dict.get() behavior (well-known, but need to verify handling)
- **Reason**: Logic continues if price is None [L305-L307], need to verify this is correct behavior

### UNKNOWN: Line 312, 315 - Position unrealized PnL calculation correctness
- **Symbol**: Position unrealized PnL formulas for long vs short
- **What must be inspected**: Business logic correctness (long: `(price - cost) * qty`, short: `(cost - price) * abs(qty)`)
- **Reason**: Need to verify formulas are correct for short positions (typically short PnL = `(entry_price - exit_price) * quantity` where quantity is negative)

