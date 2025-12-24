# Light Artifacts Implementation

## Overview

The `light_artifacts` flag has been threaded through the entire persistence pipeline to enable performance optimization by skipping non-essential artifact writes while preserving state persistence and required artifacts.

## Implementation Details

### Core Function Signature

**File**: `src/lifecycle/runner.py`

```python
def run_portfolio_cycle(
    ...
    light_artifacts: bool = False
) -> CycleResult:
```

### Persistence Functions Updated

All persistence functions now accept `light_artifacts: bool = False`:

1. **`persist_allocation`** (`src/allocation/allocator.py`)
   - Skips `allocation.json` in light mode
   - Returns allocation_id immediately

2. **`persist_rebalance_plan`** (`src/rebalance/planner.py`)
   - Skips `rebalance_plan.json` in light mode
   - Returns plan_id immediately

3. **`persist_rebalance_execution`** (`src/rebalance/executor.py`)
   - **ALWAYS writes** `rebalance_execution.json` (required for trade collection)
   - Note: Execution artifacts are critical for final Layer 2 results

4. **`persist_cycle_result`** (`src/lifecycle/runner.py`)
   - Skips `cycle_result.json` in light mode
   - Returns cycle_id immediately

5. **`persist_evaluation`** (`src/evaluation/evaluator.py`)
   - Skips `evaluation_report.json` in light mode
   - Returns evaluation_id immediately

6. **`_persist_batch_artifacts`** (`src/evaluation/batch.py`)
   - Skips `batch_summary.json` and `results_index.json` in light mode
   - Skips full evaluation report in light mode

7. **`run_backtest`** (`src/engines/simple.py`)
   - In light mode: Only writes `raw_returns.json` (required for evaluation)
   - Skips `metrics.json` and `run_metadata.json` in light mode

### State Persistence (Always Preserved)

**Critical**: State persistence is **ALWAYS** performed regardless of `light_artifacts` flag:

- `state_store.save_state()` is called unconditionally
- Portfolio state must persist across cycles for correct operation
- State includes: allocations, positions, drawdown tracker, timestamps

**Locations**:
- Line ~691: State before cycle (snapshot)
- Line ~806: State before cycle (if no previous state)
- Line ~1635: State after cycle (updated state)

### Required Artifacts (Always Written)

These artifacts are **always written** even in light mode because they're required for final results:

1. **`raw_returns.json`**: Required for evaluation to work
2. **`rebalance_execution.json`**: Required for trade collection in Layer 2 backtests

### Threading Through Call Chain

The flag is threaded through:

```
run_layer2_backtest.py
  └─> run_portfolio_cycle(light_artifacts=...)
       ├─> run_batch_evaluation(light_artifacts=...)
       │    ├─> evaluate_strategy(light_artifacts=...)
       │    │    └─> research_engine.run_backtest(light_artifacts=...)
       │    └─> _persist_batch_artifacts(light_artifacts=...)
       │         └─> persist_evaluation(light_artifacts=...)
       ├─> persist_allocation(light_artifacts=...)
       ├─> persist_rebalance_plan(light_artifacts=...)
       ├─> persist_rebalance_execution(light_artifacts=...)  # Always writes
       └─> persist_cycle_result(light_artifacts=...)
```

## Testing

### Full Mode (Default)
```bash
python3 scripts/run_layer2_backtest.py
```
- All artifacts written
- Full traceability

### Light Mode
```bash
python3 scripts/run_layer2_backtest.py --light-artifacts
```
- Only essential artifacts written
- State always persisted
- Execution artifacts always written (for trade collection)
- Raw returns always written (for evaluation)

### Determinism Verification
```bash
python3 scripts/verify_layer2_determinism.py
```
- Compares full vs light mode results
- Should produce identical final metrics

## Performance Impact

**Expected Speedup**: 5-10x reduction in I/O operations

**Artifacts Skipped in Light Mode**:
- `allocation.json` (per cycle)
- `rebalance_plan.json` (per cycle)
- `cycle_result.json` (per cycle)
- `evaluation_report.json` (per strategy)
- `batch_summary.json` (per batch)
- `results_index.json` (per batch)
- `metrics.json` (per backtest run)
- `run_metadata.json` (per backtest run)

**Artifacts Always Written**:
- `raw_returns.json` (required for evaluation)
- `rebalance_execution.json` (required for trade collection)
- Portfolio state (required for cycle continuity)

## Constraints Preserved

✅ **State persistence**: Always performed  
✅ **Determinism**: Computation unchanged, only I/O differs  
✅ **Trade collection**: Works in both modes (execution artifacts always written)  
✅ **Evaluation**: Works in both modes (raw returns always written)  
✅ **Backward compatibility**: Default behavior unchanged (light_artifacts=False)

