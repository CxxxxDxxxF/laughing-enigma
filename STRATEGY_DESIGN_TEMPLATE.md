# Strategy Design Template: Trend + Chop Filter + Vol Target

**Purpose**: Reference design for Phase 1 strategy that should pass validation gates.

**Status**: Design specification (not yet implemented)

---

## Core Philosophy

**Boring core, regime filter, volatility targeting**

This strategy is not trying to predict. It is trying to **not die**.

---

## What It Trades

- **Liquid index exposure first**: SPY / QQQ / ES / NQ (not single-name)
- **One direction at a time per instrument**: long, short, or flat
- **Optional**: Two instruments max in Phase 1 to reduce interactions

---

## Strategy Specification

### Inputs (Few, Stable)

```
lookback_fast = 50
lookback_slow = 200
chop_window = 20
target_vol_annual = 10%  (or 8 to 12)
max_leverage = 1.0  (start)
rebalance_frequency = daily  (or every N days)
stop_trading_on_halt = true  (obvious)
```

### Signal: Trend Direction

```
trend = sign(SMA(close, 50) - SMA(close, 200))

If trend > 0: long bias
If trend < 0: short bias
If trend == 0: flat
```

**Why**: Slow parameters (50/200) are "wide basin" - not magical, just coarse trend detection.

### Chop Filter (Avoid Flat Regimes)

**Trend strength proxy**:
```
strength = abs(SMA50 - SMA200) / close
```

**Trade only if**:
```
strength > threshold
```

**Threshold**: Coarse, not tuned
- Example: `threshold = 0.005` (0.5%)
- Test wide perturbations: `0.003, 0.005, 0.008`

**Why**: In mean-reverting and flat regimes, go flat instead of bleeding. Helps Gate 3.

### Volatility Targeting (Position Sizing)

**Compute daily vol estimate**:
```
vol = stdev(returns, 20)
```

**Target daily vol**:
```
target_daily = target_vol_annual / sqrt(252)
```

**Position fraction**:
```
w = clamp(target_daily / vol, 0, max_leverage)
```

**Final position**:
```
position = trend * w
```

**Why**: Vol targeting damps sensitivity - even if signal timing is slightly off, size adjusts. Reduces drawdown blowups.

### Execution Rules

**Rebalance only if weight change > threshold**:
```
if abs(w_new - w_old) > 0.05: rebalance
```

**Slippage and fees must be included** in backtest assumptions, or gates become meaningless.

---

## Why This Should Pass Gates

### Gate 1: Walk-Forward Validation

**Why it works**:
- SMA cross and vol targeting are **time-causal** (no future data)
- Design is **not optimized** on narrow window
- Vol targeting and chop filter reduce exposure when volatility rises and when chop dominates
- Should "degrade but not collapse" in walk-forward

**Walk-forward split**:
- Train: 2022-01-01 to 2023-06-30
- Test: 2023-07-01 to 2024-12-31
- **No overlap**

### Gate 2: Parameter Perturbation

**Parameters to perturb**:
- `lookback_fast`: 40, 50, 60 (±20%)
- `lookback_slow`: 160, 200, 240 (±20%)
- `threshold`: 0.003, 0.005, 0.008 (wide range)
- `target_vol_annual`: Small range (8%, 10%, 12%)

**Why it should survive**:
- **Wide basin parameters**: 50/200 is not magical, just coarse
- **Vol targeting dampens sensitivity**: Size adjusts even if signal timing is off
- **Coarse thresholds**: Not fine-tuned, should be robust

**If small changes kill it**: It dies. If it survives, it's a real candidate.

### Gate 3: Regime Stress

**Expected behavior by regime**:

1. **Trending regime**: Participates (trades with trend)
2. **Mean reverting**: Chop filter forces flat more often
3. **Flat**: Mostly flat, low churn (if rebalance threshold exists)
4. **Volatile**: Vol targeting shrinks exposure, reducing catastrophic losses

**Regime price series** (must be realistic, not too clean):
- Trending up with occasional pullbacks
- Mean reversion with noise
- Flat with noise
- Volatile with whipsaws

**Warning**: If regime generator is too clean, you'll get false passes.

---

## What "Effective" Means in Phase 1

**Effective = Does not violate rules, not "profitable"**

Phase 1 criteria:
- ✅ Does not violate rules
- ✅ Does not blow up in stress
- ✅ Produces stable equity curve shape under perturbation
- ✅ Produces non-pathological behavior (no infinite leverage, no constant flipping)

**Phase 2** defines return expectations.

Phase 1 is about **robustness**, not alpha.

---

## Implementation Notes

### Gate 2 Config

Perturb only these:
- `lookback_fast`
- `lookback_slow`
- `threshold`
- `target_vol_annual` (small range)

If 20% perturbation causes collapse → delete strategy.

### Current System Concerns

**Critical Issue**: Current results show "Final equity stays at $50,000" in many runs.

This usually means one of:
1. Strategy is not actually trading
2. Mark-to-market / PnL is not being applied correctly
3. Price series is not connected to execution prices per cycle, so nothing moves

**Action Required**: Gate passes are **meaningless** until simulation produces believable PnL dynamics.

---

## Design Principles

1. **Slow parameters**: Reduce Gate 2 fragility
2. **Volatility targeting**: Position size adapts, reduces drawdown blowups
3. **Regime filter**: Avoid chop where trend loses
4. **Coarse thresholds**: Not fine-tuned, wide basin
5. **Time-causal**: No lookahead bias
6. **Not trying to predict**: Trying to not die

---

**This is the template for Phase 1 strategies.**
**Boring. Robust. Honest.**

