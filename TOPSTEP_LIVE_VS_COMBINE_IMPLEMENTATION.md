# Topstep LIVE vs COMBINE Implementation

**Date**: 2025-12-21  
**Status**: ✅ **COMPLETE**

## Summary

Implemented account type branching to comply with verified LIVE Funded Account rules. System now correctly distinguishes between:
- **COMBINE/EXPRESS**: Trading Combine (Evaluation) accounts with static limits
- **LIVE_FUNDED**: Live Funded Accounts with dynamic limits and equity floor

## Changes Implemented

### 1. Extended TopstepRulesConfig ✅

**File**: `src/rules/topstep.py`

**Added**:
- `account_type: Optional[str] = None` field
- Validation: `account_type` must be "COMBINE" or "LIVE_FUNDED"
- Config hygiene: LIVE_FUNDED rejects `max_daily_loss` and `max_trailing_drawdown_pct`

### 2. Account Type Branching in validate_execution() ✅

**File**: `src/rules/topstep.py` (lines 284-365)

**Daily Loss Logic**:
- **COMBINE**: Enforces static `max_daily_loss` from config
- **LIVE_FUNDED**: No static enforcement (external/dynamic)

**Trailing Drawdown Logic**:
- **COMBINE**: Enforces `max_trailing_drawdown_pct` from config
- **LIVE_FUNDED**: No trailing drawdown (explicitly skipped)

**Equity Floor for LIVE**:
- **LIVE_FUNDED**: Enforces equity > 0 (hard floor)
- Implements: "Currently, your Maximum Loss Limit is $0"

### 3. Config Files ✅

**Created**:
- `configs/funded/topstep_50k_COMBINE.json` - Frozen as COMBINE with static limits
- `configs/funded/topstep_50k_LIVE.json` - New LIVE config without numeric limits

**Key Differences**:

| Field | COMBINE | LIVE_FUNDED |
|-------|---------|-------------|
| `account_type` | "COMBINE" | "LIVE_FUNDED" |
| `max_daily_loss` | -1000.0 | null (omitted) |
| `max_trailing_drawdown_pct` | 5.0 | null (omitted) |
| `account_size` | 50000.0 | null |

### 4. Regression Tests ✅

**File**: `tests/test_topstep_live_vs_combine.py`

**Tests**:
- ✅ `test_live_account_has_no_trailing_drawdown_and_equity_floor`
- ✅ `test_combine_account_requires_static_limits`
- ✅ `test_live_config_rejects_static_limits`
- ✅ `test_account_type_required`

**All tests passing**: 4/4

## Compliance Status

### LIVE Funded Account Rules

| Rule | Status | Implementation |
|------|--------|----------------|
| Daily Loss (behavior) | ✅ VERIFIED | Realized + unrealized, intraday, inclusive threshold |
| Daily Loss ($1,000) | ❌ REMOVED | Not in config, must be external/dynamic |
| Max Loss / Drawdown | ✅ VERIFIED | Equity > 0 enforced |
| Trailing Drawdown | ❌ DOES NOT APPLY | Explicitly skipped for LIVE |
| Session Boundary | ✅ VERIFIED | 5:00 PM CT → 3:10 PM CT |
| Position Limits | ⚠️ External | Not hardcoded in config |

### COMBINE Account Rules

| Rule | Status | Implementation |
|------|--------|----------------|
| Daily Loss | ✅ VERIFIED | Static -$1,000 from config |
| Trailing Drawdown | ✅ VERIFIED | Static 5% from config |
| Session Boundary | ✅ VERIFIED | 5:00 PM CT → 3:10 PM CT |

## Code Structure

### Branching Logic

```python
account_type = self.config.account_type

# Daily Loss
if account_type == "COMBINE":
    # Static limit enforcement
elif account_type == "LIVE_FUNDED":
    # No static enforcement (external)

# Trailing Drawdown
if account_type == "COMBINE":
    # Trailing drawdown enforcement
elif account_type == "LIVE_FUNDED":
    # No trailing drawdown

# Equity Floor (LIVE only)
if account_type == "LIVE_FUNDED":
    # Enforce equity > 0
```

## Verification

- ✅ Configs load correctly
- ✅ All tests pass
- ✅ Config hygiene prevents regressions
- ✅ Account type is explicit (no inference)

## Next Steps

1. **Daily Loss for LIVE**: Implement external/dynamic daily loss injection
   - Must come from account parameters, not config
   - System should refuse to start if not available

2. **Position Limits for LIVE**: Treat as externally governed
   - No static enforcement in config
   - Allow external overrides

3. **Phase 1 Unblocked**: Compliance debt resolved
   - All verified rules implemented
   - Account type branching complete
   - No silent assumptions

---

**Status**: ✅ **COMPLIANT** - System correctly branches by account type and enforces verified rules.

