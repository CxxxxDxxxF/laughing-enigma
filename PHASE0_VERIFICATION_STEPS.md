# Phase 0 Verification Steps

**Status**: Fix applied, pending verification

---

## Fix Summary

**Architectural Bug Fixed**: Prices were used for execution but not persisted for equity calculation.

**Solution**:
- Added `last_price_by_instrument` to `PaperExecutionEngine` to store execution prices
- Updated equity calculation to use execution-derived prices as single source of truth
- Added hard failure if positions exist but prices don't

---

## Verification Process

**Run a minimum 5-cycle rehearsal with price movement.**

Then verify all three conditions below.

### 1. Unrealized PnL Must Move

```bash
jq '.equity.unrealized_pnl' artifacts/latest.json
```

**Expected**:
- Non-zero
- Changes between cycles if price changes

**If this stays 0**: Prices are still not flowing correctly.

### 2. Equity Must Diverge from Initial Equity

```bash
jq '.equity.total, .equity.initial' artifacts/latest.json
```

**Expected**:
- `total != initial`

**If equal**: Mark-to-market path is broken somewhere upstream.

### 3. Price Source Must Be Execution-Derived

```bash
jq '.debug.last_price_by_instrument' artifacts/latest.json
```

**Expected**:
- Contains every instrument with an open position
- Values match recent execution prices, not static config values

**If empty while positions exist**: The hard failure should already be triggering. If it is not, that is a bug.

---

## Alternative Verification (Using Cycle Artifacts)

If using cycle artifacts directly:

```bash
jq '.summary | {equity, realized_pnl, unrealized_pnl}' \
  artifacts_phase0_verify/runs/cycle_*/cycle_result.json
```

**Expected**: Non-zero values by cycle 2 or 3.

Specifically:
- `unrealized_pnl ≠ 0`
- `equity ≠ initial equity`

---

## Architectural Assessment

**Tell-it-like-it-is verdict:**

- **This was a core system flaw, not a cosmetic bug**
  - Prices were used in execution but lost before equity calculation
  - Each subsystem worked independently, but the system as a whole lied
  
- **Your fix establishes a single source of truth for prices**
  - Execution prices are stored in `last_price_by_instrument`
  - Equity calculation uses execution-derived prices
  
- **The hard failure is a professional-grade decision**
  - Refuses to calculate equity with missing prices
  - Prevents silent failures that would produce fake results
  
- **Most retail trading systems silently fake equity. Yours now refuses to lie.**
  - That puts you ahead of many funded-account codebases.

---

## Phase 0 Completion Criteria

**Phase 0 is done only when ALL THREE conditions are true:**

1. ✅ Unrealized PnL ≠ 0 (changes with price movement)
2. ✅ Equity ≠ initial equity (mark-to-market working)
3. ✅ Price source is execution-derived (not static config)

---

## What Comes Next (After Phase 0 Passes)

**Do not move forward until equity moves.**

Once verified, the next phases are:

### Phase 1: PnL Continuity Across Session Boundaries
- Restart engine, equity must resume correctly
- Positions and PnL persist across sessions

### Phase 2: Multi-Instrument Price Coherence
- One bad price cannot poison global equity
- Price validation across instruments

### Phase 3: Slippage and Partial Fills Reflected in Mark-to-Market
- Real execution costs affect equity
- Partial fills properly accounted

---

**Last Updated**: 2025-12-21  
**Status**: Fix applied, verification pending

