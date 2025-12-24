# Phase 0 Equity Verification Report

**Date**: 2025-12-21  
**Status**: ✅ **COMPLETE - Fix Applied and Verified**

## Executive Summary

Phase 0 equity verification was executed using systematic artifact-based verification. One condition passed, two conditions failed. The failures indicate that while execution-derived prices are stored for new trades, existing positions are not being marked to market when prices change between cycles.

## Verification Methodology

**Script**: `scripts/verify_phase0_equity.py`  
**Artifacts**: `artifacts_phase0_equity_verify/`  
**Cycles Run**: 5 cycles with price series [150.0, 149.0, 148.0, 147.0, 146.0]  
**Approach**: Systematic artifact extraction and evidence-based verification

## Verification Results

### ✅ Condition 1: Unrealized PnL Must Move
**Status**: ❌ **FAILED**

**Evidence**:
```json
{
  "unrealized_pnl_by_cycle": [0.0, 0.0, 0.0, 0.0, 0.0],
  "has_non_zero": false,
  "values_change": false
}
```

**Analysis**:
- Positions are created in cycle 1 (2 fills at $150.00)
- Cycles 2-5 have no new trades (rebalance decides to hold)
- Unrealized PnL remains 0.0 despite price decreasing from $150 → $149 → $148 → $147 → $146
- **Root Cause**: Existing positions are not being marked to market with current cycle prices

### ✅ Condition 2: Equity Must Diverge from Initial
**Status**: ❌ **FAILED**

**Evidence**:
```json
{
  "initial_equity": 50000.0,
  "equity_by_cycle": [50000.0, 50000.0, 50000.0, 50000.0, 50000.0],
  "diverges": false,
  "max_divergence": 0.0
}
```

**Analysis**:
- Equity remains constant at $50,000 across all cycles
- Expected: Equity should decrease as prices fall (positions should show unrealized loss)
- **Root Cause**: Same as Condition 1 - positions not marked to market

### ✅ Condition 3: Price Source Must Be Execution-Derived
**Status**: ✅ **PASSED**

**Evidence**:
```json
{
  "fills_with_execution_prices": 2,
  "fill_price_evidence": [
    {
      "cycle_id": "phase0_verify_20251222_170000",
      "fill_price": 150.0,
      "instrument": "AAPL",
      "quantity": 166.0
    }
  ],
  "has_unrealized_pnl": false,
  "execution_derived_prices_confirmed": true
}
```

**Analysis**:
- Fills contain execution prices ($150.00)
- Prices match the cycle's execution config price
- **Conclusion**: Execution-derived prices are correctly stored for new trades

## Root Cause Analysis

### The Problem

The Phase 0 fix addressed price persistence for **new trades**, but did not address **mark-to-market for existing positions** when no new trades occur.

**Scenario**:
1. Cycle 1: Positions created at $150.00 (fills executed, prices stored)
2. Cycle 2: No new trades (rebalance decides to hold), price is now $149.00
3. **Issue**: Equity calculation doesn't mark existing positions to market with cycle 2's price

### Why This Happens

When no new trades occur:
- Execution engine doesn't execute orders
- `last_price_by_instrument` may not be updated with current cycle's price
- Equity calculation may not have access to current cycle's price for mark-to-market
- Positions remain valued at their cost basis, not current market price

### Expected Behavior

When positions exist and prices change:
- Equity calculation should use current cycle's price (from config or execution engine)
- Existing positions should be marked to market: `unrealized_pnl = (current_price - cost_basis) * quantity`
- Equity should reflect: `equity = initial_cash + realized_pnl + unrealized_pnl`

## Code Path Investigation Needed

**Location**: `src/lifecycle/runner.py` lines 1586-1609

**Questions**:
1. When no new trades occur, does `execution_engine.last_price_by_instrument` contain current cycle's price?
2. Does the fallback to `config.execution_config.price_by_strategy_or_instrument` work correctly?
3. Is `calculate_portfolio_equity()` being called with the correct `current_prices` dict?

**Next Steps**:
1. Add debug logging to equity calculation path
2. Verify `current_prices` dict is populated correctly when no new trades occur
3. Ensure fallback to config prices works for mark-to-market

## Impact Assessment

**Severity**: 🔴 **HIGH**

**Why This Matters**:
- Equity calculation is incorrect when positions are held across cycles
- Daily loss limits may not trigger correctly (equity doesn't reflect unrealized losses)
- Trailing drawdown calculations will be wrong
- System will show false equity values in LIVE_DRY and LIVE modes

**This is a critical bug for funded account trading.**

## Verification Artifacts

All verification artifacts are stored in:
- `artifacts_phase0_equity_verify/`
- Cycle results: `runs/phase0_verify_*/cycle_result.json`
- Execution results: `runs/phase0_verify_*_exec/rebalance_execution.json`

## Fix Implementation

### Solution: Per-Cycle Market Price Updates

**Files Modified**:
- `src/execution/paper_engine.py`: Added `update_market_prices()` method
- `src/lifecycle/runner.py`: 
  - Load positions from previous cycle's state into execution engine
  - Call `update_market_prices()` after execution to store current cycle prices
  - Use stored prices for mark-to-market calculation

**Implementation Details**:

1. **Added `update_market_prices()` to PaperExecutionEngine**:
   - Updates `last_price_by_instrument` for all instruments with positions
   - Called every cycle, independent of trading activity
   - Hard fails if positions exist but prices are missing

2. **Position Persistence**:
   - Positions from previous cycles are loaded into execution engine before execution
   - Ensures positions persist across cycles for mark-to-market

3. **Price Update Flow**:
   - After execution completes, `update_market_prices()` is called with current cycle's prices
   - Prices are stored in `execution_engine.last_price_by_instrument`
   - Equity calculation uses stored prices for mark-to-market

**Key Insight**: Prices must be updated every cycle, not just when fills occur. This ensures existing positions are marked to market even when no new trades happen.

## Post-Fix Verification Results

**Re-verification Date**: 2025-12-21  
**Artifacts**: `artifacts_phase0_equity_verify_fixed/`

### ✅ Condition 1: Unrealized PnL Must Move
**Status**: ✅ **PASSED**

**Evidence**:
```json
{
  "unrealized_pnl_by_cycle": [0.0, -332.0, -664.0, -996.0, -1328.0],
  "has_non_zero": true,
  "values_change": true
}
```

**Analysis**:
- Cycle 1: No unrealized PnL (positions just created at $150.00)
- Cycle 2: Unrealized PnL = -$332.00 (price dropped to $149.00)
- Cycle 3: Unrealized PnL = -$664.00 (price dropped to $148.00)
- Cycle 4: Unrealized PnL = -$996.00 (price dropped to $147.00)
- Cycle 5: Unrealized PnL = -$1,328.00 (price dropped to $146.00)
- **Result**: Unrealized PnL correctly moves with price changes, even when no new trades occur

### ✅ Condition 2: Equity Must Diverge from Initial
**Status**: ✅ **PASSED**

**Evidence**:
```json
{
  "initial_equity": 50000.0,
  "equity_by_cycle": [50000.0, 49668.0, 49336.0, 49004.0, 48672.0],
  "diverges": true,
  "max_divergence": 1328.0
}
```

**Analysis**:
- Cycle 1: Equity = $50,000.00 (initial)
- Cycle 2: Equity = $49,668.00 (diverged by -$332.00)
- Cycle 3: Equity = $49,336.00 (diverged by -$664.00)
- Cycle 4: Equity = $49,004.00 (diverged by -$996.00)
- Cycle 5: Equity = $48,672.00 (diverged by -$1,328.00)
- **Result**: Equity correctly diverges from initial as prices change

### ✅ Condition 3: Price Source Must Be Execution-Derived
**Status**: ✅ **PASSED**

**Evidence**:
```json
{
  "fills_with_execution_prices": 2,
  "fill_price_evidence": [
    {
      "cycle_id": "phase0_verify_20251222_170000",
      "fill_price": 150.0,
      "instrument": "AAPL",
      "quantity": 166.0
    }
  ],
  "has_unrealized_pnl": true,
  "execution_derived_prices_confirmed": true
}
```

**Analysis**:
- Fills contain execution prices ($150.00)
- Prices stored via `update_market_prices()` are used for mark-to-market
- **Result**: Price source is execution-derived (via engine's stored prices)

## Regression Test

**Test File**: `tests/test_phase0_equity_movement.py`  
**Test Method**: `test_mark_to_market_without_new_trades`

**Coverage**:
- Position opened in cycle 1 at $100.00
- No trades in cycle 2, price changes to $110.00
- Asserts unrealized PnL ≠ 0
- Asserts equity changes
- Verifies no dependency on new fills

**Status**: ✅ **PASSING**

This test locks the mark-to-market behavior to prevent future regression.

## Conclusion

**Phase 0 Equity Verification**: ✅ **COMPLETE**

All three conditions now pass. The fix ensures that:
1. Positions are marked to market every cycle using current cycle prices
2. Unrealized PnL correctly reflects price changes, even when no new trades occur
3. Equity calculation uses execution-derived prices (stored via `update_market_prices()`)

**Phase 0 equity movement verification is complete and locked by regression test.**

