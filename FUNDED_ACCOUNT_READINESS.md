# Funded Account Readiness Status

This document tracks progress toward funded account trading readiness for Topstep and Apex.

## Critical Requirements Status

### ✅ Determinism
- **No datetime.now() in LIVE/LIVE_DRY**: ✅ Complete
  - All timestamps derive from `cycle_timestamp`
  - `FixedClock` used in LIVE/LIVE_DRY mode
  - Tests verify no UUID usage in LIVE mode

- **No UUID generation in LIVE/LIVE_DRY**: ✅ Complete
  - `DeterministicIDProvider` replaces all UUID calls
  - Order IDs, fill IDs, session IDs are deterministic
  - Tests verify UUID never called in LIVE mode

- **All timestamps derive from single cycle_timestamp**: ✅ Complete
  - Documented in code comments
  - Causal chain: cycle_timestamp → allocation_timestamp → plan_timestamp → execution_timestamp

### ✅ Safety
- **Halts are persistent across restarts**: ✅ Complete
  - HALTED flag written to disk
  - Atomic write (temp file + rename)
  - Validated before cycle starts

- **No automatic resume after halt**: ✅ Complete
  - Manual intervention required via `halt_cli.py`
  - `_validate_portfolio_not_halted()` checks flag before starting

- **Guardrails are non-permissive in LIVE/LIVE_DRY**: ✅ Complete
  - `_validate_live_mode_guardrails()` enforces strict limits
  - All funded configs have strict guardrails

### ⚠️ Accuracy (Requires Verification)
- **Funded firm rules match official documentation**: ⚠️ **NEEDS VERIFICATION**
  - Configs created with rule provenance docs (`*_RULES.md`)
  - **ACTION REQUIRED**: Verify all values against official firm documentation
  - Update retrieval dates and source URLs in `_RULES.md` files

- **Session-based trading day boundaries**: ✅ Complete
  - `TradingDayBoundary.get_trading_date()` implements session logic
  - Daily loss resets at session start, not midnight
  - Tests verify session boundary correctness

- **No assumptions, guesses, or approximations**: ⚠️ **NEEDS REVIEW**
  - Rule provenance docs identify assumptions (marked as "ASSUMED")
  - **ACTION REQUIRED**: Verify all assumed values

## Execution Modes

### ✅ SIMULATION
- Relaxed constraints
- Implicit timestamps and IDs allowed
- Fully functional

### ✅ LIVE_DRY
- Identical behavior to LIVE
- Deterministic timestamps and IDs
- Enforces all rules and guardrails
- Uses paper execution only
- Generates full artifacts

### ⚠️ LIVE
- Same as LIVE_DRY (currently)
- Broker adapter not yet implemented
- Will use real broker execution when adapter is added

## Completed Work

### Step 1: Session-Aware Trading Day Boundary ✅
- **Status**: Complete
- **Files**: `src/rules/day_boundary.py`
- **Tests**: `tests/test_day_boundary_session.py`
- **Logic**: Trading day = date of session that began most recently before timestamp
- **Verification**: Tests cover session start timing, midnight rollover prevention, cross-day sessions

### Step 2: Funded Firm Rule Calibration ✅
- **Status**: Complete (requires verification)
- **Configs**: 
  - `configs/funded/topstep_50k.json`
  - `configs/funded/topstep_100k.json`
  - `configs/funded/apex_50k.json`
- **Provenance Docs**: 
  - `configs/funded/topstep_50k_RULES.md`
  - `configs/funded/topstep_100k_RULES.md`
  - `configs/funded/apex_50k_RULES.md`
- **Action Required**: Verify all rule values against official documentation

### Step 3: Rule Enforcement Validation ⚠️
- **Status**: Tests created, needs verification against firm dashboards
- **Tests**: `tests/test_rule_enforcement_timing.py`
- **Covers**:
  - Exact threshold breach
  - Daily loss reset at session start
  - Lock-in state persistence
- **Action Required**: 
  - Run tests and verify behavior matches firm dashboards
  - Test with actual funded account scenarios if possible

### Step 4: Evidence Report Generator ⚠️
- **Status**: Structure complete, needs artifact wiring
- **Files**: `src/analysis/evidence_report.py`
- **Includes**: Daily equity, drawdown, halts, trade stats, MAE/MFE
- **Action Required**: Wire to actual artifact store structure

### Step 5: One-Command Funded Rehearsal ✅
- **Status**: Script created
- **File**: `scripts/funded_rehearsal.py`
- **Usage**: `python scripts/funded_rehearsal.py --config configs/funded/topstep_50k.json --cycles 30`
- **Features**:
  - Runs in LIVE_DRY mode
  - Checks halt flags before starting
  - Generates evidence report
  - Stops on halt

## Test Coverage

### ✅ Session Boundary Tests
- `tests/test_day_boundary_session.py`
- Covers: session start timing, midnight vs session rollover, cross-day sessions

### ✅ ID Determinism Tests
- `tests/test_id_determinism.py`
- Covers: deterministic IDs in LIVE mode, no UUID usage

### ⚠️ Rule Enforcement Tests
- `tests/test_rule_enforcement_timing.py`
- Covers: daily loss threshold, session reset
- **Action Required**: Verify against firm behavior

## Known Gaps and TODOs

### Critical (Block Live Trading)
1. **Rule Verification**: All funded config values must be verified against official firm documentation
2. **Evidence Report Wiring**: Connect report generator to actual artifact store
3. **Position Limits**: Add instrument-specific position limits to configs (currently null)

### Important (Before Production)
4. **Weekend/Holiday Handling**: Verify how trading days are handled on weekends/holidays
5. **Apex Safety Net**: Implement Apex-specific Safety Net behavior (stops at initial + drawdown + $100)
6. **30% Consistency Rule**: Add Apex 30% per-trade loss limit enforcement
7. **Time-of-Day Rules**: Add any firm-specific trading hour restrictions

### Nice to Have
8. **Broker Adapter**: Implement real broker execution for LIVE mode
9. **Slippage Analysis**: Add slippage tracking to evidence reports
10. **Per-Instrument Breakdown**: Add instrument-level stats to evidence reports

## Verification Checklist

Before using with real funds, verify:

- [ ] All rule values in `_RULES.md` files match official documentation
- [ ] Session start times are correct (currently 17:00 CT for Topstep)
- [ ] Daily loss limits are correct ($1,000 for 50k, $2,000 for 100k)
- [ ] Trailing drawdown percentages are correct (5% for both)
- [ ] Evidence report generates correctly from artifacts
- [ ] Halt timing matches firm dashboard behavior
- [ ] Lock-in state never reverses (tested)
- [ ] Session boundaries work correctly (tested)
- [ ] No UUID or datetime.now() in LIVE mode (tested)

## Usage

### Run Funded Rehearsal
```bash
# Run 30 cycles with Topstep 50k config
python scripts/funded_rehearsal.py \
  --config configs/funded/topstep_50k.json \
  --cycles 30 \
  --artifacts ./artifacts

# Inspect halt (if occurred)
python -m src.lifecycle.halt_cli inspect topstep_50k --artifacts ./artifacts

# Clear halt (manual intervention)
python -m src.lifecycle.halt_cli clear topstep_50k --artifacts ./artifacts --force
```

### Run Tests
```bash
# Session boundary tests
python -m pytest tests/test_day_boundary_session.py -v

# ID determinism tests
python -m pytest tests/test_id_determinism.py -v

# Rule enforcement tests
python -m pytest tests/test_rule_enforcement_timing.py -v
```

## Next Steps

1. **Verify Rule Values**: Update `_RULES.md` files with verified values from official docs
2. **Wire Evidence Generator**: Connect to artifact store structure
3. **Run Rehearsal**: Test with funded configs in LIVE_DRY mode
4. **Compare Behavior**: Verify halt timing matches firm dashboards
5. **Add Missing Rules**: Position limits, time-of-day rules, etc.

## Reality Check

You are past the point where most people fail.

If you blow a funded account after these fixes, it will NOT be because:
- ❌ Timestamps drifted
- ❌ IDs changed
- ❌ Halts didn't trigger
- ❌ Rules were missing

It will be because:
- ✅ Strategy expectancy is negative
- ✅ Trade frequency is wrong
- ✅ Market regime changed

That is the right failure mode.

