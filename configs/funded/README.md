# Funded Firm Configurations

This directory contains configurations for various funded trading firm rules. These configs are designed to be runnable in `LIVE_DRY` mode to validate that your system halts exactly when a funded firm would halt you.

## Usage

These configs can be used with `run_portfolio_cycle` in `LIVE_DRY` mode:

```python
from src.lifecycle.runner import run_portfolio_cycle, ExecutionMode, PortfolioCycleConfig
from datetime import datetime

config = PortfolioCycleConfig.from_json_file("configs/funded/topstep_50k.json")
# ... set up engines and stores ...

result = run_portfolio_cycle(
    config=config,
    research_engine=research_engine,
    artifact_store=artifact_store,
    execution_engine_factory=create_engine,
    state_store=state_store,
    execution_mode=ExecutionMode.LIVE_DRY,
    cycle_timestamp=datetime.now()
)
```

## Config Files

### topstep_50k.json
- **Account Size**: $50,000
- **Max Daily Loss**: -$2,500 (5% of account)
- **Max Trailing Drawdown**: 5% ($2,500)
- **Timezone**: America/Chicago (Topstep uses CT)
- **Session Start**: 17:00:00 CT (5 PM, start of next trading day)

### topstep_100k.json
- **Account Size**: $100,000
- **Max Daily Loss**: -$2,000 (2% of account)
- **Max Trailing Drawdown**: 5% ($5,000)
- **Timezone**: America/Chicago (Topstep uses CT)
- **Session Start**: 17:00:00 CT

### apex_50k.json
- **Account Size**: $50,000
- **Max Daily Loss**: -$1,000 (2% of account, similar to Topstep)
- **Max Trailing Drawdown**: 5% ($2,500)
- **Timezone**: America/Chicago
- **Session Start**: 17:00:00 CT

## Rule Calibration

All configs use the `topstep` ruleset which enforces:
- `max_daily_loss`: Maximum daily loss (realized + unrealized PnL)
- `max_trailing_drawdown_pct`: Maximum trailing drawdown percentage
- `max_turnover_pct`: Maximum turnover per cycle (100% = no limit at ruleset level)
- `max_position_size`: Maximum position size (null = no limit)

## Guardrails

Funded firm configs use strict guardrails:
- `max_turnover_pct_per_cycle`: 0.5 (50% max turnover per cycle)
- `max_failed_intents`: 0 (no failed intents allowed)
- `min_execution_success_rate`: 0.95 (95% minimum success rate)
- `halt_on_any_error`: true (halt immediately on any error)

## Important Notes

1. **Timezone**: Topstep and Apex use Central Time (America/Chicago). Day boundaries are set to 17:00:00 CT (5 PM) which is the start of the next trading day in futures markets.

2. **Daily Loss**: This is checked against the change from the day's starting balance (initial_balance). If equity drops below `initial_balance + max_daily_loss`, a halt is triggered.

3. **Trailing Drawdown**: Once equity exceeds the initial balance, the trailing drawdown "locks in" and trails the high-water mark. If trailing drawdown exceeds `max_trailing_drawdown_pct`, a halt is triggered.

4. **Position Limits**: Some firms have position size limits. These are not yet encoded in these configs (max_position_size is null). Add them based on specific firm requirements.

5. **Time-of-Day Rules**: Some firms restrict trading during certain hours. These are not yet encoded. Add them to the ruleset if needed.

6. **Flatten-on-Close**: Some firms require positions to be flat at market close. This is not yet encoded. Add to execution logic if needed.

## Validation

Before using with real funds, validate that:
- Halt triggers match funded firm halt conditions
- Daily loss calculation matches firm's calculation
- Trailing drawdown calculation matches firm's calculation
- Day boundaries align with firm's trading day definition
- Position limits (if applicable) are enforced

Run in `LIVE_DRY` mode and compare halt behavior against firm's stated rules.

