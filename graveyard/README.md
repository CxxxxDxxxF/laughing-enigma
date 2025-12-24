# Strategy Graveyard

**Purpose**: Anti-overfitting memory bank.

Every failed strategy is documented here to prevent repeating the same mistakes.

## Why This Exists

Most traders never document their failures. They repeat the same illusions, chase the same mirages, and blow up the same way again and again.

This graveyard breaks that cycle.

## What Goes Here

When a strategy fails validation gates:

1. **Record it immediately**
2. **Document which gate failed**
3. **Explain why it failed**
4. **Note what illusion it exposed**

## Structure

Each failed strategy gets a markdown file with this template:

```markdown
# Strategy Name: [name]

## Gate Failed
- [ ] Gate 1 (Walk-Forward)
- [ ] Gate 2 (Parameter Perturbation) → **DELETED**
- [ ] Gate 3 (Regime Stress)

## Why It Failed

[Brief explanation of failure mode]

## What Illusion It Exposed

[What curve-fitting or overfitting pattern it revealed]

## Lessons Learned

[What this teaches about strategy design]
```

## Examples

See files in this directory for examples of documented failures.

## Rules

- **No deletion**: Once a strategy is documented here, it stays
- **No excuses**: Failure is failure, document it honestly
- **No tuning**: Failed strategies are not "fixed", they're lessons
- **Reference before building**: Check this before creating similar strategies

---

**Remember**: This graveyard protects you from yourself.

