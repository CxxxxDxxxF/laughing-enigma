# Phase 1: Limits & Broker Abstraction

**Status**: ✅ **COMPLETE**

## Overview

Phase 1 introduces the abstraction layer for broker-agnostic limit management and pins critical LIVE invariants. This enables:
- **LIVE_DRY**: Deterministic testing with fixed limits
- **LIVE**: Broker API integration (placeholder)
- **Multi-firm support**: Topstep, Apex, etc. without code duplication

## Architecture

### 1. LimitsProvider Abstraction

**Location**: `src/limits/`

**Interface**: `LimitsProvider`
- `get_daily_loss_limit(timestamp) -> float`
- `get_trading_session(timestamp) -> TradingSession`
- `is_trading_allowed(timestamp) -> bool`

**Implementations**:
- `DeterministicLimitsProvider`: Fixed limits for LIVE_DRY testing
- `BrokerLimitsProvider`: Placeholder for LIVE broker integration

**Usage**:
```python
# LIVE_DRY: Deterministic
provider = DeterministicLimitsProvider(
    daily_loss_limit=-1000.0,
    day_boundary=TradingDayBoundary.from_config(config.day_boundary_config)
)

# LIVE: Broker (placeholder)
provider = BrokerLimitsProvider(broker_name="topstep", account_id="...")
```

### 2. Runner Integration

**Location**: `src/lifecycle/runner.py`

**Changes**:
- Added `limits_provider: Optional[LimitsProvider]` parameter
- Backward compatible: still accepts `live_daily_loss_limit` for direct injection
- Resolves limit from provider when available

**Migration Path**:
1. Old: `live_daily_loss_limit=-1000.0`
2. New: `limits_provider=DeterministicLimitsProvider(-1000.0)`

### 3. LIVE Invariants (Pinned)

**Location**: `src/rules/live_invariants.py`

**Status**: TODO stubs (not implemented)

**Pinned Contracts**:
- **Protective Stops**: All positions must have protective stops
- **Auto-Flatten**: Positions must be flattened before 3:10 PM CT
- **Holiday Schedule**: Trading not allowed on firm-defined holidays

**Why Stubs**:
- Prevents architectural leaks before broker integration
- Documents requirements clearly
- Makes it impossible to "forget" these requirements

### 4. Multi-Firm Pattern

**Current**: Topstep-specific rules in `src/rules/topstep.py`

**Pattern for Adding New Firms**:

1. **Create Firm-Specific Ruleset**:
   ```python
   # src/rules/apex.py
   @dataclass
   class ApexRulesConfig:
       account_type: Optional[str] = None  # "EVALUATION" | "LIVE_FUNDED"
       # ... firm-specific fields
   
   class ApexRuleset(Ruleset):
       # ... firm-specific validation logic
   ```

2. **Account-Type Branching**:
   - Use string field: `account_type: "COMBINE" | "LIVE_FUNDED" | "EVALUATION" | ...`
   - Branch logic in `validate_execution()` based on account_type
   - Keep firm-specific logic isolated

3. **Limits Injection**:
   - Limits come from `LimitsProvider`, not config
   - Config only has static limits for evaluation accounts
   - LIVE accounts always use injected limits

4. **Rules Isolation**:
   - Each firm has its own ruleset class
   - No shared logic between firms (copy patterns, not code)
   - Common abstractions (LimitsProvider, TradingSession) are shared

**Example for Apex**:
```python
# Config
{
    "ruleset_type": "apex",
    "ruleset_config": {
        "account_type": "LIVE_FUNDED",
        # No static limits for LIVE
    }
}

# Runner
provider = DeterministicLimitsProvider(-1000.0)  # Or BrokerLimitsProvider
ruleset = ApexRuleset(ApexRulesConfig(**config.ruleset_config))
ruleset.validate_execution(..., live_daily_loss_limit=provider.get_daily_loss_limit(ts))
```

## Key Principles

1. **Limits are Injected, Not Inferred**
   - No hardcoded limits in rulesets
   - Limits come from provider (deterministic or broker)
   - Config only has static limits for evaluation accounts

2. **Account-Type Branching is Generic**
   - String field: `account_type`
   - Branch logic in ruleset's `validate_execution()`
   - Each firm defines its own account types

3. **Firm-Specific Rules Stay Isolated**
   - One ruleset class per firm
   - No shared business logic
   - Copy patterns, not code

4. **LIVE Invariants are Pinned**
   - Stubs prevent architectural leaks
   - Clear contracts for future implementation
   - Cannot "forget" requirements

## Next Steps (Not Phase 1)

- Broker API integration (BrokerLimitsProvider)
- Protective stop enforcement
- Auto-flatten implementation
- Holiday calendar
- Apex ruleset implementation

## Testing

All existing tests pass. New abstraction is backward compatible.

**Stress Tests**: `scripts/stress_live_daily_loss.py` validates LIVE enforcement.

---

**Status**: ✅ Phase 1 complete. Architecture ready for broker integration.

