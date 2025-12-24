# Phase 1: Strategy Development Discipline

**Status**: BLOCKED on Phase 0 (equity movement)

**⚠️ CRITICAL**: Do not proceed until `PHASE0_CRITICAL_BLOCKER.md` is resolved.

---

## Core Principle: Stop Thinking About Alpha

Alpha is not the goal. System stress testing is the goal.

Every strategy you build is a diagnostic instrument, not a money-maker.

---

## What You Build Now

### ✅ Allowed Strategy Types

**Boring. Simple. Single-signal.**

1. **Single-signal momentum**
   - One trend indicator
   - One lookback period
   - Buy/sell based on signal direction

2. **Single-signal mean reversion**
   - One mean-reversion indicator
   - One threshold
   - Buy/sell on deviation

3. **Trend-follow with one lookback**
   - Moving average crossover
   - Single period
   - No optimization

4. **Volatility breakout with one threshold**
   - Single volatility measure
   - Single threshold
   - Entry/exit rules

### ❌ Banned Strategy Types

**Complexity is forbidden until Phase 5.**

- Multi-indicator stacks
- ML models
- Regime-switching logic
- Anything that needs a paragraph to explain
- Feature engineering
- Parameter optimization
- Ensemble methods

**Rule**: If it needs explanation, it's banned.

---

## Strategy Development Workflow

### Step 1: Write the Dumbest Possible Form

**Constraints**:
- One signal
- One parameter
- One instrument
- One position rule
- Zero cleverness

**Example**:
```python
if price > moving_average(price, 20):
    signal = BUY
else:
    signal = SELL
```

That's it. Nothing more.

### Step 2: Run All Three Gates

**No exceptions. No shortcuts.**

```bash
python3 scripts/validate_strategy.py \
  --config configs/backtest/your_strategy.json \
  --param [your_param_name] \
  --pct 0.2 \
  --cycles 30
```

### Step 3: Accept the Result Without Debate

**The gates are absolute.**

- ❌ **Gate 1 fails** → Investigate engine, not strategy
- ❌ **Gate 2 fails** → **DELETE the strategy** (see graveyard process)
- ❌ **Gate 3 fails** → Document failure mode in graveyard

**No tuning.**
**No retries.**
**No "maybe if".**

**This is training you, not the code.**

---

## Strategy Graveyard Process

When a strategy fails, it goes to `/graveyard/`.

### Documentation Template

For every failed strategy, record:

1. **Strategy name**
2. **Which gate failed**
3. **Why it failed**
4. **What illusion it exposed**

### Example Entry

```
momentum_v2:
- Failed Gate 2
- Performance collapsed when lookback ±20%
- Revealed dependence on exact noise alignment
- Illusion: Thought signal was robust, was actually curve-fit
```

### Why This Matters

Most traders never do this. That's why they repeat mistakes.

This graveyard becomes your anti-overfitting memory.

---

## Survivors Are Rare

After many deletions, one of two things happens:

### Outcome 1: Nothing Survives

**This is normal.**

- It means your gates are working
- Most "alpha" is fake
- You are filtering correctly

### Outcome 2: Something Barely Survives

**Characteristics of a survivor**:
- Low Sharpe
- Modest returns
- Boring equity curve
- Predictable failure modes
- No excitement

**This is gold.**

Not because it's profitable. Because it's **honest**.

---

## Phase 5: Complexity (Future)

Complexity is allowed **only** to:
- ✅ Reduce known failure modes
- ✅ Improve robustness margins
- ✅ Control risk, not returns

Complexity is **never** allowed to:
- ❌ Increase Sharpe
- ❌ Fix Gate 2 failures
- ❌ Make equity prettier

**Rule**: If complexity improves returns but hurts robustness, it's rejected.

---

## Promotion Discipline (Non-Negotiable)

A strategy goes LIVE_DRY **only if**:

1. ✅ Gate 1 passed
2. ✅ Gate 2 passed
3. ✅ Gate 3 passed
4. ✅ **You feel bored looking at it**

### The Boredom Test

**If you feel excitement:**
- You are emotionally attached
- You are about to override a rule
- You are not ready to deploy it

**Boring strategies survive.**
**Exciting ones blow up.**

---

## What You Explicitly Do NOT Do Right Now

**Do not:**
- Copy Twitter strategies
- Read "alpha threads"
- Optimize parameters
- Ask "how much would this make?"
- Think about funding accounts yet

**Those come after discipline is proven.**

---

## Current Focus

1. Build boring strategies
2. Test with validation gates
3. Document failures in graveyard
4. Accept deletions without emotion
5. Wait for honest survivors

**You are training yourself, not the strategies.**

---

**Last Updated**: 2025-01-21  
**Phase**: 1 - System Stress Testing  
**Goal**: Discipline, not alpha

