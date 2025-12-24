# Layer 2 Determinism Verification

## Overview

The `verify_layer2_determinism.py` script verifies that the `--light-artifacts` optimization is a pure I/O optimization that does not change computation, state evolution, or final results.

## What It Does

1. **Runs Layer 2 backtest in FULL mode** (all artifacts written)
2. **Runs Layer 2 backtest in LIGHT mode** (`--light-artifacts` flag)
3. **Compares final results** from both runs
4. **Reports success or failure** with detailed differences

## Usage

```bash
python scripts/verify_layer2_determinism.py
```

## What Gets Compared

The script compares all fields in `LAYER2_BACKTEST_RESULTS.json`:

- **Integers**: Must match exactly (trade_count, daily_loss_breaches, dominant_trade_idx)
- **Floats**: Must match within tolerance (1e-10) or be both Infinity/NaN
  - net_pnl, gross_pnl, expectancy_per_trade
  - win_rate, avg_win, avg_loss, profit_factor
  - max_drawdown, max_drawdown_pct
  - execution_cost_impact_pct, daily_loss_breach_frequency_pct
- **Booleans**: Must match exactly (single_trade_dominance, costs_materially_reduced)
- **Strings**: Must match exactly (instrument, date_range)
- **Lists**: Must match in order (anomalies)

## Comparison Rules

### Float Tolerance
- Regular floats: `abs(full - light) <= 1e-10`
- Infinity: Both must be Infinity (or both -Infinity)
- NaN: Both must be NaN

### Special Cases
- JSON "Infinity" strings are normalized to `float('inf')` for comparison
- Dictionary key order doesn't matter
- List order matters (must match)

## Output

### Success
```
✅ SUCCESS: Results are IDENTICAL

All metrics match between full mode and --light-artifacts mode.
This confirms that --light-artifacts is a pure I/O optimization
and does not change computation, state evolution, or final results.
```

### Failure
```
❌ FAILURE: Found N difference(s)

Differences:
--------------------------------------------------------------------------------

1. Field: ES.net_pnl
   Full mode:  12960.975027857763
   Light mode: 12960.975027857764
   Reason: Mismatch: diff=1.00e-12, full=12960.975027857763, light=12960.975027857764
```

## Exit Codes

- `0`: Verification passed (results are identical)
- `1`: Verification failed (results differ)

## Notes

- The script runs both backtests sequentially (not in parallel)
- Temporary result files are created with suffixes `_full` and `_light`
- On success, temporary files are cleaned up
- On failure, temporary files are preserved for inspection
- The script filters output to show only key progress lines

## Integration

This script can be integrated into CI/CD pipelines:

```bash
# In CI script
python scripts/verify_layer2_determinism.py || exit 1
```

## Troubleshooting

If verification fails:

1. Check the differences reported
2. Inspect the temporary result files:
   - `LAYER2_BACKTEST_RESULTS_full.json`
   - `LAYER2_BACKTEST_RESULTS_light.json`
3. Verify that state persistence is working correctly
4. Check for any non-deterministic operations in the code

