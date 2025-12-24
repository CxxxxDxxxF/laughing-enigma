# Phase 0 Verification Criteria

**Phase 0 is NOT "code changed".**

**Phase 0 is only complete if ALL THREE are true in the same cycle artifact:**

1. ✅ **positions contain non-zero quantity**
   - At least one position has quantity != 0

2. ✅ **realized_pnl or unrealized_pnl ≠ 0**
   - Either realized_pnl != 0 OR unrealized_pnl != 0

3. ✅ **equity ≠ initial equity**
   - equity != initial_capital (e.g., $50,000)

---

## Verification Commands

### Option 1: Cycle Artifacts

After running a backtest, verify with:

```bash
jq '.summary | {equity, realized_pnl, unrealized_pnl}' \
  artifacts_phase0_verify/runs/cycle_*/cycle_result.json
```

**Expected**: Non-zero values by cycle 2 or 3

### Option 2: Evidence Report (if available)

```bash
jq '.equity.unrealized_pnl' artifacts/latest.json
jq '.equity.total, .equity.initial' artifacts/latest.json  
jq '.debug.last_price_by_instrument' artifacts/latest.json
```

See `PHASE0_VERIFICATION_STEPS.md` for detailed verification steps.

---

## Current Status

- **Fix applied**: Use `execution_engine.positions` after execution completes
- **Verification**: PENDING - Need to run test and check artifacts

---

## If Verification Fails

If equity still doesn't move after this change:

→ Need to trace one level deeper (engine may not be applying PnL correctly)

But based on artifacts showing positions with realized PnL, this should work.

---

**Phase 0A (price updates)**: ✅ Complete  
**Phase 0B (equity calculation exists)**: ✅ Complete  
**Phase 0C (correct position source)**: ⏳ Pending verification

