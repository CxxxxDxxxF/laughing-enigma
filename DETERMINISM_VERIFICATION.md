# Layer 2 Determinism Verification

## Purpose

This document describes the determinism verification system for the Layer 2 backtest optimization (`--light-artifacts` flag).

## Goal

Prove that `--light-artifacts` is a **pure I/O optimization** that:
- ✅ Does NOT change computation
- ✅ Does NOT change state evolution  
- ✅ Does NOT change final results
- ✅ Only skips per-cycle artifact writes

## Verification Script

**Location**: `scripts/verify_layer2_determinism.py`

**Usage**:
```bash
python scripts/verify_layer2_determinism.py
```

## What Gets Verified

The script compares the final output artifact: **`LAYER2_BACKTEST_RESULTS.json`**

This file contains all metrics used for evaluation and pass/fail decisions:

### Per-Instrument Metrics (ES, NQ, CL)

1. **Trade Metrics**:
   - `trade_count` (int) - Must match exactly
   - `expectancy_per_trade` (float) - Must match within tolerance
   - `win_rate` (float) - Must match within tolerance
   - `avg_win` (float) - Must match within tolerance
   - `avg_loss` (float) - Must match within tolerance
   - `profit_factor` (float or Infinity) - Must match exactly or both Infinity

2. **PnL Metrics**:
   - `net_pnl` (float) - Must match within tolerance
   - `gross_pnl` (float) - Must match within tolerance
   - `total_execution_costs` (float) - Must match within tolerance
   - `execution_cost_impact_pct` (float) - Must match within tolerance

3. **Risk Metrics**:
   - `max_drawdown` (float) - Must match within tolerance
   - `max_drawdown_pct` (float) - Must match within tolerance
   - `daily_loss_breaches` (int) - Must match exactly
   - `daily_loss_breach_frequency_pct` (float) - Must match within tolerance

4. **Boolean Flags**:
   - `single_trade_dominance` (bool) - Must match exactly
   - `costs_materially_reduced` (bool) - Must match exactly

5. **Other Fields**:
   - `instrument` (string) - Must match exactly
   - `date_range` (string) - Must match exactly
   - `dominant_trade_idx` (int or None) - Must match exactly
   - `anomalies` (list) - Must match in order

## Comparison Rules

### Float Tolerance
- **Tolerance**: `1e-10` (0.0000000001)
- **Rule**: `abs(full_value - light_value) <= 1e-10`
- **Rationale**: Accounts for floating-point precision differences in computation order

### Special Cases

1. **Infinity Values**:
   - Both must be `float('inf')` or both must be `float('-inf')`
   - JSON string "Infinity"/"inf" are normalized to `float('inf')` for comparison

2. **NaN Values**:
   - Both must be `math.nan`
   - Comparison uses `math.isnan()`

3. **Dictionary Keys**:
   - Key order doesn't matter
   - All keys must be present in both

4. **List Order**:
   - Order matters (must match)

5. **Integers and Booleans**:
   - Must match exactly (no tolerance)

## Verification Process

1. **Run Full Mode**:
   - Execute `python scripts/run_layer2_backtest.py`
   - Save results to `LAYER2_BACKTEST_RESULTS_full.json`

2. **Run Light Mode**:
   - Execute `python scripts/run_layer2_backtest.py --light-artifacts`
   - Save results to `LAYER2_BACKTEST_RESULTS_light.json`

3. **Compare Results**:
   - Load both JSON files
   - Recursively compare all fields
   - Report any differences

4. **Report**:
   - ✅ Success: All fields match
   - ❌ Failure: Differences found with detailed report

## Success Criteria

Verification **PASSES** if:
- All integer fields match exactly
- All float fields match within tolerance (1e-10)
- All boolean fields match exactly
- All string fields match exactly
- All list fields match in order
- Infinity/NaN values handled correctly

Verification **FAILS** if:
- Any field differs beyond tolerance
- Any type mismatch
- Any missing keys
- Any list length mismatch

## Failure Handling

On failure:
1. **Detailed diff report** showing:
   - Field path (e.g., `ES.net_pnl`)
   - Full mode value
   - Light mode value
   - Reason for mismatch

2. **Preserved result files**:
   - `LAYER2_BACKTEST_RESULTS_full.json`
   - `LAYER2_BACKTEST_RESULTS_light.json`
   - Available for manual inspection

3. **Exit code**: `1` (failure)

## Integration

### Manual Verification
```bash
python scripts/verify_layer2_determinism.py
```

### CI/CD Integration
```yaml
# Example GitHub Actions
- name: Verify determinism
  run: python scripts/verify_layer2_determinism.py
```

### Pre-commit Hook
```bash
# .git/hooks/pre-commit
python scripts/verify_layer2_determinism.py || exit 1
```

## Expected Behavior

When `--light-artifacts` is working correctly:
- ✅ Verification should **PASS**
- ✅ Results should be **IDENTICAL** (within float tolerance)
- ✅ No differences should be reported

If verification fails:
- ❌ Investigation required
- ❌ Optimization may have introduced a bug
- ❌ Results should not be trusted until fixed

## Maintenance

### When to Re-run Verification

1. **After any changes to**:
   - Cycle execution logic
   - State persistence
   - PnL calculation
   - Trade matching logic
   - Any computation that affects final results

2. **Before releasing**:
   - Performance optimizations
   - Code refactoring
   - Bug fixes that touch core logic

3. **Periodically**:
   - As part of CI/CD pipeline
   - Before major releases

### Updating Tolerance

If verification fails due to legitimate floating-point differences:
- **DO NOT** increase tolerance without investigation
- **DO** investigate why results differ
- **ONLY** increase tolerance if:
  - Difference is truly due to computation order
  - Difference is negligible (< 1e-8)
  - All other fields match exactly

## Troubleshooting

### Common Issues

1. **"Type mismatch" errors**:
   - Check JSON serialization/deserialization
   - Verify no type coercion in results

2. **"Infinity mismatch" errors**:
   - Check how Infinity is serialized in JSON
   - Verify normalization function handles all cases

3. **"Float mismatch" errors**:
   - Check if difference is within tolerance
   - Investigate computation order differences
   - Verify no non-deterministic operations

4. **"Key missing" errors**:
   - Check if both runs complete successfully
   - Verify no early exits or errors

## Conclusion

This verification system provides **strong guarantees** that the `--light-artifacts` optimization is safe to use. A passing verification confirms that:

- The optimization is purely I/O-based
- Computation remains deterministic
- Results are identical (within float tolerance)
- The optimization can be used with confidence

