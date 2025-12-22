# Strategy Promotion Policy

**FROZEN POLICY - DO NOT EDIT CASUALLY**

This document defines the non-negotiable requirements for promoting a trading strategy from backtest to LIVE_DRY execution.

---

## Validation Gates

All strategies must pass three validation gates before promotion:

### Gate 1: Walk-Forward Validation
- **Status**: MUST PASS
- **Purpose**: Prove no lookahead bias
- **Failure Action**: Strategy does not proceed

### Gate 2: Parameter Perturbation
- **Status**: MUST PASS
- **Purpose**: Kill curve-fit strategies
- **Failure Action**: **Strategy is DELETED, not tuned**
- **No Exceptions**: If Gate 2 fails, the strategy is fundamentally flawed. Do not attempt to fix it.

### Gate 3: Regime Stress
- **Status**: MUST PASS
- **Purpose**: Understand failure modes across market regimes
- **Failure Action**: **Failure mode must be documented** before proceeding

---

## Promotion Requirements

**No LIVE_DRY execution without all three gates passing.**

This means:
- ✅ All gates pass → Strategy can proceed to LIVE_DRY
- ❌ Any gate fails → Strategy stops, does not proceed

---

## Enforcement

- **No exceptions**
- **No "just this once"**
- **No emotional overrides**
- **No tuning failed strategies**

If a strategy fails validation, it is either:
1. Deleted (Gate 2 failure)
2. Documented and fixed before retesting (Gate 3 failure)
3. Not promoted (Gate 1 failure)

---

## Rationale

This policy protects against:
- Overfitting to historical data
- Curve-fitting to specific parameters
- Unpredictable failures in production
- Emotional attachment to losing strategies
- Premature deployment

**Future-you will thank present-you for following this policy.**

---

**Last Updated**: 2025-01-21  
**Version**: 1.0  
**Status**: FROZEN

