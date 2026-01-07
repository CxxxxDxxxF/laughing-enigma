# Halt Clearance Contract

This document defines the strict invariants and validation logic required to safely clear a system halt in the trading engine. Adherence to this contract is mandatory for maintaining "Funded Account" compliance and data integrity.

## 1. Safety Invariants
Before a halt flag can be cleared (`HALTED` file removed):

*   **Persistence Invariant**: The state of the portfolio *at the moment of the halt* MUST be persisted. This includes the `drawdown_tracker` reflecting the loss that caused the halt.
    *   *Why*: If we lose this state, the system will "rewind" to the pre-halt state, forgetting the loss and potentially allowing trading to continue in violation of daily loss limits.
*   **Acknowledgment Invariant**: The operator must explicitly acknowledge the specific halt reason (e.g., "Max Daily Loss hit: -$500").
*   **Timeflow Invariant**: Time must strictly move forward. The next cycle ID must be greater than the halted cycle ID. Re-running the *same* cycle ID after a halt is forbidden if it involves state rewinding.

## 2. Unsafe Patterns (Forbidden)

*   **[DANGEROUS] The "Ghost" Clearance**: Deleting the `HALTED` file without ensuring the corresponding `_halted_after` state exists.
    *   *Result*: System loads state *N-1*, forgets the crash, and repeats the mistake (or violates drawdown rules).
*   **[DANGEROUS] The "Time Traveler"**: Manually deleting the latest state file to "undo" a bad trade.
    *   *Result*: Immediate disqualification in funded challenges. Determinism is broken.
*   **[DANGEROUS] Hot-Patching**: Modifying code variables in a debugger to bypass the halt check.

## 3. Validation Gate (Pseudocode)
The following logic must be executed by any tool (or the runner itself) that attempts to resume a portfolio:

```python
def validate_resumption_safety(portfolio_id, artifact_store):
    """
    Validates if it is safe to resume execution for a portfolio.
    Must be called BEFORE clearing any halt flags or running a new cycle.
    """
    
    # 1. Check for Active Halt
    halt_flag = artifact_store.read_halt_flag(portfolio_id)
    if halt_flag:
        raise DangerousOperationError(
            f"System is HALTED ({halt_flag.reason}). "
            "You CANNOT run a new cycle until this is mechanically cleared. "
            "Use 'dashboard.py resolve --acknowledge' to clear safely."
        )

    # 2. Check State Consistency (The 'Ghost' Check)
    latest_state = state_store.load_latest_state(portfolio_id)
    
    # Invariant: If the last run halted, the latest state MUST have metadata["halted"] = True
    # We can infer 'last run halted' if we have logs, but strictly speaking,
    # if we are resuming, we just need to ensure the DrawdownTracker makes sense.
    
    if latest_state.metadata.get("halted") is True:
        # We are resuming from a halted state. 
        # Ensure DrawdownTracker is not corrupt (simple sanity check)
        if latest_state.drawdown_tracker.daily_loss == 0.0 and "Max Daily Loss" in latest_state.metadata.get("halt_reason"):
             raise CorruptionError("Halted state claims Max Daily Loss but Tracker shows $0 loss. State is corrupt/rewound.")

    # 3. Time Safety
    # (Optional) Verify we aren't trying to run a cycle ID that already exists
    return True
```

## 4. Required Tests

To enforce this contract, the following tests must exist in `tests/test_halt_clearance.py`:

*   **[ ] Test Ghost Clearance Prevention**:
    1.  Simulate a halt.
    2.  Delete the persisted `_halted_after` state (simulating data loss).
    3.  Attempt to resume (or run dashboard check).
    4.  **Expect**: High-severity warning or error (if logic detects gap). *Note: Detecting deletion is hard without an external log, but we can verify that IF a halt flag exists, the latest state matches it.*
*   **[ ] Test State Continuity**:
    1.  Halt system (Daily Loss -$1000).
    2.  Clear halt flag.
    3.  Resume.
    4.  **Verify**: New cycle starts with `drawdown_tracker` showing -$1000 loss (and likely halts again immediately if rules are strict, or proceeds if day rolled over).
*   **[ ] Test Acknowledgment**:
    1.  CLI tool should refuse to clear halt unless `--reason` or similar confirmation is passed.
