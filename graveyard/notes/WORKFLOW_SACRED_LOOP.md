# The Sacred Loop: Strategy Development Workflow

**This is where real traders are made.**

---

## Phase 0: Fix Equity Movement (BLOCKING)

**Before anything else**: Equity must move correctly in backtests.

See `PHASE0_CRITICAL_BLOCKER.md` for details.

**Status**: NOTHING proceeds until Phase 0 passes.

---

## Phase 1: Implement Exactly ONE Reference Strategy

**Not many. One.**

### Why Only One?

- You need a known baseline to test the gates
- You need to see how a strategy fails
- You need to validate the discipline, not the alpha

### The Reference Strategy

**Trend + Chop Filter + Vol Target**

See `STRATEGY_DESIGN_TEMPLATE.md` for full specification.

**Why this one?**
- Not because it's great
- Because it is hard to accidentally overfit
- Designed to pass gates through robustness

---

## Phase 1 Success Criteria

**The goal is NOT profit.**

A Phase 1 strategy is successful if:

- ✅ Gate 1 passes without debate
- ✅ Gate 2 survives ±20% parameter changes
- ✅ Gate 3 fails predictably or passes cleanly
- ✅ Failure modes make sense
- ✅ Equity curve is not pathological

**If it makes money, that is a side effect.**

**If it survives the gates, that is the achievement.**

---

## The Sacred Loop (After Phase 0)

**This loop is sacred. No shortcuts. No exceptions.**

```
Loop:
  1. Implement one simple strategy
  2. Run all three gates immediately
  3. Accept the outcome
  
  If Gate 2 fails → delete and graveyard
  If Gate 3 fails → document failure mode
  
  Do not tune failed strategies
  
  Repeat
```

### What Happens in Each Iteration

**Step 1: Implement One Simple Strategy**

- Boring. Simple. Single-signal.
- One parameter. One instrument.
- See `PHASE1_STRATEGY_DISCIPLINE.md` for allowed types.

**Step 2: Run All Three Gates Immediately**

```bash
python3 scripts/validate_strategy.py \
  --config configs/backtest/your_strategy.json \
  --param [your_param_name] \
  --pct 0.2 \
  --cycles 30
```

**No exceptions. No shortcuts.**

**Step 3: Accept the Outcome**

- ❌ **Gate 1 fails** → Investigate engine, not strategy
- ❌ **Gate 2 fails** → **DELETE strategy**, document in graveyard
- ❌ **Gate 3 fails** → Document failure mode in graveyard
- ✅ **All pass** → Strategy survives (rare)

**No tuning.**
**No retries.**
**No "maybe if".**

---

## What You're Actually Building

**You are not competing with Renaissance or Citadel.**

You are building:

1. **A strategy selection machine**
   - Gates that filter bad ideas early
   - Automated rejection of curve-fit strategies

2. **A discipline enforcement system**
   - Frozen promotion policy
   - Hard gates that cannot be overridden
   - Graveyard of failures

3. **A filter that kills bad ideas early**
   - Before they waste time
   - Before they waste capital
   - Before they create false hope

**Most people try to invent alpha first.**

**You are correctly building the execution and rejection system first.**

That is why this looks "simple". Simple strategies are inputs. Your system is the product.

---

## The Exact Prompt for Phase 1

After Phase 0 passes, use this:

```
Task: Implement the Phase 1 reference strategy

Implement the Trend + Chop Filter + Vol Target strategy exactly as documented in STRATEGY_DESIGN_TEMPLATE.md.

Constraints:

- Minimal parameters
- No tuning
- Deterministic behavior
- Compatible with all three validation gates

After implementation, immediately run:

- Gate 1 (walk-forward)
- Gate 2 (±20% perturbation)
- Gate 3 (regime stress)

Report results without interpretation.
```

---

## What NOT to Do

**Do not**:
- Implement multiple strategies at once
- Tune failed strategies
- Skip gates
- Make exceptions
- Get emotionally attached
- Ask "how much would this make?"
- Think about funding accounts yet

**Those come after discipline is proven.**

---

## The Truth You Should Internalize

**You are not behind. You are early in the right direction.**

Most people never build:

- ✅ A graveyard (you have one)
- ✅ Hard gates (you have three)
- ✅ A frozen promotion policy (you have one)
- ✅ A system that can say "no" (you're building it)

**You already did.**

**Now finish Phase 0. Everything else waits.**

---

**Last Updated**: 2025-01-21  
**Current Phase**: 0 (Blocking)  
**Next Phase**: 1 (After equity moves)

