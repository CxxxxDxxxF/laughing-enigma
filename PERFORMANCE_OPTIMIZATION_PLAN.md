# Layer 2 Backtest Performance Optimization Plan

## Identified Bottlenecks

### 1. Artifact Generation (LARGEST BOTTLENECK)
**Location**: Multiple files
- `src/evaluation/batch.py`: `_persist_batch_artifacts()` - writes batch_summary.json, results_index.json
- `src/evaluation/evaluator.py`: `persist_evaluation()` - writes evaluation_report.json
- `src/engines/simple.py`: `_persist_artifacts()` - writes raw_returns.json, metrics.json, run_metadata.json per strategy
- `src/execution/paper_engine.py`: `persist_session()` - writes orders.json, fills.json, positions.json, risk_limits.json, session_metadata.json
- `src/allocation/allocator.py`: `persist_allocation()` - writes allocation.json
- `src/rebalance/planner.py`: `persist_rebalance_plan()` - writes rebalance_plan.json
- `src/rebalance/executor.py`: `persist_rebalance_execution()` - writes rebalance_execution.json
- `src/lifecycle/runner.py`: `persist_cycle_result()` - writes cycle_result.json
- `src/lifecycle/state_store.py`: `save_state()` - writes state artifacts (before/after)

**Impact**: ~10-15 JSON files written per cycle × 365 cycles = 3,650-5,475 file writes
**Estimated speedup**: 5-8x by skipping per-cycle artifacts

### 2. Config Serialization (MEDIUM BOTTLENECK)
**Location**: `scripts/run_layer2_backtest.py:403-419`
- `config.to_dict()` called every cycle
- `PortfolioCycleConfig.from_dict()` called every cycle
- Deep serialization/deserialization of entire config tree

**Impact**: JSON serialization overhead × 365 cycles
**Estimated speedup**: 1.5-2x by reusing config objects

### 3. Logging Verbosity (SMALL BOTTLENECK)
**Location**: 
- `scripts/run_layer2_backtest.py:397-398` - Progress heartbeat
- `src/lifecycle/runner.py:610-611, 704-707, 830-834, 1232, 1319-1327, 1388-1389` - Debug prints

**Impact**: I/O overhead from print statements
**Estimated speedup**: 1.1-1.2x by throttling logs

### 4. Price Series Generation (ALREADY OPTIMIZED)
**Location**: `scripts/run_layer2_backtest.py:273-278`
- Already computed once and reused
- No optimization needed

### 5. State Operations (SMALL BOTTLENECK)
**Location**: `src/lifecycle/runner.py:702, 710-720, 1618-1622`
- State loaded and saved every cycle
- Necessary for correctness, but can be optimized with batching

**Impact**: File I/O for state persistence
**Estimated speedup**: 1.1x by batching (minimal, state is small)

---

## Optimization Strategy

### Phase 1: Light Artifacts Mode (5-8x speedup)
Add `--light-artifacts` flag to skip per-cycle artifact writes:
- Keep final summary artifacts (LAYER2_BACKTEST_RESULTS.json)
- Skip per-cycle JSON blobs (allocation, rebalance, execution, cycle_result)
- Skip per-strategy evaluation artifacts (raw_returns, metrics, etc.)
- Skip paper execution session artifacts (orders, fills, positions)
- Keep state persistence (required for correctness)

### Phase 2: Config Reuse (1.5-2x speedup)
- Cache base config object
- Only update mutable fields (price, cycle_id) in-place
- Avoid to_dict/from_dict round-trip

### Phase 3: Logging Throttling (1.1-1.2x speedup)
- Reduce debug prints in runner.py
- Keep progress heartbeat but make it configurable

---

## Implementation Plan

1. Add `light_artifacts` parameter to `run_portfolio_cycle()` and propagate through call chain
2. Add conditional artifact persistence in all persist functions
3. Optimize config reuse in Layer 2 backtest script
4. Reduce logging verbosity
5. Add command-line flag `--light-artifacts` to Layer 2 script

---

## Determinism Guarantees

All optimizations preserve determinism:
- Artifact skipping: Only affects I/O, not computation
- Config reuse: Same config objects, same results
- Logging: No effect on computation
- State operations: Unchanged (required for correctness)

---

## Expected Total Speedup

- Light artifacts: 5-8x
- Config reuse: 1.5-2x
- Logging: 1.1-1.2x
- **Combined: 8-19x** (conservative estimate: 5-10x)

