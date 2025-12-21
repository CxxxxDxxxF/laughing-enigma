# Research → Execution Integration Design

## Overview

This document defines the integration layer that connects the research domain (backtests, strategies) to the execution domain (paper trading, live trading).

## Core Principle

**Research answers "what should I do?"**
**Execution answers "what actually happened?"**

These domains must remain separate. The integration layer provides the bridge.

---

## Data Flow

```
┌─────────────────────────────────────────────────────────┐
│              RESEARCH DOMAIN                             │
│                                                          │
│  Backtest Run                                           │
│    │                                                     │
│    ├──→ Strategy Logic                                  │
│    │      (generates decisions)                         │
│    │                                                     │
│    └──→ SignalEmitter                                   │
│           (emits raw strategy outputs)                  │
│                                                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ Raw Strategy Outputs
                     │ (timestamps, instruments, actions)
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│           INTEGRATION LAYER                              │
│                                                          │
│  SignalAdapter                                          │
│    ├── Validates raw outputs                            │
│    ├── Maps to Signal format                            │
│    ├── Applies position sizing                          │
│    ├── Applies risk checks                              │
│    └── Converts to execution-ready Signals              │
│                                                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ Validated Signals
                     │ (immutable, execution-ready)
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              EXECUTION DOMAIN                            │
│                                                          │
│  SignalConsumer                                         │
│    ├── Receives Signals                                 │
│    ├── Routes to ExecutionEngine                        │
│    └── Tracks signal → order mapping                    │
│                                                          │
│  ExecutionEngine                                        │
│    ├── Converts Signal → Order                          │
│    ├── Enforces risk limits                             │
│    └── Executes orders                                  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Key Components

### 1. SignalEmitter (Research Domain)

**Responsibility:** Emit raw strategy outputs from backtest runs.

**Location:** Research domain (in `src/engines` or `src/strategies`)

**Output:** Raw strategy decisions (timestamps, instruments, actions, quantities)

**Characteristics:**
- Emits during backtest execution
- May emit multiple signals per backtest
- Signals are deterministic (same backtest → same signals)
- No execution knowledge (doesn't know about orders/fills)

**Example Output:**
```python
{
    "timestamp": "2024-01-15T10:30:00",
    "instrument": "AAPL",
    "action": "buy",  # or "sell", "hold"
    "quantity": 100,
    "confidence": 0.85,  # optional
    "strategy_context": {...}  # optional
}
```

### 2. SignalAdapter (Integration Layer)

**Responsibility:** Transform raw strategy outputs into execution-ready Signals.

**Location:** Integration layer (new module `src/integration`)

**Process:**
1. Validate raw outputs (instrument, quantity, action)
2. Map action → SignalType (buy/sell/hold)
3. Apply position sizing rules (if needed)
4. Apply pre-execution risk checks
5. Create immutable Signal objects

**Safety Checks:**
- Validate instrument exists and is allowed
- Validate quantity is positive and reasonable
- Check signal doesn't violate position limits
- Verify signal is within risk bounds

**Configuration:**
- Position sizing rules
- Risk limits
- Instrument whitelist
- Signal filtering rules

**Failure Modes:**
- Invalid instrument → Reject signal
- Invalid quantity → Reject signal
- Risk limit exceeded → Reject signal
- Missing required fields → Reject signal

### 3. SignalConsumer (Execution Domain)

**Responsibility:** Receive validated Signals and route to ExecutionEngine.

**Location:** Execution domain (in `src/execution`)

**Process:**
1. Receive Signal from SignalAdapter
2. Submit to ExecutionEngine (convert to Order)
3. Track signal → order mapping (for auditability)
4. Handle execution results

**Characteristics:**
- Synchronous consumption (no async queues)
- Deterministic routing
- Maintains signal provenance

---

## Integration Patterns

### Pattern 1: Backtest → Paper Trading (Immediate)

**Use Case:** Run backtest, immediately execute signals in paper trading.

**Flow:**
1. Run backtest with strategy
2. Strategy emits signals during execution
3. Signals pass through SignalAdapter
4. SignalConsumer submits to PaperExecutionEngine
5. Orders execute at current/simulated prices

**Configuration:**
- Strategy parameters (fixed for backtest)
- Position sizing (configurable)
- Risk limits (session-level)

### Pattern 2: Backtest → Signal Storage → Execution (Deferred)

**Use Case:** Store signals from backtest, execute later.

**Flow:**
1. Run backtest, store signals as artifacts
2. Later: Load signals from artifacts
3. Signals pass through SignalAdapter
4. SignalConsumer submits to ExecutionEngine

**Configuration:**
- Signal storage format
- Signal replay rules

---

## Configuration Boundaries

### Fixed (Determined by Research)
- Strategy logic
- Backtest parameters (dates, universe)
- Raw signal generation (what strategy wants)

### User-Controlled (Integration Layer)
- Position sizing rules
- Signal filtering (which signals to execute)
- Risk limits (pre-execution checks)

### Execution-Controlled (Execution Domain)
- Order acceptance/rejection
- Execution price
- Fill details
- Position updates

---

## Failure Modes and Safety

### Signal Validation Failures
- **Invalid instrument:** Signal rejected, logged, backtest continues
- **Invalid quantity:** Signal rejected, logged, backtest continues
- **Missing fields:** Signal rejected, logged

### Risk Check Failures
- **Position limit exceeded:** Signal rejected, logged
- **Daily loss limit:** Signal rejected, session paused
- **Instrument not allowed:** Signal rejected, logged

### Execution Failures
- **Order rejection:** Handled by ExecutionEngine
- **Fill failures:** Handled by ExecutionEngine
- **Position update errors:** Handled by ExecutionEngine

### Safety Principles
1. **Fail fast:** Reject invalid signals immediately
2. **Fail loud:** All rejections logged with reasons
3. **Fail safe:** Invalid signals don't crash backtest
4. **Audit trail:** Signal → Order → Fill mapping preserved
5. **Deterministic:** Same inputs → same signal processing

---

## Separation of Concerns

### Research Domain Owns:
- Strategy logic
- Signal emission (raw outputs)
- Backtest execution

### Integration Layer Owns:
- Signal validation
- Signal transformation
- Pre-execution risk checks
- Configuration management

### Execution Domain Owns:
- Order creation
- Order execution
- Position management
- Execution risk limits

### What Each Domain Doesn't Know:

**Research doesn't know:**
- How signals become orders
- Execution prices
- Fill details
- Position state (except via signals)

**Execution doesn't know:**
- Strategy logic
- Why a signal was generated
- Backtest context
- Research metrics

**Integration doesn't know:**
- Strategy internals
- Execution engine internals
- Pricing logic

---

## Next Steps

1. Define SignalEmitter interface
2. Define SignalAdapter interface
3. Define SignalConsumer interface
4. Define configuration schemas
5. Implement basic adapter for Phase 1 strategies
6. Wire to PaperExecutionEngine

