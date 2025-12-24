# Phase 0 Fix: Price Updates Per Cycle

## Problem Found

**Where equity should change**: When price moves from 150 → 149 → 148...  
**Where it doesn't**: `execution_config.price_by_strategy_or_instrument` stays at 150.0  
**What variable is wrong**: Prices are not updated per cycle from `price_series`

## Root Cause

`scripts/backtest_runner.py` loops through cycles but never updates execution prices from `evaluation_config.price_series`.

## Fix Applied

**File**: `scripts/backtest_runner.py`  
**Location**: Inside the cycle loop, before `run_portfolio_cycle`

**Change**: Update `execution_config.price_by_strategy_or_instrument` from `price_series[i]` for each cycle.

**Minimal change**: Only updates prices. No other modifications.

## Code Added

```python
# Update execution prices from price_series if available
cycle_config = config
price_series = config.evaluation_config.price_series
if price_series and i < len(price_series):
    current_price = price_series[i]
    # Create updated config with current price
    config_dict = config.to_dict()
    execution_config = config_dict.get("execution_config", {}).copy()
    price_map = execution_config.get("price_by_strategy_or_instrument", {}).copy()
    
    # Update all prices to current_price
    for key in price_map.keys():
        price_map[key] = current_price
    execution_config["price_by_strategy_or_instrument"] = price_map
    config_dict["execution_config"] = execution_config
    
    cycle_config = PortfolioCycleConfig.from_dict(config_dict)
    print(f"Price updated: ${current_price:.2f}")
```

Then use `cycle_config` instead of `config` in `run_portfolio_cycle()`.

## Testing Required

1. Run backtest with price series that changes
2. Verify prices update per cycle in logs
3. Verify equity changes as positions are marked-to-market
4. Verify equity curve is not flat

## Status

✅ Fix applied  
⏳ Awaiting test results

---

**Next**: If evaluation still fails (separate issue), trace that next. But price update was the root cause of equity not moving.

