# Topstep 50k Rules Verification Checklist

**Verification Date**: 2025-12-21  
**Status**: ⚠️ **BLOCKING - Manual Verification Required**

---

## Verification Checklist

### Rule 1: Daily Loss Limit

- [ ] **Access Source**: Open https://help.topstep.com/en/articles/8284207-what-is-the-daily-loss-limit-and-what-happens-if-i-exceed-it
- [ ] **Find Section**: Locate section about 50k Trading Combine daily loss limit
- [ ] **Extract Quote**: Copy verbatim quote confirming $1,000
- [ ] **Verify Calculation**: Confirm calculation method (realized + unrealized from session start)
- [ ] **Verify Enforcement**: Confirm enforcement behavior (auto-liquidation, pause until next session)
- [ ] **Verify Reset**: Confirm reset timing (at session start, not midnight)
- [ ] **Record Quote**: Add verbatim quote to verification document
- [ ] **Update Status**: Mark as ✅ VERIFIED or ❌ REMOVED

**Result**: ⚠️ **PENDING** - Cannot verify without direct access to source

---

### Rule 2: Trailing Drawdown (Maximum Loss Limit)

- [ ] **Access Source**: Open https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit
- [ ] **Find Section**: Locate section about 50k account maximum loss limit
- [ ] **Extract Quote**: Copy verbatim quote with exact amount or percentage
- [ ] **Resolve Inconsistency**: Determine if it's $2,000, $2,500, or 5%
- [ ] **Verify Trailing Behavior**: Confirm trailing adjusts with high-water mark
- [ ] **Verify Lock-In**: Confirm lock-in behavior (once equity exceeds initial)
- [ ] **Record Quote**: Add verbatim quote to verification document
- [ ] **Update Status**: Mark as ✅ VERIFIED or ❌ REMOVED
- [ ] **Update Config**: If value differs from config, update config file

**Result**: ⚠️ **PENDING - INCONSISTENCY TO RESOLVE**
- Current claim: $2,500 (5% of $50,000)
- Source quote says: $2,000 below highest balance
- **Action**: Resolve which is correct

---

### Rule 3: Trading Day / Session Definition

- [ ] **Access Source**: Open https://help.topstep.com/en/articles/8284197-trading-combine-parameters
- [ ] **Find Section**: Locate section about session start time
- [ ] **Extract Quote**: Copy verbatim quote confirming 5:00 PM CT
- [ ] **Verify Timezone**: Confirm Central Time (America/Chicago)
- [ ] **Verify Reset**: Confirm daily loss resets at session start, not midnight
- [ ] **Verify Flat Requirement**: Confirm "flat by 3:10 PM CT" requirement
- [ ] **Record Quote**: Add verbatim quote to verification document
- [ ] **Update Status**: Mark as ✅ VERIFIED or ❌ REMOVED

**Result**: ⚠️ **PENDING** - Cannot verify without direct access to source

---

### Rule 4: Position Limits

- [ ] **Check All Sources**: Review all Topstep documentation for position limits
- [ ] **Check Dashboard**: If accessible, check Topstep dashboard for position limit settings
- [ ] **Determine Status**: 
  - If no limits found: Mark as ✅ VERIFIED (no position limits)
  - If limits found: Document them
- [ ] **Update Config**: If limits exist, add to config file
- [ ] **Record Finding**: Add verification notes to verification document
- [ ] **Update Status**: Mark as ✅ VERIFIED or ❌ REMOVED

**Result**: ⚠️ **PENDING** - Cannot verify without direct access to sources

---

## Verification Notes

### Issues Identified

1. **Cannot Access Official Sources Directly**
   - Web search does not provide verbatim quotes from help.topstep.com
   - Manual access to URLs required for verification

2. **Inconsistency in Trailing Drawdown**
   - Source quote says "$2,000 below highest balance"
   - But 5% of $50,000 = $2,500
   - Need to resolve which is correct

3. **No Verifiable Quotes**
   - All rules need verbatim quotes from official sources
   - Current status cannot be verified without direct access

### Required Actions

1. **Manual Verification**: Access each source URL and extract verbatim quotes
2. **Resolve Inconsistency**: Determine correct trailing drawdown value
3. **Update Documentation**: Add verified quotes to verification documents
4. **Update Rules File**: Mark rules as ✅ VERIFIED or ❌ REMOVED
5. **Update Config**: If verified values differ, update config files

### Success Criteria

- [ ] All rules have verbatim quotes from official sources
- [ ] All inconsistencies resolved
- [ ] All "ASSUMED" values removed or verified
- [ ] Config values match verified rules
- [ ] No blocking issues remain

---

## Status Summary

| Rule | Status | Blocking Issue |
|------|--------|----------------|
| Daily Loss Limit | ⚠️ UNVERIFIED | Cannot access official source |
| Trailing Drawdown | ⚠️ INCONSISTENT | $2,000 vs $2,500 conflict |
| Session Start Time | ⚠️ UNVERIFIED | Cannot access official source |
| Position Limits | ⚠️ UNVERIFIED | Cannot determine if limits exist |

**Overall Status**: ⚠️ **BLOCKING - Manual Verification Required**

**Action**: Do not proceed to Phase 1 until all rules are verified or removed.
