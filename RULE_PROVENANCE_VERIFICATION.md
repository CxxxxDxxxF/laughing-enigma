# Rule Provenance Verification Process

**Status**: In Progress  
**Started**: 2025-12-21  
**Goal**: Verify all rule values in `_RULES.md` files against official firm documentation

## Current Status

**Files to Verify**:
1. `configs/funded/topstep_50k_RULES.md` - ⚠️ IN PROGRESS
2. `configs/funded/topstep_100k_RULES.md` - ⏳ PENDING
3. `configs/funded/apex_50k_RULES.md` - ⏳ PENDING

## Verification Methodology

**One file at a time. One firm at a time. One checklist.**

For each `_RULES.md` file:

1. **Identify all values to verify**:
   - Daily loss limits
   - Trailing drawdown percentages/amounts
   - Session start times
   - Position limits
   - Any value marked "ASSUMED" or "VERIFICATION PENDING"

2. **Access official sources**:
   - Use provided source URLs
   - Access firm's official documentation
   - Use firm's dashboard/help center if available

3. **Extract direct quotes**:
   - For each rule, find the exact quote from official documentation
   - Copy the quote verbatim
   - Note the source URL and date accessed

4. **Resolve inconsistencies**:
   - If multiple sources conflict, use most recent official source
   - Document the resolution
   - Update value if needed

5. **Update status**:
   - Replace "ASSUMED" with "✅ VERIFIED + source"
   - Replace "VERIFICATION PENDING" with "✅ VERIFIED + source"
   - If unverifiable, mark as "❌ REMOVED" with reason

6. **Update config if needed**:
   - If verified value differs from config, update config
   - Document the change

## Topstep 50k Verification (Current)

**File**: `configs/funded/topstep_50k_RULES.md`  
**Verification Template**: `configs/funded/topstep_50k_RULES_VERIFIED.md`

### Rules to Verify

1. **Daily Loss Limit**: $1,000
   - Source: https://help.topstep.com/en/articles/8284207-what-is-the-daily-loss-limit-and-what-happens-if-i-exceed-it
   - Status: Has source quote, needs verification against official docs
   - Action: Verify quote is accurate, confirm $1,000 for 50k account

2. **Trailing Drawdown**: 5% = $2,500
   - Source: https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit
   - Status: ⚠️ INCONSISTENCY - Source says $2,000, calculation says $2,500
   - Action: Resolve inconsistency, verify correct value

3. **Session Start Time**: 5:00 PM CT
   - Source: https://help.topstep.com/en/articles/8284197-trading-combine-parameters
   - Status: Needs direct quote from official docs
   - Action: Find official quote confirming 5:00 PM CT

4. **Position Limits**: Not enforced
   - Source: Multiple (check all Topstep docs)
   - Status: ⚠️ ASSUMED
   - Action: Verify if limits exist, document or remove

### Verification Steps

1. Open each source URL
2. Find relevant section
3. Extract direct quote
4. Fill in `topstep_50k_RULES_VERIFIED.md`
5. Resolve any inconsistencies
6. Update `topstep_50k_RULES.md` with verified values
7. Update config if values differ

## Success Criteria

- [ ] All "ASSUMED" values removed or verified
- [ ] All "VERIFICATION PENDING" values verified
- [ ] All inconsistencies resolved
- [ ] All source quotes documented
- [ ] Config values match verified rules
- [ ] Main `_RULES.md` file updated with verified status

## Next Steps

1. **Complete Topstep 50k verification** (current focus)
   - Verify daily loss limit
   - Resolve trailing drawdown inconsistency
   - Verify session start time
   - Verify position limits

2. **Move to Topstep 100k** (after 50k complete)
   - Use same methodology
   - Verify all values

3. **Move to Apex 50k** (after Topstep complete)
   - Use same methodology
   - Verify all values

## Notes

- Do not proceed to Phase 1 until all "ASSUMED" values are removed or verified
- Compliance is the gate, not stress testing
- One file at a time ensures thoroughness
- Document everything for audit trail

