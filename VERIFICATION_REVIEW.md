# Determinism Verification Review

## Executive Summary

The verification approach has a **critical gap** that will cause false negatives: trade collection depends on execution artifacts that are skipped in light mode. Additionally, several design choices need refinement for production-grade determinism verification.

---

## 1. Soundness of Verification Approach

### ✅ Strengths

- **Final results focus**: Comparing `LAYER2_BACKTEST_RESULTS.json` is appropriate since it contains all evaluation metrics
- **Comprehensive field coverage**: All metrics (PnL, trade counts, drawdowns, flags) are compared
- **Recursive comparison**: Handles nested structures correctly

### ❌ Critical Gap: Trade Collection Dependency

**Issue**: The Layer 2 backtest collects trades by reading execution artifacts:

```python
# scripts/run_layer2_backtest.py:497
exec_files = list(artifacts_dir.glob("runs/*_exec/rebalance_execution.json"))
```

**Problem**: In `--light-artifacts` mode, these files are **not written**, so:
- `exec_files` will be empty
- `trades` list will be empty
- Trade metrics will be incorrect (all zeros)
- Verification will **fail** even though computation is identical

**Impact**: **FALSE NEGATIVE** - verification fails despite correct computation

**Fix Required**: Trade collection must use in-memory execution engine state, not artifact files.

### ⚠️ Hidden Failure Modes

1. **Intermediate state divergence**: If state evolves differently but final metrics converge, verification passes incorrectly
   - Example: Different cycle-by-cycle equity curves that sum to same final PnL
   - Risk: State corruption masked by aggregation

2. **Early exit differences**: If one mode halts early but final JSON still exists, comparison proceeds
   - Example: Full mode halts at cycle 100, light mode completes all 365 cycles
   - Both produce JSON, but results are incomparable

3. **Error handling divergence**: Different exception paths might produce same final metrics
   - Example: Full mode catches exception and continues, light mode doesn't
   - Both produce same final numbers, but execution paths differ

4. **Trade ordering sensitivity**: If trade matching logic depends on artifact read order, results may differ
   - Current code uses `glob()` which has undefined ordering
   - Risk: Different file system order → different trade matching → different metrics

---

## 2. Comparison Rules Critique

### Float Tolerance (1e-10)

**Assessment**: **Too strict for some operations, appropriate for others**

**Issues**:
- **Accumulation errors**: Summing 365 daily equity values can accumulate errors > 1e-10
  - Example: `sum([50000.0 + i*0.001 for i in range(365)])` may have errors ~1e-8
- **Division operations**: `net_pnl / trade_count` can introduce precision loss
- **Percentage calculations**: `(drawdown / initial_capital) * 100.0` amplifies errors

**Recommendation**: 
- Use **relative tolerance** for large values: `abs(a - b) <= max(abs(a), abs(b)) * 1e-9`
- Use **absolute tolerance** for small values: `abs(a - b) <= 1e-10`
- Or use **ULP-based comparison** for production-grade verification

**Example**:
```python
def compare_floats_robust(a: float, b: float, tol: float = 1e-10) -> bool:
    if abs(a) < 1.0 and abs(b) < 1.0:
        return abs(a - b) <= tol  # Absolute for small values
    else:
        return abs(a - b) <= max(abs(a), abs(b)) * 1e-9  # Relative for large
```

### Infinity / NaN Handling

**Assessment**: **Mostly correct, but missing edge cases**

**Issues**:
1. **String normalization**: Converting "infinity" strings to `float('inf')` is correct, but:
   - What if JSON has `null` for Infinity? (some encoders do this)
   - What if JSON has `"Inf"` (abbreviated)?
   
2. **NaN comparison**: `math.isnan()` comparison is correct, but:
   - NaN != NaN in Python, so direct comparison would fail
   - Current implementation handles this correctly

3. **Mixed Infinity/NaN**: What if one is Infinity and other is NaN?
   - Current code handles this (separate checks)

**Recommendation**: Add explicit handling for `null` values in JSON that represent Infinity.

### List Order Sensitivity

**Assessment**: **Correct for `anomalies`, but potential issue for trade data**

**Current behavior**: Lists are compared in order (line 112)

**Issue**: If `anomalies` list order differs but contents are same, verification fails
- Example: `[error1, error2]` vs `[error2, error1]` → failure
- This may be intentional (order matters), but should be documented

**Trade data**: If trade collection produces different order, metrics may differ
- Example: Round-trip matching depends on fill order
- Current code uses `glob()` which has undefined order

**Recommendation**: 
- Document that list order matters (intentional)
- Or make `anomalies` comparison order-independent if order doesn't matter

### Dictionary Key Handling

**Assessment**: **Correct** - order-independent comparison is appropriate

**No issues identified** - dictionary key order handling is sound.

---

## 3. Gaps and Risks

### Computation Divergence Scenarios

1. **Floating-point operation order**:
   - Different evaluation order → different rounding errors
   - Example: `(a + b) + c` vs `a + (b + c)` can differ by ~1e-15
   - **Risk**: May pass verification if within tolerance, but computation differs

2. **Hash-based non-determinism**:
   - If any code uses `hash()` or `set()` iteration order, results may differ
   - Python 3.7+ guarantees dict order, but sets are still unordered
   - **Risk**: Different set iteration → different results → may still pass if aggregated

3. **Exception handling paths**:
   - If artifact write fails in full mode but succeeds in light mode, execution continues differently
   - **Risk**: Different code paths → same final numbers → passes verification incorrectly

### State-Related Issues

1. **Intermediate state not verified**:
   - Only final aggregated metrics are compared
   - Cycle-by-cycle state evolution is not checked
   - **Risk**: State corruption in early cycles masked by later corrections

2. **State persistence differences**:
   - Full mode writes state artifacts, light mode doesn't
   - If state loading depends on artifacts, behavior differs
   - **Current code**: State is loaded from state_store, not artifacts (good)
   - **Risk**: If state_store implementation changes, behavior may diverge

3. **Drawdown tracker state**:
   - Drawdown calculations depend on high-water-mark tracking
   - If tracker state differs, max_drawdown may be wrong
   - **Risk**: Different tracker evolution → same final max_drawdown → passes incorrectly

### Artifact Dependency Risks

1. **Trade collection from artifacts** (CRITICAL):
   - Current implementation reads trades from execution artifacts
   - In light mode, artifacts don't exist
   - **Impact**: Verification will fail with empty trades

2. **Raw returns retrieval**:
   - Evaluation retrieves `raw_returns.json` from artifacts (line 353 in evaluator.py)
   - In light mode, this file is not written
   - **Impact**: Evaluation will fail, not just verification

3. **Divergence analysis dependencies**:
   - May depend on artifacts for paper execution data
   - Need to verify all artifact dependencies are optional in light mode

---

## 4. Concrete Improvements

### Immediate Fixes (Required)

1. **Fix trade collection** (CRITICAL):
   ```python
   # Instead of reading from artifacts:
   # exec_files = list(artifacts_dir.glob("runs/*_exec/rebalance_execution.json"))
   
   # Collect trades from execution engine state:
   trades = []
   for cycle_result in cycle_results:
       if cycle_result.rebalance_execution_id:
           # Get execution result from in-memory state or cycle_result
           execution_result = get_execution_from_cycle(cycle_result)
           trades.extend(extract_fills_from_execution(execution_result))
   ```

2. **Add execution result tracking**:
   - Store execution results in `CycleResult` objects
   - Make execution data accessible without artifacts
   - Ensure `RebalanceExecutionResult` is available in memory

3. **Verify artifact dependencies**:
   - Audit all `artifact_store.retrieve()` calls
   - Ensure all required data is available in-memory in light mode
   - Add assertions that light mode doesn't depend on artifacts

### Enhanced Verification

4. **Add intermediate state checks**:
   ```python
   # Compare equity series cycle-by-cycle
   for i, (full_eq, light_eq) in enumerate(zip(full_equity_series, light_equity_series)):
       assert abs(full_eq - light_eq) <= tolerance, f"Equity differs at cycle {i}"
   ```

5. **Add execution path verification**:
   ```python
   # Compare cycle counts
   assert len(full_cycle_results) == len(light_cycle_results), "Different cycle counts"
   
   # Compare cycle statuses
   for i, (full, light) in enumerate(zip(full_cycle_results, light_cycle_results)):
       assert full.status == light.status, f"Cycle {i} status differs"
   ```

6. **Improve float comparison**:
   ```python
   def compare_floats_robust(full: float, light: float, field_path: str) -> ComparisonResult:
       # Use relative tolerance for large values
       if abs(full) > 1.0 or abs(light) > 1.0:
           rel_tol = max(abs(full), abs(light)) * 1e-9
           if abs(full - light) <= rel_tol:
               return ComparisonResult(True, full, light, field_path, "Match (relative)")
       # Use absolute tolerance for small values
       if abs(full - light) <= FLOAT_TOLERANCE:
           return ComparisonResult(True, full, light, field_path, "Match (absolute)")
       return ComparisonResult(False, full, light, field_path, "Mismatch")
   ```

7. **Add checksum verification**:
   ```python
   # Compute checksums of intermediate data structures
   full_state_checksum = compute_state_checksum(full_cycle_results)
   light_state_checksum = compute_state_checksum(light_cycle_results)
   assert full_state_checksum == light_state_checksum, "State checksums differ"
   ```

### CI/CD Enhancements

8. **Add verification to CI pipeline**:
   ```yaml
   - name: Verify determinism
     run: |
       python scripts/verify_layer2_determinism.py
       # Fail build on verification failure
   ```

9. **Add performance regression test**:
   ```python
   # Measure runtime difference
   full_time = time_backtest(light_artifacts=False)
   light_time = time_backtest(light_artifacts=True)
   speedup = full_time / light_time
   assert speedup >= 3.0, f"Expected 3x+ speedup, got {speedup:.2f}x"
   ```

10. **Add artifact size verification**:
    ```python
    # Verify light mode produces fewer artifacts
    full_artifact_count = count_artifacts("artifacts_full")
    light_artifact_count = count_artifacts("artifacts_light")
    assert light_artifact_count < full_artifact_count * 0.1, "Light mode still writes too many artifacts"
    ```

### Guardrails

11. **Add pre-commit hook**:
    ```bash
    # .git/hooks/pre-commit
    python scripts/verify_layer2_determinism.py || {
        echo "Determinism verification failed. Commit blocked."
        exit 1
    }
    ```

12. **Add runtime assertions**:
    ```python
    # In light_artifacts mode, assert no artifact writes
    if light_artifacts:
        original_store = artifact_store.store
        write_count = [0]
        def tracked_store(*args, **kwargs):
            write_count[0] += 1
            # Only allow state persistence
            if "state" not in args[0].lower():
                raise AssertionError(f"Unexpected artifact write in light mode: {args[1]}")
            return original_store(*args, **kwargs)
        artifact_store.store = tracked_store
    ```

13. **Add documentation requirements**:
    - Document all artifact dependencies
    - Document which artifacts are required vs optional
    - Add comments explaining why certain artifacts are skipped

---

## 5. Risk Assessment

### High Risk

1. **Trade collection from artifacts** - Will cause verification failure
2. **Raw returns retrieval** - Will cause evaluation failure
3. **Intermediate state divergence** - May pass verification incorrectly

### Medium Risk

1. **Float tolerance too strict** - May cause false failures
2. **Exception handling differences** - May pass verification incorrectly
3. **Trade ordering sensitivity** - May cause different results

### Low Risk

1. **List order sensitivity** - Documented behavior
2. **Infinity/NaN edge cases** - Rare, handled mostly correctly
3. **Dictionary key order** - Handled correctly

---

## 6. Recommendations Priority

### P0 (Blocking)

1. **Fix trade collection** - Verification will fail without this
2. **Fix raw returns retrieval** - Evaluation will fail without this
3. **Audit all artifact dependencies** - Ensure light mode doesn't depend on artifacts

### P1 (High Priority)

4. **Improve float comparison** - Use relative tolerance for large values
5. **Add intermediate state checks** - Verify cycle-by-cycle consistency
6. **Add execution path verification** - Compare cycle counts and statuses

### P2 (Nice to Have)

7. **Add checksum verification** - Additional safety check
8. **Add performance regression test** - Verify speedup
9. **Add CI/CD integration** - Automated verification

---

## Conclusion

The verification approach is **sound in principle** but has a **critical implementation gap** that must be fixed before it can be used. The trade collection dependency on artifacts will cause false negatives. Once fixed, the approach provides good coverage of final results, but would benefit from intermediate state verification for stronger guarantees.

**Overall Assessment**: **Good foundation, needs critical fixes before production use.**

