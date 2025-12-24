# Implementation Notes & Current Issues

**Critical**: Before validation gates can be trusted, the backtesting system must produce believable PnL dynamics.

---

## Current System Issue

**Observation**: Many backtest runs show "Final equity stays at $50,000" (unchanged from initial capital).

### Possible Causes

1. **Strategy is not actually trading**
   - Signals not being generated
   - Signals not reaching execution
   - Execution engine not processing orders

2. **Mark-to-market / PnL not applied correctly**
   - Equity calculation not including unrealized PnL
   - Positions not being marked to market
   - PnL not being accumulated

3. **Price series not connected to execution**
   - `evaluation_config.price_series` not used in execution
   - `execution_config.price_by_strategy_or_instrument` static
   - Prices not updating per cycle

### Investigation Required

Before trusting validation gate results:

1. **Verify strategy is trading**:
   - Check cycle artifacts for order submissions
   - Verify fills are being generated
   - Confirm positions are being updated

2. **Verify PnL calculation**:
   - Check that `cycle_summary["equity"]` changes over cycles
   - Verify `unrealized_pnl` is calculated correctly
   - Confirm `realized_pnl` accumulates from fills

3. **Verify price connection**:
   - Confirm price series is used during execution
   - Verify prices update per cycle
   - Check execution prices match evaluation prices

### Action Required

**Gate passes are meaningless until the simulation produces believable PnL dynamics.**

If equity never moves, you're not testing strategy robustness - you're testing a broken backtest.

---

## Strategy Design Reference

See `STRATEGY_DESIGN_TEMPLATE.md` for the reference design:
- Trend + Chop Filter + Vol Target
- Designed to pass gates through robustness, not curve-fitting
- Uses wide-basin parameters and volatility targeting

---

**Status**: BLOCKING (Phase 0)  
**Priority**: CRITICAL - Nothing else proceeds until this is fixed

**See**: `PHASE0_CRITICAL_BLOCKER.md` for the exact task and verification steps.

