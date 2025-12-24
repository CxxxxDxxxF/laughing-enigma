# Topstep 50k LIVE Funded Account Rules - VERIFIED

**Source**: "LIVE funded account TRADING rules"  
**Last Updated**: Dec 3, 2025  
**Applies To**: Live Funded Accounts (NOT Combine / Evaluation)  
**Verification Date**: 2025-12-21  
**Status**: ✅ **VERIFIED** (with required architectural changes)

---

## Critical Distinction

**LIVE Funded Accounts ≠ Trading Combine (Evaluation)**

- **LIVE Funded**: Rules verified in this document
- **Trading Combine/Evaluation**: Different rules (see `topstep_50k_RULES.md`)

**⚠️ System must branch by account type for compliance.**

---

## Rule 1: Daily Loss Limit (Behavior)

### ✅ VERIFIED - Behavior and Enforcement

**Verbatim Quote**:
> "Trader may not hit or exceed the Daily Loss Limit … The Daily Loss Limit is calculated intraday on both realized and unrealized net P&L, including commissions and fees."

> "Hitting or exceeding the Daily Loss Limit will suspend Trader's ability to trade for the remainder of the then current trading session, which resets for the next trading session (as set forth here)."

> "If your Net P&L reaches or exceeds this limit during the trading day (defined as 5:00 PM CT to 3:10 PM CT), your account will enter a soft breach."

> "This lockout is not a rule violation."

### What is VERIFIED

✅ Daily loss uses realized + unrealized PnL  
✅ Includes fees and commissions  
✅ Evaluated intraday  
✅ Threshold is inclusive (hit or exceed)  
✅ Reset occurs at session boundary  
✅ Trading day defined as 5:00 PM CT → 3:10 PM CT  
✅ Enforcement is a soft breach (lockout, flattening)

### What is NOT VERIFIED

🚫 **The dollar amount ($1,000) is NOT stated anywhere in this document**

**Implication**:
- This document does not define the numeric Daily Loss Limit
- The value is account-specific and dynamic
- This text governs behavior, not the numeric cap

### Required Encoding Change

❌ **Config must NOT hardcode $1,000 for LIVE accounts**

✅ **Instead**:
- Daily loss must be sourced dynamically from account parameters
- Enforcement logic is correct
- Static config value is invalid for LIVE

### Final Status

- **Daily Loss Rule (behavior)**: ✅ VERIFIED
- **Daily Loss Amount ($1,000)**: ❌ UNVERIFIED for LIVE → **REMOVE from LIVE config**

---

## Rule 2: Maximum Loss Limit (Trailing Drawdown)

### ✅ VERIFIED - AND RESOLVED

**Verbatim Quote**:
> "Trader may not hit or exceed the Maximum Loss Limit … Currently, your Maximum Loss Limit is $0."

> "For the remainder of your Live Funded Account, you will need to make sure your account balance stays above $0 (positive)."

### What This Means

✅ **There is NO trailing drawdown in LIVE**  
✅ **There is NO percentage**  
✅ **There is NO $2,000 or $2,500**  
✅ **This is a hard floor at zero**

**This resolves the $2,000 vs $2,500 issue conclusively.**

### Required Encoding Change

❌ **Remove trailing drawdown logic for LIVE**  
✅ **Enforce equity > 0 invariant**  
✅ **Immediate account closure if breached**

### Final Status

- **Maximum Loss Limit (LIVE)**: ✅ VERIFIED
- **Trailing Drawdown**: ❌ **DOES NOT APPLY (REMOVE)**

---

## Rule 3: Trading Day / Session Definition

### ✅ VERIFIED

**Verbatim Quote**:
> "trading day (defined as 5:00 PM CT to 3:10 PM CT)"

> "All positions MUST be closed prior to 3:10 PM CT or prior to the market close of that product, whichever is sooner."

> "Your open positions will be closed (flattened)."

### What is VERIFIED

✅ Session start: 5:00 PM CT  
✅ Session end: 3:10 PM CT  
✅ Mandatory flattening  
✅ Daily loss resets at session boundary

### Final Status

**Session Boundary Rule**: ✅ VERIFIED

**Note**: Your `TradingDayBoundary` implementation is correct.

---

## Rule 4: Position Limits

### ⚠️ PARTIALLY VERIFIED

**Verbatim Quote**:
> "Once you reach $100,000, you can contact the Trade Desk to request higher contract limits."

> "Path to Reduction helps manage risk by tightening limits…"

### What This Means

✅ Position limits exist  
✅ They are:
- Dynamic
- Account-specific
- Risk-managed
- They are NOT statically defined

### Required Encoding Change

❌ **Static position limits should not be enforced in config**  
✅ **System must allow**:
- External overrides
- Risk-manager adjustments
✅ **Treat limits as externally governed**

### Final Status

- **Static Position Limits**: ❌ REMOVE
- **Dynamic/Risk-Based Limits**: ✅ VERIFIED (external)

---

## Final Compliance Summary (LIVE FUNDED)

| Rule | Status | Action |
|------|--------|--------|
| Daily Loss (behavior) | ✅ VERIFIED | Keep |
| Daily Loss ($1,000) | ❌ UNVERIFIED | **Remove from LIVE** |
| Max Loss / Drawdown | ✅ VERIFIED | Enforce equity > 0 |
| Trailing Drawdown | ❌ DOES NOT APPLY | **Remove** |
| Session Boundary | ✅ VERIFIED | Keep |
| Position Limits | ⚠️ External | Do not hardcode |

---

## Critical Architectural Implication

**Your current logic must branch by account type:**

### LIVE_FUNDED
- Dynamic daily loss (not hardcoded)
- Equity floor = 0 (no trailing drawdown)
- No trailing drawdown
- No static position caps

### EXPRESS / COMBINE
- Static daily loss (config-defined)
- Trailing drawdown applies
- Config-defined values allowed

**⚠️ If you do not branch, you are non-compliant.**

---

## Required System Changes

1. **Remove numeric daily loss from LIVE configs**
2. **Remove trailing drawdown from LIVE configs**
3. **Add explicit branch in rules engine for LIVE vs EXPRESS/COMBINE**
4. **Enforce equity > 0 for LIVE (no trailing drawdown)**
5. **Make daily loss amount dynamic for LIVE (not config-defined)**

---

**Next Steps**: Update configs and rules engine to implement account type branching.

