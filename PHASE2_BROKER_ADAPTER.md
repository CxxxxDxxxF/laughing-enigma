# Phase 2: Broker Adapter Skeleton

**Status**: ✅ **COMPLETE**

## Overview

Phase 2 introduces the broker adapter abstraction layer, proving that the architecture can accept real broker feeds without changing rules, runner, or limits logic.

**Key Achievement**: Everything is injected, nothing is inferred. No broker-specific conditionals in business logic.

## Architecture

### 1. BrokerAdapter Interface

**Location**: `src/broker/adapter.py`

**Interface**: `BrokerAdapter`
- `get_account_metadata() -> AccountMetadata`
- `submit_order(...) -> BrokerOrder`
- `cancel_order(order_id) -> BrokerOrder`
- `flatten_positions(instrument) -> List[BrokerFill]`
- `poll_fills(since) -> List[BrokerFill]`
- `get_positions() -> Dict[str, float]`

**Key Principle**: All broker operations are abstracted. Business logic never checks broker names.

### 2. NullBrokerAdapter

**Location**: `src/broker/null.py`

**Purpose**: Deterministic mock broker for LIVE_DRY testing

**Behavior**:
- Returns fixed account metadata
- Accepts orders but never fills them
- No real broker API calls
- Deterministic and predictable

**Usage**:
```python
broker_adapter = NullBrokerAdapter(
    account_id="test_account",
    balance=50000.0,
    equity=50000.0,
    buying_power=50000.0,
    daily_loss_limit=-1000.0
)
```

### 3. Runner Integration

**Location**: `src/lifecycle/runner.py`

**Changes**:
- Added `broker_adapter: Optional[BrokerAdapter]` parameter
- Wires adapter into execution engine if provided
- No behavior change in SIM or LIVE_DRY (backward compatible)

**Usage**:
```python
result = run_portfolio_cycle(
    config=config,
    ...,
    limits_provider=limits_provider,
    broker_adapter=broker_adapter
)
```

### 4. Execution Engine Integration

**Location**: `src/execution/paper_engine.py`

**Changes**:
- Added `broker_adapter: Optional[Any]` parameter to `__init__`
- Stored as instance attribute
- Not yet used (Phase 2 is skeleton only)

**Future**: Execution engine will use broker_adapter for:
- Submitting orders to broker
- Polling fills from broker
- Getting positions from broker

## Architecture Validation

**Test**: `scripts/rehearse_broker_architecture.py`

**Validates**:
- ✅ LimitsProvider injected (no hardcoded limits)
- ✅ BrokerAdapter injected (no broker conditionals)
- ✅ Ruleset unchanged (broker-agnostic)
- ✅ Runner unchanged (broker-agnostic)
- ✅ Everything injected, nothing inferred

**Key Checks**:
- No `if broker_name == "topstep"` in business logic
- No `if firm == "apex"` in business logic
- Ruleset selection via `ruleset_type` is OK (configuration, not business logic)
- All broker operations go through adapter interface

## Key Principles

1. **Everything Injected, Nothing Inferred**
   - BrokerAdapter injected into runner
   - LimitsProvider injected into runner
   - No hardcoded broker logic

2. **No Broker-Specific Conditionals**
   - Business logic never checks broker names
   - All broker operations go through adapter interface
   - Ruleset selection is configuration, not business logic

3. **Skeleton Only (No Real Integration)**
   - NullBrokerAdapter is mock
   - BrokerLimitsProvider is placeholder
   - Real broker integration comes later

4. **Backward Compatible**
   - All existing code works unchanged
   - Optional parameters (broker_adapter, limits_provider)
   - No breaking changes

## Next Steps (Not Phase 2)

- Real broker API integration
- Authentication handling
- Retries, reconnections, websockets
- Order routing through broker
- Fill polling/streaming
- Position synchronization

## Testing

**Rehearsal Test**: `scripts/rehearse_broker_architecture.py`

**Results**:
- ✅ Architecture validation passed
- ✅ No broker-specific conditionals in business logic
- ✅ Everything injected correctly
- ✅ Cycle runs successfully with both provider and adapter

---

**Status**: ✅ Phase 2 complete. Architecture proven broker-ready without real integration.

