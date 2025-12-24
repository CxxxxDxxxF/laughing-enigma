# Phase 2.5: Invariant Lockdown & Red-Team Audit

**Status**: ✅ **COMPLETE**

## Overview

Phase 2.5 locks architectural invariants to prevent regressions and freeze correctness. The system is functionally complete at this layer, and this phase ensures that future changes cannot silently break correctness, compliance, or determinism.

## Architecture Invariants

### Part 1: Invariant Matrix (Tests)

**Location**: `tests/test_architectural_invariants.py`

**Purpose**: Enforce architectural truths through binary tests (PASS or FAIL).

#### Ruleset Invariants

1. **Must NOT import broker.* modules**
   - Rulesets must be broker-agnostic
   - Any import of `broker.*` is a violation
   - Test: `test_ruleset_must_not_import_broker`

2. **Must NOT import limits.provider**
   - Rulesets receive limits via method parameters, not direct imports
   - Test: `test_ruleset_must_not_import_limits_provider`

3. **Must NOT reference broker adapters directly**
   - Rulesets must not contain code that directly uses `BrokerAdapter`
   - Test: `test_ruleset_must_not_reference_broker_adapters_directly`

4. **Must NOT reference LimitsProvider directly**
   - Rulesets receive limits via method parameters, not direct provider access
   - Test: `test_ruleset_must_not_reference_limits_provider_directly`

5. **Must consume limits via parameters only**
   - Rulesets receive `live_daily_loss_limit` as a parameter
   - Test: `test_ruleset_consumes_limits_via_parameters`

#### Execution Engine Invariants

1. **Must NOT infer limits**
   - Execution engine does not calculate or infer limits from config
   - Test: `test_execution_engine_must_not_infer_limits`

2. **Must NOT branch on account type**
   - Execution engine is account-type agnostic
   - Test: `test_execution_engine_must_not_branch_on_account_type`

3. **Must NOT call broker methods unless injected**
   - Execution engine only uses `broker_adapter` if it's provided (injected)
   - Test: `test_execution_engine_must_not_call_broker_unless_injected`

#### Runner Invariants

1. **Must accept LimitsProvider parameter**
   - Runner must have `limits_provider` parameter for injection
   - Test: `test_runner_must_accept_limits_provider`

2. **Must accept BrokerAdapter parameter**
   - Runner must have `broker_adapter` parameter for injection
   - Test: `test_runner_must_accept_broker_adapter`

3. **Must NOT contain firm-specific rules**
   - Runner must not have hardcoded Topstep or Apex business logic
   - Test: `test_runner_must_not_contain_firm_specific_rules`

4. **Must NOT infer LIVE behavior from config**
   - Runner must use explicit `account_type`, not infer from missing fields
   - Test: `test_runner_must_not_infer_live_behavior_from_config`

#### LIVE_FUNDED Invariants

1. **Missing limits → hard fail**
   - LIVE_FUNDED accounts must fail immediately if `live_daily_loss_limit` is None
   - Test: `test_live_funded_missing_limits_must_hard_fail`

2. **Equity ≤ 0 → HALT**
   - LIVE_FUNDED accounts must halt when equity reaches zero or goes negative
   - Test: `test_live_funded_equity_zero_or_negative_must_halt`

3. **Trailing drawdown logic must NOT execute**
   - LIVE_FUNDED accounts have no trailing drawdown
   - Test: `test_live_funded_must_not_execute_trailing_drawdown_logic`

#### LIVE_DRY Invariants

1. **Must be fully deterministic**
   - Same inputs → same outputs
   - Test: `test_live_dry_must_be_deterministic`

2. **Must use DeterministicLimitsProvider**
   - LIVE_DRY mode requires deterministic limits, not broker limits
   - Test: `test_live_dry_must_use_deterministic_limits_provider`

3. **Must use NullBrokerAdapter**
   - LIVE_DRY mode requires null broker adapter, not real broker
   - Test: `test_live_dry_must_use_null_broker_adapter`

#### COMBINE Invariants

1. **Must ignore LIVE-only parameters**
   - COMBINE accounts use static limits from config, not `live_daily_loss_limit`
   - Test: `test_combine_must_ignore_live_only_parameters`

2. **Must require static limits**
   - COMBINE accounts must have `max_daily_loss` and `max_trailing_drawdown_pct` in config
   - Test: `test_combine_must_require_static_limits`

3. **Must enforce trailing drawdown**
   - COMBINE accounts must check and enforce trailing drawdown limits
   - Test: `test_combine_must_enforce_trailing_drawdown`

### Part 2: Red-Team Misconfiguration Rehearsal

**Location**: `tests/test_red_team_misconfiguration.py`

**Purpose**: Verify that misconfigurations fail predictably and explicitly.

#### Scenarios

1. **LIVE_FUNDED without LimitsProvider → must fail immediately**
   - Test: `test_live_funded_without_limits_provider_must_fail`
   - Expected: RuntimeError with clear message about missing limits

2. **LIVE_FUNDED with trailing drawdown configured → config error**
   - Test: `test_live_funded_with_trailing_drawdown_config_must_fail`
   - Expected: ValueError during config initialization

3. **LIVE_FUNDED with static daily loss → config error**
   - Test: `test_live_funded_with_static_daily_loss_must_fail`
   - Expected: ValueError during config initialization

4. **COMBINE with BrokerAdapter injected → ignored**
   - Test: `test_combine_with_broker_adapter_injected_is_ignored`
   - Expected: No error (COMBINE simply doesn't use it)

5. **COMBINE without static limits → must fail**
   - Test: `test_combine_without_static_limits_must_fail`
   - Expected: RuntimeError during validate_execution

6. **SIM mode with LimitsProvider → ignored**
   - Test: `test_sim_mode_with_limits_provider_is_ignored`
   - Expected: No error (SIM simply doesn't use it)

7. **Ruleset attempting to import broker code → fails**
   - Test: `test_ruleset_attempting_to_import_broker_code_fails`
   - Expected: Invariant test catches this (no broker imports found)

## Interface Freeze

### Frozen Interfaces

The following interfaces are **FROZEN** as of Phase 2.5:

1. **LimitsProvider** (`src/limits/provider.py`)
   - `get_daily_loss_limit(timestamp) -> Optional[float]`
   - `get_trading_hours(trading_date) -> Optional[TradingSession]`
   - Any future changes must:
     - Update invariant tests
     - Be additive only (no breaking refactors)
     - Maintain backward compatibility

2. **BrokerAdapter** (`src/broker/adapter.py`)
   - `get_account_metadata() -> AccountMetadata`
   - `submit_order(...) -> BrokerOrder`
   - `cancel_order(order_id) -> BrokerOrder`
   - `flatten_positions(instrument) -> List[BrokerFill]`
   - `poll_fills(since) -> List[BrokerFill]`
   - Any future changes must:
     - Update invariant tests
     - Be additive only (no breaking refactors)
     - Maintain backward compatibility

3. **Ruleset Public APIs** (`src/rules/base.py`, `src/rules/topstep.py`)
   - `validate_execution(...) -> List[RulesViolation]`
   - Parameter signatures (especially `live_daily_loss_limit`)
   - Any future changes must:
     - Update invariant tests
     - Be additive only (no breaking refactors)
     - Maintain backward compatibility

### Change Policy

**For any change to frozen interfaces:**

1. **Update invariant tests first**
   - Add new tests for new invariants
   - Update existing tests if behavior changes
   - Ensure all tests pass

2. **Be additive only**
   - No breaking refactors
   - No removal of methods or parameters
   - New methods/parameters must be optional

3. **Maintain backward compatibility**
   - Existing code must continue to work
   - Deprecation warnings are acceptable
   - Migration path must be clear

4. **Document changes**
   - Update this document
   - Add migration guide if needed
   - Update API documentation

## Test Results

**Invariant Tests**: ✅ 21/21 passing
- Ruleset invariants: 5/5
- Execution engine invariants: 3/3
- Runner invariants: 4/4
- LIVE_FUNDED invariants: 3/3
- LIVE_DRY invariants: 3/3
- COMBINE invariants: 3/3

**Red-Team Tests**: ✅ 7/7 passing
- All misconfiguration scenarios fail predictably

## Success Criteria

✅ **Invariants are enforced by tests**
- All 21 invariant tests passing
- Binary assertions (PASS or FAIL)
- No warnings or skips

✅ **Red-team failures are intentional and predictable**
- All 7 misconfiguration scenarios fail as expected
- Error messages are clear
- No silent passes

✅ **No business logic changed**
- Only test code added
- No changes to rulesets, runner, or execution engine
- Architecture remains unchanged

✅ **Architecture is regression-resistant**
- Interface freeze documented
- Change policy established
- Future changes must update tests

## Next Steps

Phase 2.5 is complete. The system is now protected against architectural regressions. Future changes must:

1. Pass all invariant tests
2. Follow the interface freeze policy
3. Update tests for any new invariants
4. Maintain backward compatibility

---

**Status**: ✅ Phase 2.5 complete. Architecture locked and regression-resistant.

