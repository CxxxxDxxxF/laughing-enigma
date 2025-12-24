# Phase 0 Trace Findings

**Date**: 2025-12-21  
**Status**: IN PROGRESS

---

## Issue Found: Price Series Not Connected to Execution

### Observation

**STEP 1: PRICE INPUT**

- `execution_config.price_by_strategy_or_instrument`: Static `{'AAPL': 150.0}` for all cycles
- `evaluation_config.price_series`: `[150.0, 149.0, 148.0, ...]` (changes per cycle)

**The price_series exists but is NOT wired into execution_config per cycle.**

### The Broken Link

**Where equity should change**: When price moves from 150 → 149 → 148...

**Where it doesn't**: `execution_config.price_by_strategy_or_instrument` stays at 150.0

**What variable is wrong or missing**: The `backtest_runner.py` script should update `execution_config.price_by_strategy_or_instrument` from `price_series[cycle_index]` but it doesn't.

---

## Current State

1. ✅ Price series exists in config (10 prices: 150 → 141)
2. ❌ Execution config prices are static (always 150.0)
3. ❌ Prices don't update per cycle
4. ❌ Even if positions exist, unrealized PnL won't change (price never changes)
5. ❌ Equity stays flat

---

## Root Cause

**`scripts/backtest_runner.py` does not update execution prices per cycle.**

It should do something like:

```python
for i, cycle_timestamp in enumerate(cycle_timestamps):
    # Update execution config with price from series
    if price_series and i < len(price_series):
        current_price = price_series[i]
        config.execution_config["price_by_strategy_or_instrument"] = {
            instrument: current_price for instrument in ...
        }
    
    # Run cycle with updated price
    result = run_portfolio_cycle(config=config, ...)
```

But it doesn't.

---

## Additional Issue: Evaluation Fails

Before we even get to equity calculation, evaluation fails with:

```
Failed to retrieve raw returns for run test_strategy_v1_20251221_215914
```

This suggests the strategy evaluation step is also broken, but that's a separate issue from the price update problem.

---

## Fix Applied

**Fixed in `scripts/backtest_runner.py`**:

Added price update per cycle from `price_series`:

```python
# Update execution prices from price_series if available
cycle_config = config
price_series = config.evaluation_config.price_series
if price_series and i < len(price_series):
    current_price = price_series[i]
    # Update execution_config.price_by_strategy_or_instrument
    # ... (code creates new config with updated prices)
    cycle_config = PortfolioCycleConfig.from_dict(config_dict)
```

**Minimal change**: Only updates prices per cycle. No other modifications.

---

## Next Steps

1. ✅ **Fixed price updates per cycle** in `backtest_runner.py`
2. **Test**: Run trace again to verify prices update
3. **If evaluation still fails**, that's the next broken link to fix
4. **If evaluation passes**, verify equity moves with price changes

---

**Status**: Fix applied, ready for testing

