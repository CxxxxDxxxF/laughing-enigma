# Apex Trader Funding 50k Account Rules

## Rule Provenance

- **Firm**: Apex Trader Funding
- **Account Type**: 50k Evaluation Account
- **Source URL**: https://support.apextraderfunding.com/hc/en-us/articles/40463582041371-Trailing-Drawdown-Rule
- **Retrieved**: 2025-01-21 (via web search, needs direct verification)
- **Last Verified**: 2025-01-21
- **Status**: ⚠️ **REQUIRES MANUAL VERIFICATION** - Many values are ASSUMED based on similar firms, require direct verification from Apex documentation

## Rule Definitions

### Daily Loss Limit
- **Amount**: $1,000
- **Status**: ⚠️ **ASSUMED** (not verified from Apex documentation)
- **Definition**: Maximum loss allowed within a single trading day
- **Calculation**: Net loss from start of trading day (realized + unrealized PnL)
- **Reset**: Resets at start of each new trading day/session
- **Note**: Value assumed based on similar firms (2% of account size). **MUST VERIFY** from Apex documentation.

**Source Quote**: [NEEDS ACTUAL QUOTE FROM APEX DOCS - NOT VERIFIED]

**Verification Required**: 
- ⚠️ **CRITICAL** - Daily loss limit must be verified from official Apex documentation or dashboard
- Cannot proceed with live trading until this value is confirmed

### Trailing Drawdown
- **Percentage**: 5% of account size
- **Amount**: $2,500 (for 50k account) = 5% of $50,000
- **Status**: ✅ **VERIFIED** (from Apex documentation)
- **Definition**: Minimum account balance that trails the peak unrealized balance
- **Calculation**: Starts at liquidation threshold (initial balance - drawdown limit) = $50,000 - $2,500 = $47,500
- **Behavior**: 
  - Trails the peak unrealized balance as it increases
  - Stops moving when peak reaches "Safety Net" (initial balance + drawdown limit + $100)
  - Once at Safety Net, trailing drawdown becomes fixed
- **Enforcement**: If account balance falls to or below trailing drawdown, account is closed

**Source Quote**: "The trailing drawdown starts at the liquidation threshold, determined by your plan's max drawdown amount. As your account balance increases, the trailing drawdown follows your peak unrealized balance until it reaches a fixed point called the Safety Net (initial balance + drawdown limit + $100). The trailing drawdown stops moving when your peak unrealized account balance reaches the Safety Net."

**Verification Notes**: 5% drawdown confirmed from Apex documentation. Safety Net behavior is Apex-specific and differs from Topstep.

### Safety Net
- **Definition**: Fixed point where trailing drawdown stops moving
- **Calculation**: Initial balance + drawdown limit + $100
- **For 50k account**: $50,000 + $2,500 + $100 = $52,600

### Trading Day / Session Definition
- **Session Start**: 5:00 PM CT (17:00:00 Central Time)
- **Status**: ⚠️ **ASSUMED** (not verified from Apex documentation)
- **Definition**: Trading day begins at session start time
- **Reset Logic**: Daily loss limit resets at session start
- **Timezone**: Central Time (America/Chicago)
- **Note**: Value assumed based on standard futures market session times. **MUST VERIFY** from Apex documentation.

**Verification Required**:
- ⚠️ **CRITICAL** - Session start time must be verified from official Apex documentation
- Cannot proceed with live trading until this value is confirmed
- May differ from Topstep session timing

### 30% Negative P&L Rule (Consistency Rule)
- **Definition**: Limits loss on any single trade to 30% of account's profit balance at start of day
- **Calculation**: 30% of start-of-day profit balance
- **Enforcement**: Per-trade basis (live, unrealized, open negative P&L cannot exceed threshold)
- **Note**: This is a consistency rule, not encoded in current config

**Source Quote**: "The live, unrealized, open negative P&L cannot exceed 30% of the account's profit balance at the start of the day on a per-trade basis."

## Known Edge Cases

1. **Safety Net**: Once peak equity reaches Safety Net, trailing drawdown becomes fixed at Safety Net - drawdown limit. This differs from Topstep behavior.

2. **Day Boundary**: Daily loss resets at session start (assumed 5 PM CT), not midnight. Needs verification.

3. **Trailing Drawdown**: Tracks peak unrealized balance, not realized balance. This is different from some other firms.

4. **30% Rule**: This is a per-trade consistency rule that is not yet encoded in the config. May need separate enforcement.

## Implementation Notes

- Daily loss is checked against change from day's starting balance
- Trailing drawdown implementation may differ from Topstep (Safety Net behavior)
- Day boundary uses TradingDayBoundary with session_start_time support (requires implementation)
- Current implementation uses 5 PM CT (17:00:00) session start (ASSUMED - needs verification)

## Validation Checklist

- [ ] Daily loss triggers at correct amount (needs verification: $1,000?)
- [ ] Trailing drawdown triggers at 5% below high-water mark
- [ ] Safety Net behavior is correctly implemented (stops at initial + drawdown + $100)
- [ ] Day boundary resets at correct session start time (needs verification)
- [ ] Trailing drawdown persists across days correctly
- [ ] Session start time is actually used in day boundary logic

## TODO

- [ ] Verify exact daily loss limit amount
- [ ] Verify exact session start time
- [ ] Verify timezone
- [ ] Implement Safety Net behavior in drawdown tracker
- [ ] Consider adding 30% consistency rule enforcement

