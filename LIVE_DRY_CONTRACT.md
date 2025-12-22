# LIVE_DRY Mode Execution Contract

## Purpose

LIVE_DRY mode enforces the same strict constraints as LIVE mode but does not place real orders with external brokers. It is designed for:

- Testing LIVE mode behavior without risk
- Validating halt and guardrail logic
- Ensuring determinism before going live
- Proving system behavior to funded firms

## Execution Contract

### Identical to LIVE Mode

LIVE_DRY mode behaves identically to LIVE mode in:

1. **Validation**
   - Requires explicit `cycle_timestamp`
   - Requires explicit `cycle_id`
   - Requires non-permissive `guardrails_config`
   - Checks for halt flags before execution
   - Enforces all guardrails (allocation, rebalance, execution)

2. **Determinism**
   - Uses `FixedClock` seeded from `cycle_timestamp`
   - Uses `DeterministicIDProvider` seeded from `cycle_id` or `cycle_timestamp`
   - All timestamps and IDs are deterministic
   - Same inputs produce identical outputs

3. **Pipeline Execution**
   - Runs complete portfolio lifecycle pipeline
   - Executes evaluation → allocation → planning → execution
   - Produces all artifacts (same as LIVE)
   - Updates portfolio state (if state_store provided)

4. **Halt Behavior**
   - Writes halt flags on violations (same as LIVE)
   - Raises `CycleHaltError` (same as LIVE)
   - Prevents continuation until manually cleared

### Difference from LIVE Mode

**Only difference**: Execution engine never sends orders to external broker adapter.

Since the system currently uses `PaperExecutionEngine` (no broker adapter exists yet), LIVE_DRY and LIVE are functionally identical. Both use the paper execution engine.

When a real broker adapter is implemented:
- **LIVE_DRY**: Will use `PaperExecutionEngine` (simulated execution)
- **LIVE**: Will use `LiveExecutionEngine` (real broker orders)

### Implementation Status

- ✅ ExecutionMode enum includes LIVE_DRY
- ✅ All validations treat LIVE_DRY same as LIVE
- ✅ Halt flags written in LIVE_DRY mode
- ✅ Deterministic clock and ID provider used in LIVE_DRY mode
- ⚠️ Broker adapter separation not yet implemented (uses PaperExecutionEngine for both)

### Future Broker Integration

When broker adapter is added:

```python
if execution_mode == ExecutionMode.LIVE:
    execution_engine = LiveExecutionEngine(broker_connection, ...)
elif execution_mode == ExecutionMode.LIVE_DRY:
    execution_engine = PaperExecutionEngine(...)  # Simulated
else:  # SIMULATION
    execution_engine = PaperExecutionEngine(...)  # Simulated
```

The contract ensures LIVE_DRY produces identical artifacts and behavior to LIVE, just without external order placement.

