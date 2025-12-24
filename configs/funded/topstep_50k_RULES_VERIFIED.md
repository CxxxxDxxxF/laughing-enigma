# Topstep 50k Rules Verification Report

**Verification Date**: 2025-12-21  
**Verification Method**: Systematic verification against official Topstep documentation  
**Status**: ⚠️ **BLOCKING ISSUES IDENTIFIED**

---

## Rule 1: Daily Loss Limit

### Claim in topstep_50k_RULES.md
- **Amount**: $1,000
- **Status**: Marked as "✅ VERIFIED" but source quote provided
- **Source Quote Provided**: "For example, in a $50K Trading Combine, the Daily Loss Limit is set at $1,000. If this limit is exceeded, your positions are automatically liquidated and you cannot place new trades until the next trading session begins."

### Verification Attempt
- **Source URL**: https://help.topstep.com/en/articles/8284207-what-is-the-daily-loss-limit-and-what-happens-if-i-exceed-it
- **Method**: Web search for official Topstep Help Center article
- **Result**: ❌ **CANNOT VERIFY** - Web search did not return verbatim quote from official source

### Status Classification
**⚠️ UNVERIFIED (BLOCKING)**

**Reason**: Cannot access verbatim quote from official Topstep Help Center article. The provided source quote may be accurate, but without direct access to the official source, it cannot be verified.

**Action Required**: 
- Manually access https://help.topstep.com/en/articles/8284207-what-is-the-daily-loss-limit-and-what-happens-if-i-exceed-it
- Extract verbatim quote confirming $1,000 for 50k account
- Update this section with exact quote and mark as ✅ VERIFIED

---

## Rule 2: Trailing Drawdown (Maximum Loss Limit)

### Claim in topstep_50k_RULES.md
- **Percentage**: 5% of account size
- **Amount**: $2,500 (for 50k account) = 5% of $50,000
- **Status**: Marked as "✅ VERIFIED" but INCONSISTENCY noted
- **Source Quote Provided**: "For instance, in a $50,000 account, the limit is set at $2,000 below the highest account balance. If your account balance reaches $50,500, the Maximum Loss Limit becomes $48,500."

### Inconsistency Identified
- Source quote says "$2,000 below"
- But 5% of $50,000 = $2,500
- Current rules file uses $2,500 (5%) but source quote says $2,000

### Verification Attempt
- **Source URL**: https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit
- **Method**: Web search for official Topstep Help Center article
- **Result**: ❌ **CANNOT VERIFY** - Web search did not return verbatim quote resolving inconsistency

### Status Classification
**⚠️ INCONSISTENT (BLOCKING)**

**Reason**: 
1. Cannot access verbatim quote from official source
2. Existing source quote conflicts with calculated value ($2,000 vs $2,500)
3. Cannot resolve which value is correct without official source

**Action Required**:
- Manually access https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit
- Extract verbatim quote with exact amount or percentage for 50k account
- Resolve inconsistency: Is it $2,000, $2,500, or 5%?
- Update this section with exact quote and mark as ✅ VERIFIED
- Update config if verified value differs from current

---

## Rule 3: Trading Day / Session Definition

### Claim in topstep_50k_RULES.md
- **Session Start**: 5:00 PM CT (17:00:00 Central Time)
- **Status**: Marked as "✅ VERIFIED (confirmed from multiple sources)"
- **Notes**: "Traders must be flat by 3:10 PM CT on weekdays. Next session opens at 5:00 PM CT."

### Verification Attempt
- **Source URL**: https://help.topstep.com/en/articles/8284197-trading-combine-parameters
- **Method**: Web search for official Topstep Help Center article
- **Result**: ⚠️ **PARTIAL** - Web search found references to 5:00 PM CT but no verbatim quote

### Status Classification
**⚠️ UNVERIFIED (BLOCKING)**

**Reason**: Cannot access verbatim quote from official Topstep Help Center confirming:
- Exact session start time (5:00 PM CT)
- "Flat by 3:10 PM CT" requirement
- Daily loss reset timing

**Action Required**:
- Manually access https://help.topstep.com/en/articles/8284197-trading-combine-parameters
- Extract verbatim quote confirming 5:00 PM CT session start
- Extract verbatim quote confirming "flat by 3:10 PM CT" requirement
- Update this section with exact quotes and mark as ✅ VERIFIED

---

## Rule 4: Position Limits

### Claim in topstep_50k_RULES.md
- **Current Config**: Not enforced (max_position_size: null)
- **Status**: ⚠️ ASSUMED - "Position size limits vary by instrument and account type"
- **Note**: "TODO: Add instrument-specific limits if needed"

### Verification Attempt
- **Source URLs**: Multiple (checked all Topstep documentation sources)
- **Method**: Web search for position limits in Topstep Trading Combine
- **Result**: ❌ **CANNOT VERIFY** - No clear information found about position limits

### Status Classification
**⚠️ UNVERIFIED (BLOCKING)**

**Reason**: Cannot determine if position limits exist or are not enforced. Current config assumes no limits, but this is not verified.

**Action Required**:
- Manually check all Topstep documentation for position size limits
- Check Topstep dashboard (if accessible) for position limit settings
- If no limits found: Mark as ✅ VERIFIED (no position limits)
- If limits found: Document them and update config

---

## Summary

### Verification Status
- **Rule 1 (Daily Loss Limit)**: ⚠️ UNVERIFIED (BLOCKING)
- **Rule 2 (Trailing Drawdown)**: ⚠️ INCONSISTENT (BLOCKING)
- **Rule 3 (Session Start)**: ⚠️ UNVERIFIED (BLOCKING)
- **Rule 4 (Position Limits)**: ⚠️ UNVERIFIED (BLOCKING)

### Blocking Issues
1. **Cannot access official Topstep Help Center articles directly** - Web search does not provide verbatim quotes
2. **Inconsistency in trailing drawdown** - $2,000 vs $2,500 needs resolution
3. **No verified source quotes** - All rules need manual verification with verbatim quotes

### Required Actions
1. **Manual Verification Required**: Access each source URL directly and extract verbatim quotes
2. **Resolve Inconsistency**: Determine correct trailing drawdown value ($2,000 or $2,500)
3. **Update Status**: Mark each rule as ✅ VERIFIED with source quote, or ❌ REMOVED if unverifiable
4. **Update Config**: If verified values differ from config, update config files

### Next Steps
1. Manually access all source URLs listed above
2. Extract verbatim quotes for each rule
3. Resolve trailing drawdown inconsistency
4. Update this document with verified quotes
5. Update `topstep_50k_RULES.md` with verified status
6. Update config files if values differ

**⚠️ DO NOT PROCEED TO PHASE 1 UNTIL ALL RULES ARE VERIFIED OR REMOVED**
