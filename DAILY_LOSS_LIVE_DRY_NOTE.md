Daily loss guardrail cannot be reached in LIVE_DRY rehearsal because
first-cycle rebalance causes 100% turnover, which correctly halts
before loss accumulation when max_turnover_pct_per_cycle < 1.0.

This is expected and desirable safety behavior.
Daily loss will be validated in backtests and paper live runs.
