# Determinism Verification Fixes

## P0 Fixes (Critical - Blocking)

### Fix 1: Store Raw Returns in BacktestResult

**Problem**: Raw returns are only persisted to artifacts, but evaluation needs them in-memory for light mode.

**Solution**: Add `raw_returns` field to `BacktestResult` and populate it in `run_backtest()`.

**Files**:
- `src/engines/base.py` - Add `raw_returns` to `BacktestResult`
- `src/engines/simple.py` - Populate `raw_returns` in `run_backtest()`
- `src/evaluation/evaluator.py` - Use `backtest_result.raw_returns` instead of artifact retrieval

### Fix 2: Store Execution Result in CycleResult

**Problem**: `CycleResult` only stores `rebalance_execution_id` (string), not the actual `RebalanceExecutionResult` object with fills.

**Solution**: Add optional `execution_result` field to `CycleResult` to store in-memory execution data.

**Files**:
- `src/lifecycle/runner.py` - Add `execution_result` to `CycleResult`, populate it in `run_portfolio_cycle()`
- `scripts/run_layer2_backtest.py` - Extract fills from `cycle_result.execution_result` instead of artifacts

### Fix 3: Fix Trade Collection to Use In-Memory Data

**Problem**: Trade collection reads from artifact files that don't exist in light mode.

**Solution**: Extract fills directly from `CycleResult.execution_result.intent_results`.

**Files**:
- `scripts/run_layer2_backtest.py` - Replace artifact file reading with in-memory extraction

## P1 Improvements (High Priority)

### Fix 4: Improve Float Comparison

**Problem**: Absolute tolerance (1e-10) is too strict for accumulated values.

**Solution**: Use relative tolerance for large values, absolute for small values.

**Files**:
- `scripts/verify_layer2_determinism.py` - Update `compare_floats()` function

### Fix 5: Add Cycle-by-Cycle Consistency Checks

**Problem**: Only final aggregated metrics are compared, intermediate state divergence may be masked.

**Solution**: Compare equity series cycle-by-cycle and verify cycle counts/statuses match.

**Files**:
- `scripts/verify_layer2_determinism.py` - Add intermediate state comparison

### Fix 6: Ensure Deterministic Execution Ordering

**Problem**: `glob()` has undefined ordering, may cause different trade matching.

**Solution**: Sort cycle results by cycle_id before processing.

**Files**:
- `scripts/run_layer2_backtest.py` - Sort cycle results deterministically

## Implementation Order

1. Fix 1 (Raw Returns) - Required for evaluation to work in light mode
2. Fix 2 (Execution Result) - Required for trade collection
3. Fix 3 (Trade Collection) - Required for verification to work
4. Fix 4 (Float Comparison) - Improves verification accuracy
5. Fix 5 (Cycle Checks) - Strengthens guarantees
6. Fix 6 (Ordering) - Ensures determinism

