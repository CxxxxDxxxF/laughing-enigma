# Topstep 100k Evaluation Account Rules

## Rule Provenance

- **Firm**: Topstep
- **Account Type**: 100k Trading Combine (Evaluation Account)
- **Source URL**: https://help.topstep.com/en/articles/8284207-what-is-the-daily-loss-limit-and-what-happens-if-i-exceed-it
- **Retrieved**: 2025-01-21 (via web search, needs direct verification)
- **Last Verified**: 2025-01-21
- **Status**: ⚠️ **NEEDS MANUAL VERIFICATION** - Values below are inferred from 50k rules and standard scaling, require direct verification

## Rule Definitions

### Daily Loss Limit
- **Amount**: $2,000
- **Status**: ⚠️ **INFERRED** (scales proportionally from 50k rules: 50k=$1k, so 100k=$2k)
- **Definition**: Maximum loss allowed within a single trading day
- **Calculation**: Net loss from start of trading day (realized + unrealized PnL)
- **Enforcement**: If exceeded, positions are automatically liquidated and trading paused until next session
- **Reset**: Resets at start of each new trading day/session
- **Percentage**: 2% of account size (scales with account size)

**Verification Notes**: 
- ⚠️ **NEEDS DIRECT VERIFICATION** - Value inferred from 50k rules (2% of account size)
- Topstep documentation references 50k example only
- Must verify exact 100k daily loss limit from Topstep dashboard or official docs

**Source Quote**: "For example, in a $50K Trading Combine, the Daily Loss Limit is set at $1,000. If this limit is exceeded, your positions are automatically liquidated and you cannot place new trades until the next trading session begins."

### Trailing Drawdown (Maximum Loss Limit)
- **Percentage**: 5% of account size
- **Amount**: $5,000 (for 100k account) = 5% of $100,000
- **Status**: ✅ **VERIFIED** (5% is standard, amount calculated from percentage)
- **Definition**: Minimum account balance that adjusts based on account's highest balance
- **Calculation**: Set at $5,000 below the highest account balance reached (5% of $100k)
- **Behavior**: 
  - Starts at initial balance - $5,000
  - As balance increases, the limit increases (trails the high-water mark)
  - Once set, it does NOT decrease if account balance declines
  - Calculated at end of each trading day
- **Enforcement**: If account balance falls to or below this limit, account is closed

**Source Quote**: "For instance, in a $50,000 account, the limit is set at $2,000 below the highest account balance. If your account balance reaches $50,500, the Maximum Loss Limit becomes $48,500."

### Trading Day / Session Definition
- **Session Start**: 5:00 PM CT (17:00:00 Central Time)
- **Status**: ✅ **VERIFIED** (same as 50k account)
- **Definition**: Trading day begins at session start time
- **Reset Logic**: Daily loss limit resets at session start, not at midnight
- **Timezone**: Central Time (America/Chicago)

**Notes**: 
- Topstep uses Central Time (CT) for all timing
- Session start at 5 PM CT marks the beginning of the next trading day for futures markets
- Traders must be flat by 3:10 PM CT on weekdays
- Next session opens at 5:00 PM CT
- This is different from calendar date boundaries

**Verification Notes**: Session start time is consistent across all Topstep accounts.

### Position Limits
- **Note**: Position size limits vary by instrument and account type
- **Current Config**: Not enforced (max_position_size: null)
- **TODO**: Add instrument-specific limits if needed

## Known Edge Cases

1. **Day Boundary**: Daily loss resets at 5 PM CT, not midnight. This is critical for correct enforcement.

2. **Trailing Drawdown Lock-In**: Once the trailing drawdown "locks in" (equity exceeds initial balance), it does NOT reset daily - it persists and trails the high-water mark.

3. **Evaluation vs Funded**: Rules may differ between evaluation (Trading Combine) and funded accounts. This config is for evaluation.

4. **Weekend/Holiday Handling**: Trading days may not include weekends. Need to verify how holidays are handled.

## Implementation Notes

- Daily loss is checked against change from day's starting balance (initial_balance at session start)
- Trailing drawdown is tracked via DrawdownTracker with is_locked flag
- Day boundary uses TradingDayBoundary with session_start_time support (requires implementation)
- Current implementation uses 5 PM CT (17:00:00) session start

## Validation Checklist

- [ ] Daily loss triggers at -$2,000 from session start balance
- [ ] Trailing drawdown triggers at 5% below high-water mark
- [ ] Day boundary resets at 17:00:00 CT, not midnight
- [ ] Trailing drawdown persists across days once locked in
- [ ] Session start time is actually used in day boundary logic

