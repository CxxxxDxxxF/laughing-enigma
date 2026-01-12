# Timestamp Removal Checklist (Step 5B.4)

This checklist tracks remaining `datetime.now()` usages that need to be addressed for LIVE mode determinism.

## Search Results

### Pattern: `datetime.now()`

#### Cycle Boundary (runner.py) - ✅ COMPLETED
- ✅ `src/lifecycle/runner.py` - cycle_id generation (Step 5B.1)
- ✅ `src/lifecycle/runner.py` - cycle_timestamp fallback (validation in place)

#### Planning/Allocation/Execution - ✅ COMPLETED
- ✅ `src/allocation/allocator.py` - allocation_id and allocation_timestamp (Step 5B.2)
- ✅ `src/rebalance/planner.py` - plan_id and plan_timestamp (Step 5B.3)
- ✅ `src/rebalance/executor.py` - execution_id and execution_timestamp (Step 5B.3)

#### Engine Internals - ⚠️ TODO
These need investigation for order/fill timestamps:

1. **`src/execution/paper_engine.py`**
   - Order timestamps
   - Fill timestamps
   - Signal timestamps
   - Position mark-to-market timestamps

2. **`src/execution/engine.py`** (if exists)
   - Any timestamp generation

3. **`src/execution/order.py`**
   - Order creation timestamps

4. **`src/execution/fill.py`**
   - Fill execution timestamps

### Pattern: `strftime('%Y%m%d_%H%M%S')`

All ID generation using this pattern should be addressed:
- ✅ Cycle IDs (Step 5B.1)
- ✅ Allocation IDs (Step 5B.2)
- ✅ Plan IDs (Step 5B.3)
- ✅ Execution IDs (Step 5B.3)

### Pattern: `_id is None` followed by generation

All auto-generation logic should respect LIVE mode:
- ✅ cycle_id (Step 5B.1)
- ✅ allocation_id (Step 5B.2)
- ✅ plan_id (Step 5B.3)
- ✅ execution_id (Step 5B.3)

## Implementation Strategy for Engine Internals

### Approach: Timestamp Provider / Clock Dependency

**Option 1: Thread explicit timestamp through engine methods**
- Pass `current_timestamp` to all order/fill creation methods
- Pros: Explicit, deterministic
- Cons: Many method signature changes

**Option 2: Engine-level timestamp provider**
- Add `timestamp_provider` parameter to engine constructor
- Engine uses provider for all timestamps
- Provider can be:
  - Fixed timestamp (deterministic)
  - `datetime.now()` callback (SIMULATION mode)
- Pros: Centralized, cleaner API
- Cons: Requires refactoring engine initialization

**Option 3: Hybrid**
- Pass explicit timestamp where available (from cycle_timestamp)
- Fallback to engine-provided timestamp only in SIMULATION mode
- Pros: Flexible, gradual migration
- Cons: More complex logic

### Recommended: Option 2 (Engine-level timestamp provider)

**Implementation Steps:**

1. Create `TimestampProvider` interface or callable
2. Modify `PaperExecutionEngine.__init__` to accept `timestamp_provider`
3. Replace all `datetime.now()` in engine with `self.timestamp_provider()`
4. In `run_portfolio_cycle`, create engine with deterministic timestamp provider:
   ```python
   def create_engine():
       return PaperExecutionEngine(
           instrument="AAPL",
           artifact_store=artifact_store,
           timestamp_provider=lambda: cycle_timestamp  # Deterministic
       )
   ```
5. In SIMULATION mode, can still use `datetime.now` if desired

### Files to Modify (in order):

1. `src/execution/paper_engine.py` - Main engine timestamp handling
2. `src/execution/order.py` - Order timestamp
3. `src/execution/fill.py` - Fill timestamp
4. `src/rebalance/executor.py` - map_intent_to_signal timestamp handling

## Validation

After completing Step 5B.4:
- ✅ All `datetime.now()` calls removed or gated by execution_mode
- ✅ All timestamps in LIVE mode are deterministic
- ✅ SIMULATION mode can still use `datetime.now()` at boundaries
- ✅ Tests verify LIVE mode rejects implicit timestamps

