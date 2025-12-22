# Multi-Strategy Stub Strategy Explanation

## Purpose

Added a second strategy (`allocation_stub_v1`) to the funded rehearsal config to enable multi-strategy allocation testing. With only one strategy, equal allocation assigns 100% to that strategy, which violates the `max_single_strategy_allocation_fraction: 0.99` guardrail.

## What Was Added

### Strategy Configuration
- **strategy_id**: `allocation_stub_v1`
- **experiment_name**: `momentum` (same as existing strategy)
- **experiment_version**: `v1` (same as existing strategy)
- **experiment_config**: `{ "daily_trend": 0.0 }` (zero trend = minimal/no returns)
- **inputs**: Same structure as `test_strategy_v1`, same dates, same instrument
- **strategy_type**: `"buy_hold"` (required by SimpleResearchEngine)

### Config Changes
- Added strategy to `evaluation_config.strategies` array
- Updated `allocation_config.top_n_strategies` from `1` to `2`
- Added price entry in `execution_config.price_by_strategy_or_instrument`

## Why This Doesn't Affect Existing Behavior

### 1. No Code Changes
- No modifications to engine, evaluator, allocator, or lifecycle code
- Uses existing `SimpleResearchEngine` interface
- Uses existing `"buy_hold"` strategy type (only supported type)

### 2. Isolation
- Strategy has distinct `strategy_id` (`allocation_stub_v1` vs `test_strategy_v1`)
- Evaluated separately by existing batch evaluation system
- Allocated separately by existing allocation system

### 3. Zero-Trend Design
- `daily_trend: 0.0` means minimal returns (no directional bias)
- Will generate flat/neutral returns, effectively a no-op
- No trades expected (buy_hold with zero trend = no movement)

### 4. Sandbox-Only
- Only exists in `configs/funded/topstep_50k.json`
- Not referenced in any other configs
- Can be removed/reverted easily

## Allocation Impact

**Before (1 strategy)**:
- Strategy gets 100% allocation
- Violates 99% guardrail → HALT

**After (2 strategies)**:
- With equal allocation and `top_n_strategies: 2`:
  - `test_strategy_v1`: ~50% allocation
  - `allocation_stub_v1`: ~50% allocation
- Both below 99% limit → proceeds past guardrail check

## Determinism Guarantees

- Both strategies use same experiment (`momentum/v1`)
- Both use same date range and instrument
- Different `strategy_id` ensures separate evaluation runs
- Different `daily_trend` values ensure different return series
- All existing determinism guarantees remain intact

## Reversibility

To revert:
1. Remove `allocation_stub_v1` entry from strategies array
2. Change `top_n_strategies` back to `1`
3. Remove price entry for `allocation_stub_v1`

No code changes required to revert.

