# Strategy Promotion Pipeline

**Policy Document - Non-Negotiable Requirements**

This document defines the mandatory stages every strategy must pass before reaching live trading.

---

## Overview

```
SIMULATION
   ↓ (Gate 1, 2, 3 passed)
LIVE_DRY (single strategy, small turnover)
   ↓ (30-60 cycles, zero rule violations)
FUNDED (Topstep/Apex rules)
   ↓ (Pass firm rules + profit buffer)
LIVE (same strategy, same config, reduced size)
```

---

## Stage 1: SIMULATION

**Purpose**: Prove strategy robustness through validation gates.

### Requirements

✅ **Pass all 3 validation gates:**

1. **Gate 1: Walk-Forward Validation**
   - Run: `python scripts/run_walkforward.py --config <config>`
   - Must pass:
     - Test Sharpe ≥ 0.5 × Train Sharpe
     - Test max drawdown ≤ 1.5 × Train max drawdown

2. **Gate 2: Parameter Perturbation**
   - Run: `python scripts/run_parameter_sensitivity.py --config <config>`
   - Must pass:
     - Equity curve correlation > 0.8
     - No drawdown explosion (max variant DD ≤ 2× base DD)
   - **Failure Action**: Delete strategy. Do not tweak or fix.

3. **Gate 3: Regime Stress**
   - Run: `python scripts/run_regime_stress.py --config <config>`
   - Must pass:
     - No catastrophic loss (>50% loss) in any regime
   - Underperformance is acceptable; unbounded loss is rejection

### Failure Policy

**If a strategy fails any gate:**
- ❌ Delete it
- ❌ Do not "fix" it
- ❌ Do not tweak parameters
- ✅ This saves months later

### Strategy Selection Discipline

**Ideal first strategies:**
- Simple
- Boring
- Low turnover
- Daily or slower cadence
- Momentum, carry, or volatility-scaled trend following

**Do not start with:**
- Intraday scalping
- Multi-indicator soups
- ML-heavy logic

You're building infrastructure, not chasing dopamine.

---

## Stage 2: LIVE_DRY

**Purpose**: Validate strategy under LIVE constraints without real capital.

### Requirements

✅ **30-60 cycles with zero rule violations**

- Use: `python scripts/funded_rehearsal.py --config <config>`
- Execution mode: `ExecutionMode.LIVE_DRY`
- Guardrails enforced:
  - `max_turnover_pct_per_cycle < 1.0` (strict)
  - All funded firm rules active
  - Halt on any violation

### Success Criteria

- ✅ All cycles complete (status="completed")
- ✅ Zero rule violations across all cycles
- ✅ No halts triggered
- ✅ Equity curve looks reasonable
- ✅ Drawdowns stay within expected bounds

### Failure Policy

**If violations occur:**
- Review violation types and frequencies
- May need to return to SIMULATION for adjustments
- Or reject strategy if violations are systematic

---

## Stage 3: FUNDED

**Purpose**: Validate strategy against specific funded firm rules (Topstep/Apex).

### Requirements

✅ **Pass firm-specific rules + profit buffer**

- Use funded firm configs (e.g., `configs/funded/topstep_50k.json`)
- Run: `python scripts/funded_rehearsal.py --config <funded_config>`
- Execution mode: `ExecutionMode.LIVE_DRY`
- Firm rules enforced:
  - Daily loss limits
  - Trailing drawdown limits
  - Turnover limits
  - Position size limits (if applicable)

### Success Criteria

- ✅ Strategy survives full rehearsal period (30+ cycles)
- ✅ No rule violations
- ✅ Profit buffer: Strategy should be profitable, not just surviving
- ✅ Drawdown behavior matches expectations

### Notes

- Each funded firm has different rules (see `configs/funded/` for firm-specific configs)
- Must pass rehearsal for each firm separately
- Firm rules are stricter than general LIVE_DRY mode

---

## Stage 4: LIVE

**Purpose**: Trade real capital with validated strategy.

### Requirements

✅ **Same strategy, same config, reduced size**

- Strategy must have passed all previous stages
- Use exact same config that passed LIVE_DRY and FUNDED
- Start with **reduced position size** (e.g., 50% of backtested size)
- Execution mode: `ExecutionMode.LIVE`

### Size Reduction Rationale

- Backtests have assumptions (slippage, fills, timing)
- Real markets have more friction
- Reduced size provides safety buffer
- Can scale up after proving real-world performance

### Monitoring

- Monitor for 30+ cycles before considering size increases
- Watch for divergence from backtested behavior
- Maintain strict halt enforcement

---

## Promotion Checklist

Use this checklist for each strategy:

```
[ ] Gate 1 (Walk-Forward): PASSED
    - Train/Test Sharpe ratio check: PASS
    - Drawdown check: PASS
    
[ ] Gate 2 (Parameter Perturbation): PASSED
    - Correlation > 0.8: PASS
    - No drawdown explosion: PASS
    
[ ] Gate 3 (Regime Stress): PASSED
    - No catastrophic loss: PASS
    - Failure modes documented: YES
    
[ ] LIVE_DRY Rehearsal: PASSED
    - Cycles completed: ___/30
    - Rule violations: 0
    - Halts: 0
    
[ ] FUNDED Rehearsal: PASSED
    - Firm: ___________
    - Cycles completed: ___/30
    - Rule violations: 0
    - Profit buffer: YES
    
[ ] LIVE Deployment: READY
    - Config locked: YES
    - Size reduced: YES (50% of backtest)
    - Monitoring plan: YES
```

---

## Non-Negotiable Rules

### Rule 1: All Gates Must Pass

**If a strategy does not pass all three gates, it never reaches LIVE_DRY.**

- No exceptions
- No "one more tweak"
- No "it's close enough"

### Rule 2: No Skipping Stages

You cannot skip from SIMULATION directly to LIVE.

- Each stage validates different aspects
- LIVE_DRY validates LIVE constraints
- FUNDED validates firm-specific rules
- All are required

### Rule 3: Config Locking

Once a strategy passes SIMULATION gates:
- Lock the config
- No parameter tweaking between stages
- Same config must pass LIVE_DRY, FUNDED, and LIVE

### Rule 4: Failure = Delete, Don't Fix

If Gate 2 (Parameter Perturbation) fails:
- Strategy is curve-fit
- Delete it
- Do not try to "fix" it
- Start over with a new strategy

---

## Implementation Status

### ✅ Completed

- ✅ Gate 1: Walk-Forward Validation (`scripts/run_walkforward.py`)
- ✅ Gate 2: Parameter Perturbation (`scripts/run_parameter_sensitivity.py`)
- ✅ Gate 3: Regime Stress (`scripts/run_regime_stress.py`)
- ✅ LIVE_DRY infrastructure (`scripts/funded_rehearsal.py`)
- ✅ Funded firm configs (`configs/funded/`)
- ✅ Halt enforcement
- ✅ Rule validation

### ⚠️ Policy Implementation

The code infrastructure exists. What's missing is **policy discipline**:

- ✅ Gates exist and can be run
- ⚠️ Must enforce: "All gates must pass before LIVE_DRY"
- ⚠️ Must enforce: "Gate 2 failure = delete strategy"
- ⚠️ Must enforce: "Config locking between stages"

**This is a discipline problem, not a code problem.**

---

## What You Should NOT Do Yet

This matters more than what you should do.

❌ **Do not build a UI yet**
- UI comes after strategy confidence, not before

❌ **Do not optimize PnL**
- Focus on robustness, not returns

❌ **Do not add more strategies**
- Validate infrastructure with one strategy first

❌ **Do not trade live capital**
- Not until all stages pass

❌ **Do not refactor working engine code**
- Infrastructure is proven; don't break what works

---

## Questions to Ask Yourself

Before promoting a strategy, ask:

1. ✅ Did it pass all 3 gates?
2. ✅ Did it pass LIVE_DRY rehearsal with zero violations?
3. ✅ Did it pass FUNDED rehearsal for the target firm?
4. ✅ Is the config locked (no changes since SIMULATION)?
5. ✅ Am I starting with reduced size in LIVE?

If any answer is "no", stop and fix it.

---

## Document Control

**Status**: Policy Document (Non-Negotiable)

**Last Updated**: 2025-12-21

**Enforcement**: Self-enforced discipline. Code provides tools; you provide judgment.

