# Strategy Name: [strategy_id]

**Date Failed**: [YYYY-MM-DD]  
**Config Path**: `configs/backtest/[filename].json`

---

## Gate Failed

- [ ] Gate 1 (Walk-Forward Validation)
- [ ] Gate 2 (Parameter Perturbation) → **DELETED**
- [ ] Gate 3 (Regime Stress)

---

## Strategy Description

[One sentence description of what the strategy was supposed to do]

**Signal Type**: [momentum/mean_reversion/trend_follow/volatility_breakout]

**Parameters**:
- `[param_name]`: [value]

**Instrument**: [instrument]

---

## Why It Failed

[Brief explanation of the failure mode observed during validation]

**Specific Failure Indicators**:
- [Metric that failed]
- [What the gate detected]

---

## What Illusion It Exposed

[What curve-fitting or overfitting pattern this strategy revealed]

**Common patterns**:
- Parameter sensitivity (Gate 2)
- Lookahead bias (Gate 1)
- Regime-specific overfitting (Gate 3)
- Noise alignment dependency

---

## Validation Results Summary

**Gate Results**:
- Gate 1: [PASS/FAIL/SKIP]
- Gate 2: [PASS/FAIL/SKIP]
- Gate 3: [PASS/FAIL/SKIP]

**Key Metrics** (if available):
- Final Equity: $[amount]
- Max Drawdown: $[amount]
- Sharpe: [value]

---

## Lessons Learned

[What this teaches about strategy design]

**Do not repeat**:
- [Pattern to avoid]

**Future strategies should**:
- [What to do differently]

---

## Action Taken

- [ ] Strategy code deleted
- [ ] Config file archived/deleted
- [ ] Evidence artifacts retained for reference
- [ ] This entry created in graveyard

---

**Remember**: This failure is a lesson, not a setback.

