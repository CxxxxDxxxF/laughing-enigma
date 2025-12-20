# Phase 1 Scope

## Objective

Produce reproducible backtests with institutional-grade analytics, visible in a clean UI.

## Success Criteria

- You can run the same config twice and get the same result
- You can explain every number on the dashboard
- You trust the metrics more than the curve
- No execution. No brokers. No money.

## Deliverables

### Experiment Registry
- Named experiments
- Versioned configs
- Hashable, reproducible inputs

### Backtest Runs
- Multiple runs per experiment
- Clear success or failure state
- Stored artifacts

### Metrics Pipeline
- Equity curve
- Drawdown
- Monthly returns
- Sharpe, volatility
- Turnover

### UI Dashboard
- Overview
- Experiments
- Runs
- Detailed run report

## Locked Architecture

No changes unless something breaks.

Execution engines do not exist yet.

