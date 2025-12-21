# Research → Execution Integration: Design Summary

## Overview

The integration layer connects research outputs (backtest signals) to execution inputs (execution-ready orders) while maintaining strict domain separation.

## Key Interfaces

### 1. SignalEmitter (Research Domain)
- **Location:** `src/integration/emitter.py`
- **Purpose:** Interface for strategies to emit raw outputs
- **Output:** `RawStrategyOutput` (timestamp, instrument, action, quantity)
- **Key Method:** `emit_signals()` - yields raw strategy decisions

### 2. SignalAdapter (Integration Layer)
- **Location:** `src/integration/adapter.py`
- **Purpose:** Transform raw outputs → execution-ready Signals
- **Responsibilities:**
  - Validate raw outputs
  - Apply filters
  - Apply position sizing
  - Map action → SignalType
  - Pre-execution risk checks
- **Key Method:** `adapt()` - converts RawStrategyOutput to Signal
- **Configuration:** `AdapterConfig` (position sizing, filters, risk limits)

### 3. SignalConsumer (Execution Domain)
- **Location:** `src/integration/consumer.py`
- **Purpose:** Route validated Signals to ExecutionEngine
- **Responsibilities:**
  - Receive Signals
  - Submit to ExecutionEngine
  - Track signal → order mapping
- **Key Method:** `consume_signal()` - submits Signal to engine

## Data Flow

```
Research (Strategy)
    │
    ├─→ SignalEmitter.emit_signals()
    │   (yields RawStrategyOutput)
    │
    ▼
Integration Layer
    │
    ├─→ SignalAdapter.adapt()
    │   (validates, filters, sizes, converts)
    │
    ▼
Execution (Engine)
    │
    ├─→ SignalConsumer.consume_signal()
    │   (routes to ExecutionEngine)
    │
    ▼
ExecutionEngine.submit_order()
    (creates Order, enforces risk limits)
```

## Configuration Boundaries

### Fixed (Research)
- Strategy logic
- Backtest parameters
- Raw signal generation

### User-Controlled (Integration)
- Position sizing rules
- Signal filters
- Pre-execution risk limits

### Execution-Controlled (Execution)
- Order acceptance/rejection
- Execution price
- Fill details

## Failure Modes

### Signal Validation
- Invalid instrument → `InvalidSignalError`
- Invalid quantity → `InvalidSignalError`
- Missing fields → `InvalidSignalError`

### Risk Checks
- Position limit exceeded → `RiskCheckError`
- Instrument not allowed → `RiskCheckError`

### Execution
- Order rejection → `OrderRejectionError` (from ExecutionEngine)
- Risk limits violated → `RiskLimitExceededError` (from ExecutionEngine)

## Safety Principles

1. **Fail Fast:** Reject invalid signals immediately
2. **Fail Loud:** All rejections logged with reasons
3. **Fail Safe:** Invalid signals don't crash backtest
4. **Audit Trail:** Signal → Order mapping preserved
5. **Deterministic:** Same inputs → same outputs

## Domain Separation

- **Research doesn't know:** Orders, fills, execution prices
- **Execution doesn't know:** Strategy logic, backtest context
- **Integration doesn't know:** Strategy internals, execution internals

## Next Steps

1. Implement basic SignalAdapter for Phase 1 strategies
2. Implement SignalConsumer for PaperExecutionEngine
3. Wire into backtest execution flow
4. Add signal storage/retrieval
5. Add UI for signal inspection

