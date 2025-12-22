# Semantic Audit: src/rules/day_boundary.py

## 1) File Purpose

This module provides trading day boundary logic for Topstep-style rules, determining when day rollover occurs and resetting daily loss tracking while preserving trailing drawdown across days.

## 2) Data Model

### 2.1 `TradingDayBoundary` [L18-L80]
- **Type**: dataclass (frozen=True, immutable)
- **Purpose**: Trading day boundary configuration

**Fields:**

- `timezone: timezone` [L27]
  - **Default**: `timezone.utc` [L27]
  - **Purpose**: Timezone for trading day boundaries
  - **When set**: Constructor/default
  - **When read**: `get_trading_date()` [L40, L42, L45], `is_same_trading_day()` [L60]
  - **Mutates**: No (frozen dataclass)
  - **Persisted**: Not in this module (no serialization methods)

- `session_start_time: time` [L28]
  - **Default**: `time(0, 0, 0)` (midnight) [L28]
  - **Purpose**: Start time of trading session (documented but **NEVER USED** in code)
  - **When set**: Constructor/default
  - **When read**: Never (field exists but is unused)
  - **Mutates**: No (frozen dataclass)
  - **Persisted**: Not in this module (no serialization methods)

**Methods:**

#### Method: `get_trading_date(timestamp)` [L30-L48]
- **Inputs**: 
  - `timestamp: datetime` - Datetime (will be converted to self.timezone)
- **Outputs**: 
  - `date` - Trading date for this timestamp (date portion after timezone conversion)
- **Side effects**: None (pure function, may modify local timestamp variable [L42, L45] but not object state)
- **Determinism guarantees**: Yes (same timestamp → same date, but depends on timestamp timezone handling)

**Process**:
1. If `timestamp.tzinfo is None` (naive timestamp): assumes it's in `self.timezone` [L40-L42]
2. If `timestamp.tzinfo is not None` (aware timestamp): converts to `self.timezone` [L43-L45]
3. Returns `timestamp.date()` [L48] (date portion of converted timestamp)

#### Method: `is_same_trading_day(timestamp1, timestamp2)` [L50-L60]
- **Inputs**: 
  - `timestamp1: datetime` - First timestamp
  - `timestamp2: datetime` - Second timestamp
- **Outputs**: 
  - `bool` - True if same trading day, False otherwise
- **Side effects**: None (pure function)
- **Determinism guarantees**: Yes (same inputs → same output)

**Process**: Calls `get_trading_date()` on both timestamps and compares dates [L60]

#### Method: `has_day_rollover(previous_timestamp, current_timestamp)` [L62-L79]
- **Inputs**: 
  - `previous_timestamp: Optional[datetime]` - Previous timestamp (None if first update)
  - `current_timestamp: datetime` - Current timestamp
- **Outputs**: 
  - `bool` - True if rollover occurred, False otherwise
- **Side effects**: None (pure function)
- **Determinism guarantees**: Yes (same inputs → same output)

**Process**:
1. If `previous_timestamp is None`: returns False [L76-L77] (no rollover on first update)
2. Otherwise: returns `not self.is_same_trading_day(previous_timestamp, current_timestamp)` [L79]

### 2.2 Function: `reset_daily_loss_for_new_day()` [L82-L133]
- **Type**: Module-level function
- **Purpose**: Reset daily loss tracking for a new trading day while preserving trailing drawdown

**Inputs**:
- `tracker: 'DrawdownTracker'` - Current drawdown tracker [L83]
- `new_trading_date: date` - New trading date [L84]
- `new_initial_balance: Optional[float] = None` - New initial balance for the day (default: current equity) [L85]

**Outputs**:
- `DrawdownTracker` - New DrawdownTracker instance with daily loss reset but trailing drawdown preserved [L86, L133]

**Side effects**: 
- None (creates new object, does not mutate input tracker)

**Determinism guarantees**: Yes (same inputs → same output tracker state)

**Process**:
1. Gets current equity from latest snapshot if available [L111-L113], otherwise uses `tracker.initial_balance` [L115]
2. If `new_initial_balance is None`, uses `current_equity` [L118-L119]
3. Creates new `DrawdownTracker` [L125-L131]:
   - `initial_balance=new_initial_balance` (reset)
   - `trading_date=new_trading_date` (reset)
   - `high_water_mark=tracker.high_water_mark` (preserved)
   - `is_locked=tracker.is_locked` (preserved)
   - `snapshots=list(tracker.snapshots)` (preserved, but new list object)

## 3) Trading Day Definition

### 3.1 Timezone Assumption

**Default timezone**: UTC [L27] (`timezone.utc`)

**Timezone handling** [L39-L45]:
- Naive timestamps (no tzinfo): Assumed to be in `self.timezone` [L40-L42]
- Aware timestamps (with tzinfo): Converted to `self.timezone` [L43-L45]

**Implications**: 
- All date comparisons are done after conversion to configured timezone
- Trading day boundaries are defined by date change in configured timezone
- Different timezones may produce different trading days for same timestamp

### 3.2 Day Rollover Definition

**Rollover occurs when**: Two timestamps have different trading dates (after timezone conversion) [L79]

**Rollover detection**: 
- `has_day_rollover()` returns True if `not is_same_trading_day(previous_timestamp, current_timestamp)` [L79]
- First update (previous_timestamp is None) never triggers rollover [L76-L77]

**Boundary timing**: 
- Trading day is determined by `timestamp.date()` in configured timezone [L48]
- Date change occurs at midnight (00:00:00) in configured timezone
- **Boundary is exclusive**: Timestamps on same date (even at 23:59:59 and 00:00:01) are same day; timestamps on different dates are different days

**Example**:
- `2024-01-01 23:59:59 UTC` and `2024-01-02 00:00:00 UTC` → different trading days (rollover detected)
- `2024-01-01 00:00:00 UTC` and `2024-01-01 23:59:59 UTC` → same trading day (no rollover)

### 3.3 Weekends and Holidays

**Weekends**: **NOT CONSIDERED** - Code does not check if date is weekend. Any date change triggers rollover regardless of day of week.

**Holidays**: **NOT CONSIDERED** - Code does not check if date is holiday. Any date change triggers rollover regardless of holiday status.

**Trading calendar**: Code does not use any trading calendar. Trading day = calendar day in configured timezone.

### 3.4 Boundary Inclusivity/Exclusivity

**Same trading day**: Timestamps on the same date (in configured timezone) are considered the same trading day [L60, L48]

**Boundary**: Date change at midnight (00:00:00) in configured timezone. The exact moment of midnight belongs to the new day.

**Inclusivity**: 
- All timestamps on date X (00:00:00 to 23:59:59.999...) are same trading day
- Timestamp at 00:00:00 belongs to new day (not previous day)

**Example with timezone conversion**:
- Timestamp `2024-01-01 08:00:00 EST` (2024-01-01 13:00:00 UTC) → trading date depends on configured timezone
  - If timezone=UTC: trading date = 2024-01-01
  - If timezone=EST: trading date = 2024-01-01

### 3.5 Session Start Time (UNUSED)

**Field**: `session_start_time: time = time(0, 0, 0)` [L28]

**Usage**: **NEVER USED** in code. Field exists but is not referenced anywhere in the file.

**Implication**: Trading day starts at 00:00:00 in configured timezone, but `session_start_time` field has no effect on logic.

## 4) Reset Semantics

### 4.1 What `reset_daily_loss_for_new_day()` Does

**Functionality**: Creates a new `DrawdownTracker` instance with some fields reset and others preserved [L125-L131]

**Step-by-step**:

1. **Determine current equity** [L110-L115]:
   - If `tracker.snapshots` is non-empty: uses `tracker.snapshots[-1].equity` [L112-L113]
   - If `tracker.snapshots` is empty: uses `tracker.initial_balance` [L115]

2. **Determine new initial balance** [L117-L119]:
   - If `new_initial_balance` parameter is provided: uses it
   - If `new_initial_balance` is None: uses `current_equity` (from step 1)

3. **Create new tracker** [L125-L131]:
   - Constructs new `DrawdownTracker` with:
     - `initial_balance=new_initial_balance` (from step 2)
     - `trading_date=new_trading_date` (from parameter)
     - `high_water_mark=tracker.high_water_mark` (copied from old tracker)
     - `is_locked=tracker.is_locked` (copied from old tracker)
     - `snapshots=list(tracker.snapshots)` (copied list, but new list object)

4. **Return new tracker** [L133]

### 4.2 Fields Preserved

**Preserved fields** (copied from old tracker to new tracker):

1. **`high_water_mark`** [L128] - Preserved exactly (trailing drawdown persists)
2. **`is_locked`** [L129] - Preserved exactly (lock state persists)
3. **`snapshots`** [L130] - Preserved (list contents copied, but new list object created)

### 4.3 Fields Reset

**Reset fields** (new values in new tracker):

1. **`initial_balance`** [L126] - Set to `new_initial_balance` (or `current_equity` if None)
2. **`trading_date`** [L127] - Set to `new_trading_date` parameter

### 4.4 Trailing Drawdown Effect

**Trailing drawdown is NOT affected**:
- `high_water_mark` is preserved [L128] (trailing drawdown calculation depends on high_water_mark)
- `is_locked` is preserved [L129] (lock state affects trailing drawdown calculation)
- Only `initial_balance` is reset, which affects daily loss calculation, not trailing drawdown

**Daily loss calculation**: Resets because `initial_balance` is reset. Daily loss = `equity - initial_balance`, so new day starts with `initial_balance = current_equity`, making initial daily loss = 0.

**Trailing drawdown calculation**: Unaffected because `trailing_drawdown = max(0.0, high_water_mark - equity)` depends only on `high_water_mark` and `equity`, not `initial_balance`.

## 5) Determinism Analysis

### 5.1 Identical Timestamp Input

**Question**: Does identical timestamp input always produce identical output?

**Answer**: **YES**, with caveats.

**`get_trading_date()`**:
- Same `timestamp` + same `self.timezone` → same date
- Deterministic for naive timestamps (assumed to be in self.timezone)
- Deterministic for aware timestamps (converted deterministically)

**`is_same_trading_day()`**:
- Same `timestamp1` + same `timestamp2` + same `self.timezone` → same bool
- Deterministic (calls `get_trading_date()` twice and compares)

**`has_day_rollover()`**:
- Same `previous_timestamp` + same `current_timestamp` + same `self.timezone` → same bool
- Deterministic (calls `is_same_trading_day()`)

**`reset_daily_loss_for_new_day()`**:
- Same `tracker` state + same `new_trading_date` + same `new_initial_balance` → same output tracker
- Deterministic (pure function, no randomness, no system calls)

**Caveat**: If timestamps have different timezone info but represent same moment, results may differ if timezone conversion produces different dates.

### 5.2 Implicit System Time Calls

**None**: No calls to `datetime.now()`, `time.time()`, or other system time functions in this module.

All methods are pure functions that operate on provided inputs only.

### 5.3 Locale Dependence

**None**: No locale-dependent operations. All date/time operations use Python's `datetime` module which is locale-independent.

### 5.4 Timezone Dependence

**Explicit dependence**: 
- All date calculations depend on `self.timezone` [L27, L40-L45]
- Same timestamp in different timezones may produce different trading dates

**Example**:
- `2024-01-01 23:00:00 UTC` → trading date = 2024-01-01 (UTC)
- `2024-01-01 23:00:00 EST` (2024-01-02 04:00:00 UTC) → trading date = 2024-01-02 (EST) or 2024-01-01 (UTC) depending on configured timezone

**Determinism**: Within same timezone configuration, results are deterministic.

## 6) Invariants

### 6.1 Explicit Invariants Enforced

**None**: No explicit invariant checks (no assertions, no validation, no error raising for invariant violations).

All methods assume inputs are valid and do not validate invariants.

### 6.2 Implicit Invariants Assumed

**Assumed Invariant 1: TradingDayBoundary Immutability**
- **Statement**: `TradingDayBoundary` instance is immutable (frozen dataclass)
- **Enforcement**: Python dataclass frozen=True [L18]
- **What breaks if violated**: Methods assume `self.timezone` doesn't change between calls

**Assumed Invariant 2: Timestamp Validity**
- **Statement**: `timestamp` parameters are valid datetime objects
- **Enforcement**: None (no validation)
- **What breaks if violated**: `timestamp.date()`, `timestamp.tzinfo`, `timestamp.astimezone()` may raise exceptions or produce incorrect results

**Assumed Invariant 3: Timezone Object Validity**
- **Statement**: `self.timezone` is a valid timezone object (supports `replace(tzinfo=...)` and `astimezone(...)`)
- **Enforcement**: None (default is `timezone.utc`, but no validation if changed)
- **What breaks if violated**: Timezone conversion may fail or produce incorrect results

**Assumed Invariant 4: Tracker State Consistency**
- **Statement**: `tracker` parameter in `reset_daily_loss_for_new_day()` is a valid DrawdownTracker with consistent state
- **Enforcement**: None (no validation)
- **What breaks if violated**: Accessing `tracker.snapshots[-1]` may raise IndexError if snapshots is empty (but code checks for this [L111])

**Assumed Invariant 5: Date Validity**
- **Statement**: `new_trading_date` parameter is a valid date object
- **Enforcement**: None (no validation)
- **What breaks if violated**: DrawdownTracker constructor may fail or produce invalid tracker

**Assumed Invariant 6: Snapshot Equity Consistency**
- **Statement**: `tracker.snapshots[-1].equity` (if exists) represents current equity
- **Enforcement**: None (caller responsibility)
- **What breaks if violated**: New initial_balance may be set incorrectly if snapshot equity is stale

**Assumed Invariant 7: No Timezone Ambiguity for Naive Timestamps**
- **Statement**: Naive timestamps (no tzinfo) are in `self.timezone`
- **Enforcement**: None (assumed, not validated)
- **What breaks if violated**: Trading day may be calculated incorrectly if naive timestamp is actually in different timezone

## 7) Interaction Points

### 7.1 Where DrawdownTracker Depends on This Module

**drawdown.py usage**:

1. **Import [L21]**: `from .day_boundary import TradingDayBoundary` (TYPE_CHECKING only)
2. **update() method parameter [L116]**: `day_boundary: Optional['TradingDayBoundary'] = None`
3. **Day rollover check [L140-L142]**: 
   - If `day_boundary is not None`: calls `day_boundary.has_day_rollover(previous_timestamp, timestamp)`
   - Detects if day rollover occurred between last snapshot and current timestamp
4. **Trading date retrieval [L145]**: Calls `day_boundary.get_trading_date(timestamp)` to get new trading date
5. **Reset call [L147-L151]**: Calls `reset_daily_loss_for_new_day()` with tracker, new_trading_date, and equity
6. **State update [L153-L154]**: Updates tracker's `initial_balance` and `trading_date` from reset_tracker result

**Dependencies**:
- DrawdownTracker.update() depends on TradingDayBoundary for day rollover detection
- Day rollover triggers daily loss reset while preserving trailing drawdown

### 7.2 Where lifecycle.runner Depends on This Module

**runner.py usage** (based on grep results):

1. **Import [L822, L904, L1005]**: `from ..rules.day_boundary import TradingDayBoundary`
2. **Instantiation [L823, L905, L1006]**: `day_boundary = TradingDayBoundary()  # Default UTC`
   - Creates default TradingDayBoundary (UTC timezone)
   - Used in ruleset validation calls
3. **Ruleset validation [L828-L837, L1013-L1027]**: Passes `day_boundary` to `ruleset.validate_execution()`
   - Used for day rollover detection during execution validation

**Dependencies**:
- lifecycle.runner creates TradingDayBoundary instances for ruleset validation
- Day boundary is passed to TopstepRuleset.validate_execution() for day rollover handling

**Note**: Runner does not directly call day_boundary methods; it creates instances and passes them to rulesets.

## 8) Unknowns

### UNKNOWN: Line 28 - Purpose of `session_start_time` field
- **Symbol**: `session_start_time: time`
- **What must be inspected**: No other files (field is unused)
- **Reason**: Field is defined but never referenced in code. Purpose unclear - may be intended for future use or legacy code.

### UNKNOWN: Line 40-42 - Behavior with naive timestamps in wrong timezone
- **Symbol**: Naive timestamp timezone assumption
- **What must be inspected**: Caller behavior in drawdown.py and runner.py
- **Reason**: Code assumes naive timestamps are in `self.timezone`, but if caller provides naive timestamp in different timezone, trading day calculation will be incorrect. Need to verify caller behavior.

### UNKNOWN: Line 111-115 - Snapshot availability assumption
- **Symbol**: `tracker.snapshots` access
- **What must be inspected**: `src/rules/drawdown.py` - DrawdownTracker class definition
- **Reason**: Code checks `if tracker.snapshots:` but assumes `snapshots[-1]` exists if list is non-empty. Need to verify DrawdownTracker guarantees snapshots is always a list (not None).

### UNKNOWN: Line 130 - List copy behavior
- **Symbol**: `list(tracker.snapshots)`
- **What must be inspected**: Python list() constructor behavior
- **Reason**: Creates shallow copy of list. If snapshots contain mutable objects, mutations may affect both lists. Need to verify if DrawdownSnapshot is immutable (frozen dataclass) to confirm safety.

### UNKNOWN: Line 125-131 - DrawdownTracker constructor behavior
- **Symbol**: `DrawdownTracker(...)`
- **What must be inspected**: `src/rules/drawdown.py` - DrawdownTracker.__init__() and __post_init__()
- **Reason**: Cannot determine if constructor validates inputs, if __post_init__() modifies fields, if default values are applied correctly.

### UNKNOWN: Line 48 - Date extraction behavior at timezone boundaries
- **Symbol**: `timestamp.date()`
- **What must be inspected**: Python datetime.date() behavior documentation
- **Reason**: Need to verify exact behavior when timestamp is at midnight boundary, especially after timezone conversion. Does `date()` return date before or after conversion?

