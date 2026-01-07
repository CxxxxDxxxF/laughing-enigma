# Antigravity Audit Report & System Contract

## System Understanding

### Architecture Summary
The system employs a strict linear pipeline architecture emphasizing immutability and determinism.
**Pipeline**: `Runner` -> `Load State` -> `Evaluate` -> `Allocate` -> `Plan` -> `Execute` -> `Persist State`.

### Lifecycle Diagram
```text
[Disk/Artifacts]
      ^
      | (Load State N)
      v
[Runner]
  |--> [BatchEvaluation] (Generate Signals)
  |--> [Allocator]       (Determine Target Capital Dist)
  |--> [RebalancePlanner] (Diff: Target - Current = Deltas)
  |--> [ExecEngine]      (Fill Orders Deterministically)
  |--> [StateStore]      (Save State N+1)
```

### Invariants
1.  **Time**: `cycle_timestamp` acts as the single source of truth. `datetime.now()` is strictly forbidden in business logic during LIVE execution.
2.  **Identity**: Deterministic UUID generation seeded by `cycle_id` ensures replayability.
3.  **State**: Append-only persistence. History is never overwritten.
4.  **Guardrails**: Checked pre-execution (allocation/planning) and post-execution (fills).

---

## Determinism Audit

### Verified
-   `runner.py`: Correctly enforcing `FixedClock` and `DeterministicIDProvider` when `ExecutionMode` is LIVE/LIVE_DRY.
-   `paper_engine.py`: Execution logic relies purely on input signals and config prices.
-   `drawdown.py`: Mathematical calculations are free of side effects.

### Critical Finding: Halt State Data Loss
**Severity**: High
**Location**: `src/lifecycle/runner.py` (Lines ~1008-1020, ~1477)
**Issue**: When a cycle halts (e.g., due to a guardrail violation like `Max Daily Loss`), the system writes a `HALTED` flag file but **skips saving the new portfolio state** (`state_after_id` is None).
**Consequence**: The `DrawdownTracker` updates (which tracked the loss causing the halt) are discarded. If the user clears the halt flag, the system reloads the *previous* state, effectively "forgetting" the loss. This breaks the "Funded Account" requirement of strict daily loss enforcement.
**Status**: **RESOLVED**. Fixed in `runner.py` to persist `drawdown_tracker` and state on halt. Verified by `tests/test_halt_persistence.py`.

---

## Trading Logic Risks

| Risk | Status | Notes |
| :--- | :--- | :--- |
| **Only one trade ever firing** | Low | System iterates all strategies. `top_n` config controls breadth. |
| **Positions never closing** | Low | `RebalancePlanner` correctly calculates negative deltas for removed strategies. |
| **Allocations not changing** | Expected | If strategy signals are static, allocations remain static. Design intent (stateless allocator). |
| **Equity not moving** | Config | In SIM/LIVE-DRY, equity depends on `price_by_strategy_or_instrument` config. Needs real data for LIVE. |
| **Re-entry blocked** | Safe | Tracker locking is one-way. Re-entry only blocked if HALT is triggered. |

---

## Dashboard Design Contract

**Principle**: Headless, read-only observer. No database dependency.

### Data Sources (Artifacts)
-   `portfolio/{id}/states/{id}.json`: Equity, Allocations, Positions, Drawdown Tracker.
-   `portfolio/{id}/HALTED`: System health and manual intervention triggers.
-   `runs/{id}/rebalance_execution.json`: Trade history.

### Required Interface (CLI/API)
1.  **`metrics`**: Returns current Equity, Daily PnL, Open PnL, Drawdown % from latest state.
2.  **`positions`**: Returns list of open instruments with Qty and Entry Price.
3.  **`status`**: Returns System Mode (LIVE/SIM), Halt Status, and Guardrail Utilization.
4.  **`history`**: Returns simple list of recent fills.

---

## Funded Account Readiness

### Compliance Checklist
-   [x] **Max Daily Loss**: Implemented (`DrawdownTracker`). **VERIFIED FIXED**.
-   [x] **Trailing Drawdown**: Implemented (High-Water Mark logic).
-   [x] **Max Position Size**: Implemented (Cap enforcement).
-   [x] **Session Boundaries**: Implemented (`TradingDayBoundary`).

### Blocking Issues
1.  **Halt Persistence**: Must fix the state loss on halt to ensure PnL memory persists.
2.  **Live Price Injection**: `run_portfolio_cycle` currently relies on static execution config for prices. LIVE mode requires a `MarketDataProvider` to inject real-time execution prices.

---

## Recommended Next Actions

1.  **Fix Critical Bug**: Patch `runner.py` to persist a "Halted State" snapshot so `DrawdownTracker` history is preserved.
2.  **Dashboard CLI**: Implement a simple `scripts/dashboard.py` to prove visibility without external deps.
3.  **Live Price Connector**: **IMPLEMENTED**. `MarketDataProvider` interface integrated into `runner.py`. Verified by `tests/test_live_prices.py`.
