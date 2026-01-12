# ExecutionMode Enum Proposal

## Enum Definition

```python
from enum import Enum

class ExecutionMode(str, Enum):
    """Execution mode for portfolio cycles.
    
    SIMULATION: Allows relaxed constraints for testing/backtesting
    LIVE: Enforces strict constraints for production trading
    """
    SIMULATION = "simulation"
    LIVE = "live"
```

## 1) Forbid Implicit Timestamps

### Problem
`datetime.now()` calls create non-deterministic timestamps that prevent reproducibility in LIVE mode.

### Insertion Points

#### A) `src/lifecycle/runner.py` - Cycle Timestamp Generation

**Location**: [L363, L365]

**Current code**:
```python
if cycle_id is None:
    cycle_id = config.cycle_id or f"cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

cycle_timestamp = datetime.now()
```

**Proposed contract**:
- `ExecutionMode.LIVE`: `cycle_timestamp` MUST be provided explicitly (via new parameter or config field)
- `ExecutionMode.SIMULATION`: `datetime.now()` allowed as fallback

**Insertion point**: 
- Add `execution_mode: ExecutionMode` parameter to `run_portfolio_cycle()`
- Add validation: if `execution_mode == ExecutionMode.LIVE` and `cycle_timestamp` not provided, raise `CycleError("LIVE mode requires explicit cycle_timestamp")`
- Alternative: Add `cycle_timestamp: Optional[datetime]` parameter and validate based on mode

#### B) `src/rules/drawdown.py` - DrawdownTracker.update() Timestamp

**Location**: [L136-L137]

**Current code**:
```python
if timestamp is None:
    timestamp = datetime.now()
```

**Proposed contract**:
- `ExecutionMode.LIVE`: `timestamp` parameter MUST NOT be None
- `ExecutionMode.SIMULATION`: `datetime.now()` allowed as fallback

**Insertion point**:
- Add `execution_mode: ExecutionMode` parameter to `DrawdownTracker.update()`
- Add validation: if `execution_mode == ExecutionMode.LIVE` and `timestamp is None`, raise `ValueError("LIVE mode requires explicit timestamp")`
- **Calls to update**: Must pass explicit timestamp when mode is LIVE:
  - `src/lifecycle/runner.py:908` (hold-quantity mode) - already passes explicit timestamp ✓
  - `src/rules/topstep.py:236` - passes `execution_result.execution_timestamp` ✓

**Note**: Both call sites already pass explicit timestamps, but validation should enforce this.

#### C) `src/rebalance/executor.py` - Execution Timestamp Generation

**Location**: [L216, L288, L436]

**Current code**:
```python
# Line 216 (in map_intent_to_signal, if timestamp is None):
if timestamp is None:
    timestamp = datetime.now()

# Line 288 (in execute_rebalance_plan, if execution_id is None):
if execution_id is None:
    execution_id = f"rebalance_exec_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Line 436 (in RebalanceExecutionResult construction):
execution_timestamp=datetime.now(),
```

**Proposed contract**:
- `ExecutionMode.LIVE`: All timestamps and IDs MUST be provided explicitly
- `ExecutionMode.SIMULATION`: `datetime.now()` allowed as fallback

**Insertion points**:
- Add `execution_mode: ExecutionMode` parameter to `execute_rebalance_plan()`
- Add validation in `map_intent_to_signal()`: if mode is LIVE and `timestamp is None`, raise error
- Pass `execution_timestamp` as parameter to `execute_rebalance_plan()` instead of generating it
- Pass `execution_id` as parameter or require it (no auto-generation in LIVE mode)

#### D) `src/allocation/allocator.py` - Allocation Timestamp Generation

**Location**: [L384, L394, L438]

**Current code**:
```python
# Line 384 (in allocate_capital):
if allocation_id is None:
    allocation_id = f"alloc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Lines 394, 438 (allocation_timestamp):
allocation_timestamp=datetime.now(),
```

**Proposed contract**:
- `ExecutionMode.LIVE`: `allocation_id` and `allocation_timestamp` MUST be provided explicitly
- `ExecutionMode.SIMULATION`: `datetime.now()` allowed as fallback

**Insertion points**:
- Add `execution_mode: ExecutionMode` parameter to `allocate_capital()`
- Require `allocation_timestamp` parameter in LIVE mode
- Require `allocation_id` parameter in LIVE mode (no auto-generation)

#### E) `src/rebalance/planner.py` - Plan Timestamp Generation

**Location**: [L481, L516]

**Current code**:
```python
# Line 481 (in plan_rebalance):
if plan_id is None:
    plan_id = f"rebalance_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Line 516 (plan_timestamp):
plan_timestamp=datetime.now(),
```

**Proposed contract**:
- `ExecutionMode.LIVE`: `plan_id` and `plan_timestamp` MUST be provided explicitly
- `ExecutionMode.SIMULATION`: `datetime.now()` allowed as fallback

**Insertion points**:
- Add `execution_mode: ExecutionMode` parameter to `plan_rebalance()`
- Require `plan_timestamp` parameter in LIVE mode
- Require `plan_id` parameter in LIVE mode (no auto-generation)

#### F) Lower-level Execution Engine Timestamps

**Locations**: `src/execution/paper_engine.py`, `src/execution/position.py`, `src/execution/order.py`, `src/execution/fill.py`

**Current code**: Multiple `datetime.now()` calls for order/fill timestamps

**Proposed contract**:
- `ExecutionMode.LIVE`: All timestamps MUST be provided explicitly
- `ExecutionMode.SIMULATION`: `datetime.now()` allowed as fallback

**Insertion points**:
- Add `execution_mode` to `PaperExecutionEngine.__init__()`
- Pass timestamps explicitly through execution chain
- Validate timestamps are not None in LIVE mode at each step

### Summary: Implicit Timestamp Forbidding

**Contract Pattern**:
```python
def function(..., execution_mode: ExecutionMode, timestamp: Optional[datetime] = None):
    if execution_mode == ExecutionMode.LIVE and timestamp is None:
        raise ValueError(f"LIVE mode requires explicit timestamp for {function.__name__}")
    if timestamp is None:
        timestamp = datetime.now()  # Only allowed in SIMULATION
```

## 2) Forbid Relaxed Guardrails

### Problem
Guardrails can be disabled by setting `guardrails_config=None` or setting permissive limits, which is unsafe in LIVE mode.

### Insertion Points

#### A) `src/lifecycle/runner.py` - GuardrailsConfig Validation

**Location**: [L514, L616, L720]

**Current code**:
```python
# Line 514 (allocation guardrails):
if use_normal_cycle and config.guardrails_config:
    # Check guardrails

# Line 616 (rebalance guardrails):
if config.guardrails_config:
    # Check guardrails

# Line 720 (execution guardrails):
if use_normal_cycle and config.guardrails_config:
    # Check guardrails
```

**Proposed contract**:
- `ExecutionMode.LIVE`: `guardrails_config` MUST NOT be None
- `ExecutionMode.LIVE`: Guardrails MUST have non-permissive values:
  - `max_turnover_pct_per_cycle < 1.0` (must have some limit)
  - `max_failed_intents is not None` (must have limit)
  - `min_execution_success_rate > 0.0` (must require some success)
  - `max_single_strategy_allocation_fraction < 1.0` (must have concentration limit)
- `ExecutionMode.SIMULATION`: Guardrails can be None or permissive

**Insertion point**: 
- Add validation at start of `run_portfolio_cycle()`:
```python
if execution_mode == ExecutionMode.LIVE:
    if config.guardrails_config is None:
        raise CycleError("LIVE mode requires guardrails_config")
    # Validate guardrail limits are non-permissive
    validate_live_guardrails(config.guardrails_config)
```

#### B) `src/lifecycle/guardrails.py` - GuardrailsConfig Validation

**Location**: Create new validation function

**Proposed function**:
```python
def validate_live_guardrails(config: GuardrailsConfig) -> None:
    """Validate guardrails are appropriate for LIVE mode.
    
    Raises:
        ValueError: If guardrails are too permissive for LIVE mode
    """
    if config.max_turnover_pct_per_cycle >= 1.0:
        raise ValueError("LIVE mode requires max_turnover_pct_per_cycle < 1.0")
    if config.max_failed_intents is None:
        raise ValueError("LIVE mode requires max_failed_intents to be set")
    if config.min_execution_success_rate <= 0.0:
        raise ValueError("LIVE mode requires min_execution_success_rate > 0.0")
    if config.max_single_strategy_allocation_fraction >= 1.0:
        raise ValueError("LIVE mode requires max_single_strategy_allocation_fraction < 1.0")
```

**Insertion point**: Call this function in `run_portfolio_cycle()` when `execution_mode == ExecutionMode.LIVE`

## 3) Forbid Post-Halt Continuation

### Problem
After a cycle halts, the caller could continue processing or start a new cycle, which is unsafe in LIVE mode.

### Insertion Points

#### A) `src/lifecycle/runner.py` - Post-Halt State Check

**Location**: [L1032-L1059, and other halt return points]

**Current code**:
```python
if halt_violations:
    return CycleResult(
        ...
        status="halted",
        state_after_id=None,  # Don't update state if halted
        ...
    )

# Execution continues after halt (function returns normally)
```

**Proposed contract**:
- `ExecutionMode.LIVE`: After returning halted CycleResult, system MUST NOT allow subsequent cycles until manual intervention
- `ExecutionMode.SIMULATION`: Post-halt continuation allowed (for testing)

**Insertion point**: 
- Add `execution_mode` parameter to `run_portfolio_cycle()`
- After returning halted result, check mode and raise exception to prevent continuation:
```python
if halt_violations:
    result = CycleResult(..., status="halted", ...)
    if execution_mode == ExecutionMode.LIVE:
        # In LIVE mode, halt must stop all further processing
        raise CycleHaltError(
            f"Cycle halted in LIVE mode: {skip_reason}. "
            "Manual intervention required before continuing.",
            result=result
        )
    return result
```

**Note**: This requires a new exception type `CycleHaltError` that carries the result.

#### B) State Store - Halted State Tracking

**Location**: `src/lifecycle/state_store.py` or new validation module

**Proposed contract**:
- `ExecutionMode.LIVE`: Before starting new cycle, check if portfolio is in halted state
- `ExecutionMode.SIMULATION`: Skip halted state check

**Insertion point**: 
- Add check at start of `run_portfolio_cycle()`:
```python
if execution_mode == ExecutionMode.LIVE and state_store:
    # Check if portfolio is in halted state (from previous cycle)
    if is_portfolio_halted(state_store, config.portfolio_id):
        raise CycleError(
            f"Portfolio {config.portfolio_id} is in halted state. "
            "Manual intervention required before continuing."
        )
```

**Implementation note**: Need to track halted state (could use a flag file, or check if last cycle result has status="halted" and state_after_id=None)

#### C) Validation Runner - Post-Halt Continuation Check

**Location**: `src/lifecycle/validation_runner.py` [L462-L464]

**Current code**:
```python
if result.status == "halted":
    print(f"HALT detected at cycle {day}. Stopping early.")
    break  # Stops loop, but function continues normally
```

**Proposed contract**:
- `ExecutionMode.LIVE`: Validation runner MUST NOT continue after halt
- `ExecutionMode.SIMULATION`: Early stopping allowed

**Insertion point**: 
- Add `execution_mode` parameter to validation runner functions
- After halt, raise exception in LIVE mode instead of just breaking:
```python
if result.status == "halted":
    if execution_mode == ExecutionMode.LIVE:
        raise ValidationHaltError(
            f"Validation halted at cycle {day} in LIVE mode. "
            "Cannot continue.",
            result=result
        )
    print(f"HALT detected at cycle {day}. Stopping early.")
    break
```

### Summary: Post-Halt Continuation Forbidding

**Contract Pattern**:
```python
if halt_detected:
    result = CycleResult(..., status="halted")
    if execution_mode == ExecutionMode.LIVE:
        raise CycleHaltError("Cannot continue after halt in LIVE mode", result=result)
    return result  # SIMULATION mode: return and allow continuation
```

## Execution Engine Instantiation Points

### Where Execution Engines Are Created

1. **`src/lifecycle/runner.py:1274`** - Factory function in `main()`
2. **`src/lifecycle/validation_runner.py:388`** - Factory function
3. **`src/evaluation/batch.py:523`** - Factory function in `main()`
4. **`src/api/app.py:523`** - API endpoint (POST /paper/sessions)
5. **`src/lifecycle/demo_two_cycles.py:108`** - Demo code
6. **`src/control/demo_position_size_control.py:129`** - Demo code

### Proposed: ExecutionMode Propagation

**Contract**: ExecutionMode should be set when creating execution engine factory:

```python
def create_engine_factory(instrument: str, execution_mode: ExecutionMode) -> Callable[[], PaperExecutionEngine]:
    def factory():
        return PaperExecutionEngine(
            instrument=instrument,
            execution_mode=execution_mode,  # Pass mode to engine
            ...
        )
    return factory
```

**Insertion point**: All factory creation sites should accept and pass `execution_mode`.

## Drawdown.update() Call Sites

### Where drawdown.update() is Called

1. **`src/lifecycle/runner.py:908`** - Hold-quantity mode, already passes explicit timestamp ✓
2. **`src/rules/topstep.py:236`** - Ruleset validation, passes `execution_result.execution_timestamp` ✓

**Both sites already pass explicit timestamps**, but need validation to enforce this in LIVE mode.

## Recommended Implementation Order

1. **Define ExecutionMode enum** in `src/core/` or `src/lifecycle/`
2. **Add execution_mode parameter** to `run_portfolio_cycle()`
3. **Implement timestamp validation** (section 1)
4. **Implement guardrails validation** (section 2)
5. **Implement post-halt prevention** (section 3)
6. **Propagate execution_mode** through call chain (allocation, rebalance, execution)
7. **Update all factory functions** to accept and pass execution_mode
8. **Add CycleHaltError exception** for LIVE mode halts

