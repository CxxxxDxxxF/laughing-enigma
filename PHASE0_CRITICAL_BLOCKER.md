# Phase 0: Equity Movement Verification (CRITICAL BLOCKER)

**Status**: BLOCKING ALL STRATEGY WORK

**Priority**: Non-negotiable. Nothing else matters until this is fixed.

---

## The Problem

Many backtest runs show **"Final equity stays at $50,000"** (unchanged from initial capital).

**This makes all validation gates meaningless.**

---

## Definition of "Fixed"

A backtest must show:

1. ✅ **Positions opening**
   - Orders are generated
   - Fills are created
   - Positions are established

2. ✅ **Prices changing per cycle**
   - Price series updates
   - Execution prices reflect current market

3. ✅ **Equity changing mark-to-market, not just at close**
   - Unrealized PnL updates as prices move
   - Equity reflects current portfolio value

4. ✅ **Losses and gains reflected in**:
   - Cycle summaries
   - Evidence reports
   - Drawdown tracker

---

## If Equity is Flat at $50,000

- ❌ Gate passes are meaningless
- ❌ Strategy validation is invalid
- ❌ Promotion policy is unenforceable
- ❌ All strategy work is wasted effort

**Everything is fake until this is resolved.**

---

## The Task (One Thing Only)

**Trace one cycle end-to-end**:

```
price → signal → intent → fill → position → PnL → equity
```

**If any link is broken, stop and fix that link.**

**No new strategies until this is resolved.**

---

## Verification Checklist

For a single backtest cycle, verify:

- [ ] Price updates from price_series or execution config
- [ ] Strategy generates signal based on price
- [ ] Signal becomes execution intent
- [ ] Intent creates order
- [ ] Order generates fill
- [ ] Fill updates position
- [ ] Position PnL is calculated (realized + unrealized)
- [ ] Equity updates in cycle summary
- [ ] Equity propagates to evidence report
- [ ] Equity updates drawdown tracker
- [ ] Multiple cycles show equity changes

---

## The Exact Prompt to Use

```
Task: Verify backtest integrity

Trace a single backtest cycle end-to-end and confirm that:

- prices update per cycle
- at least one order is generated
- fills create positions
- PnL is calculated from fills
- equity changes as prices move

Identify where equity remains constant and fix the minimal root cause.

Do not modify strategy logic.
Do not add features.
Stop once equity movement is correct and deterministic.
```

---

## After Phase 0 Passes

Only then proceed to Phase 1 (implement one reference strategy).

**Nothing else happens until equity moves correctly.**

---

**Last Updated**: 2025-01-21  
**Status**: BLOCKING  
**Priority**: CRITICAL

