# Sanity Backtest Results - Layer 1

**Status**: PASS

## Configuration

- **Instrument**: ES
- **Strategy**: buy_hold (daily_trend=0.001)
- **Date Range**: 2024-01-01 to 2024-03-31
- **Initial Capital**: $50,000.00
- **Cycles**: 91

## Metrics

- **Trade Count**: 1
- **Net PnL**: $4,405.05
- **Final Equity**: $54,405.05
- **Total Return**: 8.81%
- **Expectancy Per Trade**: $4,405.05
- **Total Commission**: $46.20
- **Total Slippage**: $250.00
- **Total Execution Costs**: $296.20
- **Execution Cost Impact**: 6.72%
- **Daily Loss Breaches**: 0
- **Daily Loss Breach Frequency**: 0.00%
- **Max Drawdown**: $0.00 (0.00%)

## Validation Checks

- **trades_occurred**: ✅ PASS
- **losses_occurred**: ✅ PASS
- **slippage_reduced_returns**: ✅ PASS
- **no_silent_rule_bypasses**: ✅ PASS
- **equity_remains_finite**: ✅ PASS

**All Validations Pass**: ✅ YES

## Decision: **PASS**

## Equity Series

| Date | Equity |
|------|--------|
| 2024-01-01 | $50,000.00 |
| 2024-01-02 | $50,050.00 |
| 2024-01-03 | $50,100.05 |
| 2024-01-04 | $50,150.15 |
| 2024-01-05 | $50,200.30 |
| 2024-01-06 | $50,250.50 |
| 2024-01-07 | $50,300.75 |
| 2024-01-08 | $50,351.05 |
| 2024-01-09 | $50,401.40 |
| 2024-01-10 | $50,451.80 |
| 2024-01-11 | $50,502.26 |
| 2024-01-12 | $50,552.76 |
| 2024-01-13 | $50,603.31 |
| 2024-01-14 | $50,653.91 |
| 2024-01-15 | $50,704.57 |
| 2024-01-16 | $50,755.27 |
| 2024-01-17 | $50,806.03 |
| 2024-01-18 | $50,856.83 |
| 2024-01-19 | $50,907.69 |
| 2024-01-20 | $50,958.60 |
| ... | ... (70 more entries) |

## Raw Data

Full results saved to: `artifacts_sanity_backtest/`

---

**Generated**: 2025-12-23T21:52:23.450566
**Spec Version**: BACKTEST_SPEC_V1.md