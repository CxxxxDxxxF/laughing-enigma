# Backtest Spec v1 – Truth Discovery Phase

**Status**: ✅ **SPECIFICATION COMPLETE**

**Version**: 1.0  
**Date**: 2024-01-XX  
**Purpose**: Systematic backtest design to determine whether strategies have positive expectancy under realistic conditions.

## Document Control

**Frozen Components** (NO changes allowed):
- `runner.py` - Portfolio lifecycle runner
- `execution/paper_engine.py` - Execution engine
- `rules/topstep.py` - Rulesets
- `limits/provider.py` - Limits logic
- `broker/adapter.py` - Broker abstraction

**Mutable Components** (may change):
- Strategy code (`src/engines/simple.py` or future strategy implementations)
- Backtest harnesses (`scripts/backtest_runner.py`)
- This specification document

**Change Policy**:
- Any change to this spec invalidates previous backtest results
- All changes must be documented with version number
- Previous spec versions must be preserved

---

## 1. Instruments & Markets

### 1.1 Primary Instruments

**Futures Contracts** (Topstep-compatible):
- **ES** (E-mini S&P 500) - Primary equity index
- **NQ** (E-mini Nasdaq-100) - Secondary equity index
- **CL** (Crude Oil) - Commodity diversification

**Contract Specifications**:
- **ES**: $50 per point, tick size 0.25 points ($12.50 per tick)
- **NQ**: $20 per point, tick size 0.25 points ($5.00 per tick)
- **CL**: $1,000 per point, tick size 0.01 points ($10.00 per tick)

**Exchange**: CME Group (Chicago Mercantile Exchange)

### 1.2 Session Rules

**Trading Hours** (CT - Central Time):
- **Regular Session**: 5:00 PM CT (previous day) to 3:15 PM CT (current day)
- **Trading Day Boundary**: 5:00 PM CT (session start)
- **Pre-Market Flatten**: 3:00 PM CT (10 minutes before close)
- **Session End**: 3:15 PM CT

**Timezone Handling**:
- All timestamps in `America/Chicago` (CT/CDT)
- Trading day boundary: 17:00:00 CT
- Day boundary logic: `TradingDayBoundary(timezone=ZoneInfo("America/Chicago"), session_start_time=time(17, 0, 0))`

**Holiday Schedule**:
- New Year's Day
- Martin Luther King Jr. Day
- Presidents' Day
- Good Friday
- Memorial Day
- Juneteenth
- Independence Day
- Labor Day
- Thanksgiving
- Christmas

**Holiday Handling**:
- No trading on holidays
- Trading day boundary shifts to next trading day
- No data generation for holiday dates

### 1.3 Contract Rollover

**Rollover Rules** (for future real data):
- Roll to next contract on first trading day of expiration month
- Use front month contract for backtesting
- No backwardation/contango adjustments (assume perfect roll)

**Current Status**: Synthetic data - no rollover needed

---

## 2. Data

### 2.1 Data Source

**Current Implementation**: `SimpleResearchEngine`
- Generates synthetic, deterministic return series
- No real market data (by design for Phase 0/1/2)
- Deterministic hash-based price generation

**Future Real Data Requirements** (when implemented):
- Source: CME Group historical data or third-party provider (e.g., QuantConnect, Polygon)
- Format: OHLCV bars (Open, High, Low, Close, Volume)
- Quality: Cleaned, adjusted for splits/dividends (futures: no adjustments needed)

### 2.2 Bar Resolution

**Primary Resolution**: Daily bars
- One bar per trading day
- Bar timestamp: Close of regular session (3:15 PM CT)
- Bar date: Trading day (session start date, e.g., 2024-01-01 if session starts 2024-01-01 17:00 CT)

**Alternative Resolutions** (future):
- Intraday: 1-minute, 5-minute, 15-minute, 1-hour
- Not used in v1 backtests

### 2.3 Date Range

**Sanity Backtest Range**:
- Start: 2024-01-01
- End: 2024-03-31
- Duration: 90 calendar days (~60 trading days)
- Purpose: Quick validation, not statistical significance

**Statistical Backtest Range**:
- Start: 2023-01-01
- End: 2023-12-31
- Duration: 365 calendar days (~252 trading days)
- Purpose: One full year of data for statistical validity

**Robustness Backtest Range**:
- Start: 2022-01-01
- End: 2023-12-31
- Duration: 730 calendar days (~504 trading days)
- Purpose: Multi-year robustness, different market regimes

### 2.4 Missing Data Handling

**Missing Bars**:
- If bar is missing for a trading day: **HARD FAIL**
- No interpolation, no forward-fill, no backward-fill
- Missing data indicates data quality issue, not market closure

**Holiday Handling**:
- No bars generated for holidays
- Trading day boundary shifts to next trading day
- No data required for non-trading days

**Data Quality Checks** (before backtest):
1. All required dates have bars
2. No duplicate dates
3. Dates are in chronological order
4. All prices are positive
5. High >= Low
6. High >= Open, High >= Close
7. Low <= Open, Low <= Close

### 2.5 Future Data Leakage Prevention

**Strict Rules**:
- No data from future dates used in any calculation
- Price series must be strictly chronological
- No look-ahead bias in strategy logic
- Execution uses only prices available at decision time

**Validation**:
- All price accesses must be timestamped
- Execution engine validates timestamp ordering
- Any future data access → HARD FAIL

---

## 3. Execution Assumptions

### 3.1 Order Type Model

**Order Types**:
- **Market Orders Only** (v1)
- Immediate execution at current price
- No limit orders, no stop orders, no conditional orders

**Execution Price**:
- Market orders fill at bar close price
- No intraday price discovery
- Assumes perfect liquidity (no slippage from bar close)

**Future Enhancements** (not in v1):
- Limit orders
- Stop-loss orders
- Time-in-force (GTC, DAY, IOC)

### 3.2 Slippage Model

**Slippage Assumption**: **Conservative fixed slippage**

**Slippage Rules**:
- **ES**: 0.25 points per contract ($12.50 per contract)
- **NQ**: 0.25 points per contract ($5.00 per contract)
- **CL**: 0.01 points per contract ($10.00 per contract)

**Slippage Application**:
- Applied to all fills (entry and exit)
- Slippage is always a cost (reduces profit, increases loss)
- For long positions: entry price + slippage, exit price - slippage
- For short positions: entry price - slippage, exit price + slippage

**Formula**:
```
Long Entry Cost = Entry Price + Slippage
Long Exit Proceeds = Exit Price - Slippage
Short Entry Proceeds = Entry Price - Slippage
Short Exit Cost = Exit Price + Slippage
```

### 3.3 Commission & Fees

**Commission Model**: Fixed per-contract commission

**Commission Rates**:
- **ES**: $4.20 per contract per side (round-trip: $8.40)
- **NQ**: $4.20 per contract per side (round-trip: $8.40)
- **CL**: $4.20 per contract per side (round-trip: $8.40)

**Fee Structure**:
- Exchange fees: Included in commission
- NFA fees: Included in commission
- No additional fees

**Commission Application**:
- Charged on entry (open position)
- Charged on exit (close position)
- Total round-trip cost: 2 × commission per contract

**Total Execution Cost** (per contract, round-trip):
- **ES**: $8.40 commission + $25.00 slippage = **$33.40**
- **NQ**: $8.40 commission + $10.00 slippage = **$18.40**
- **CL**: $8.40 commission + $20.00 slippage = **$28.40**

### 3.4 Execution Latency

**Latency Assumption**: Zero latency (instantaneous execution)

**Rationale**:
- Daily bar resolution means decisions are made at bar close
- Execution happens at bar close price
- No intraday latency considerations

**Future Considerations** (not in v1):
- Order submission latency
- Fill confirmation latency
- Network latency

---

## 4. Capital & Risk Model

### 4.1 Starting Capital

**Initial Capital**: $50,000.00

**Account Type**: Topstep COMBINE (evaluation account)

**Capital Constraints**:
- No margin calls (assumes sufficient margin)
- No leverage beyond contract margin requirements
- Capital cannot go negative (halt on equity ≤ 0)

### 4.2 Position Sizing Logic

**Position Sizing Method**: Fixed dollar allocation per strategy

**Allocation Rules**:
- Each strategy receives equal capital allocation
- If 2 strategies: $25,000 per strategy
- If 3 strategies: $16,666.67 per strategy
- Rounding: Floor to nearest contract

**Contract Calculation**:
```
Contracts = Floor(Allocated Capital / (Contract Price × Contract Multiplier × Margin Requirement))
```

**Margin Requirements** (conservative):
- **ES**: $13,200 per contract (26.4% of notional at $5,000/contract)
- **NQ**: $17,600 per contract (26.4% of notional at $6,667/contract)
- **CL**: $6,600 per contract (13.2% of notional at $50,000/contract)

**Example** (ES at $5,000):
- Allocated Capital: $25,000
- Contracts = Floor($25,000 / ($5,000 × 1 × 0.264)) = Floor($25,000 / $1,320) = 18 contracts

### 4.3 Max Risk Per Trade

**Risk Definition**: Maximum loss per trade (stop-loss distance)

**Stop-Loss Rules** (v1):
- **No explicit stop-loss** (strategy-dependent)
- Risk controlled by position size only
- Maximum position size limited by capital and margin

**Future Enhancement**:
- Explicit stop-loss per trade
- Risk-reward ratio constraints

### 4.4 Max Daily Risk

**Daily Loss Limit**: -$1,000.00 (Topstep COMBINE rule)

**Enforcement**:
- Enforced by `TopstepRuleset.validate_execution()`
- Daily loss = Equity - Initial Balance
- If daily_loss <= -$1,000: HALT violation
- Trading stops for remainder of trading day

**Daily Loss Calculation**:
```
Daily Loss = Current Equity - Initial Balance (at session start)
```

**Session Reset**:
- Daily loss resets at trading day boundary (5:00 PM CT)
- New trading day starts with current equity as new initial balance

### 4.5 Capital Reset Rules

**No Capital Reset**:
- Capital compounds (or depletes) over time
- No periodic resets to initial capital
- Equity curve reflects true cumulative performance

**Exception**: Trading day boundary resets daily loss tracking (not capital)

---

## 5. Strategy Definition

### 5.1 Current Strategy: Buy-and-Hold with Trend

**Strategy Type**: `buy_hold`

**Strategy Logic**:
1. Enter long position on first bar
2. Hold position until end of backtest
3. Exit on last bar

**Parameters**:
- `daily_trend`: Daily return trend (decimal, e.g., 0.001 = 0.1% per day)
- `instrument`: Instrument identifier (e.g., "ES", "NQ", "CL")

**Entry Logic**:
- Entry: First bar of backtest period
- Entry Price: Close price of first bar
- Entry Quantity: Calculated from allocated capital and margin requirements

**Exit Logic**:
- Exit: Last bar of backtest period
- Exit Price: Close price of last bar
- Exit Quantity: Full position (no partial exits)

**Stop Logic**:
- No explicit stop-loss
- Stop occurs only via daily loss limit (-$1,000) or equity floor ($0)

### 5.2 Strategy Parameters (Explicit)

**Required Parameters**:
```json
{
  "strategy_type": "buy_hold",
  "daily_trend": 0.001,
  "instrument": "ES"
}
```

**Parameter Ranges** (for future optimization, NOT in v1):
- `daily_trend`: -0.01 to +0.01 (-1% to +1% per day)
- `instrument`: "ES", "NQ", "CL"

**Parameter Constraints**:
- `daily_trend` must be a float
- `instrument` must be a valid instrument identifier
- No other parameters allowed

### 5.3 Discretionary Behavior Prohibition

**Strict Rules**:
- No manual intervention during backtest
- No parameter changes mid-backtest
- No strategy logic changes based on results
- All decisions must be algorithmically determined

**Validation**:
- Strategy code must be deterministic
- Same inputs → same outputs
- No external state (except price data)

---

## 6. Backtest Layers to Run

### 6.1 Layer 1: Sanity Backtests

**Purpose**: Quick validation that system works correctly

**Configuration**:
- Date Range: 2024-01-01 to 2024-03-31 (90 days)
- Strategies: 1 strategy (buy_hold, daily_trend=0.001)
- Instruments: ES only
- Number of Runs: 1

**Required Trades**: Minimum 1 trade (entry + exit)

**Metrics to Evaluate**:
- Total return
- Number of trades
- Execution cost impact
- Daily loss breach frequency

**Pass/Fail Criteria**:
- ✅ System executes without errors
- ✅ At least 1 trade occurs
- ✅ Equity curve is non-decreasing if trend > 0
- ✅ Execution costs are applied correctly

**Expected Duration**: < 1 minute

### 6.2 Layer 2: Statistical Backtests

**Purpose**: Determine statistical significance of strategy performance

**Configuration**:
- Date Range: 2023-01-01 to 2023-12-31 (365 days, ~252 trading days)
- Strategies: 1 strategy (buy_hold, daily_trend=0.001)
- Instruments: ES, NQ, CL (separate backtests)
- Number of Runs: 3 (one per instrument)

**Required Trades**: Minimum 1 trade per instrument

**Metrics to Evaluate** (see Section 7):
- Expectancy per trade
- Win rate
- Average win / average loss
- Profit factor
- Max drawdown
- Daily loss breach frequency
- Trades per day
- Time in market

**Pass/Fail Criteria**:
- ✅ Expectancy > 0 after costs
- ✅ Profit factor > 1.0
- ✅ Max drawdown < 50% of initial capital
- ✅ Daily loss breaches < 5% of trading days
- ✅ At least 1 trade per instrument

**Expected Duration**: < 5 minutes

### 6.3 Layer 3: Robustness Backtests

**Purpose**: Test strategy across different market regimes and time periods

**Configuration**:
- Date Range: 2022-01-01 to 2023-12-31 (730 days, ~504 trading days)
- Strategies: 1 strategy (buy_hold, daily_trend=0.001)
- Instruments: ES, NQ, CL (separate backtests)
- Number of Runs: 3 (one per instrument)

**Required Trades**: Minimum 1 trade per instrument

**Metrics to Evaluate** (see Section 7):
- All metrics from Layer 2
- Year-over-year consistency
- Regime-specific performance
- Worst-case scenarios

**Pass/Fail Criteria**:
- ✅ Expectancy > 0 after costs (both years)
- ✅ Profit factor > 1.0 (both years)
- ✅ Max drawdown < 50% of initial capital
- ✅ No single trade accounts for > 50% of total profit
- ✅ Performance is consistent across years

**Expected Duration**: < 10 minutes

---

## 7. Metrics (Required)

### 7.1 Trade-Level Metrics

**Expectancy Per Trade**:
```
Expectancy = (Win Rate × Average Win) - (Loss Rate × Average Loss)
```
- **Required**: Must be > 0 after execution costs
- **Calculation**: Sum of all trade PnL / Number of trades
- **Cost Adjustment**: Subtract execution costs (commission + slippage) from each trade

**Win Rate**:
```
Win Rate = Number of Winning Trades / Total Number of Trades
```
- **Required**: Not a primary success metric (can be < 50% if avg win >> avg loss)
- **Calculation**: Count trades with PnL > 0

**Average Win / Average Loss**:
```
Average Win = Sum of Winning Trade PnL / Number of Winning Trades
Average Loss = Sum of Losing Trade PnL / Number of Losing Trades
Ratio = Average Win / |Average Loss|
```
- **Required**: Ratio > 1.0 for profitability (if win rate < 50%)
- **Calculation**: Separate winning and losing trades

**Profit Factor**:
```
Profit Factor = Sum of Winning Trade PnL / |Sum of Losing Trade PnL|
```
- **Required**: Must be > 1.0
- **Calculation**: Total profits / Total losses (absolute value)

### 7.2 Portfolio-Level Metrics

**Max Drawdown**:
```
Max Drawdown = Maximum peak-to-trough decline in equity
```
- **Required**: Must be < 50% of initial capital
- **Calculation**: Track equity curve, find maximum decline from any peak
- **Time Period**: Entire backtest period

**Daily Loss Breach Frequency**:
```
Breach Frequency = Number of Days with Daily Loss <= -$1,000 / Total Trading Days
```
- **Required**: Must be < 5% of trading days
- **Calculation**: Count days where daily loss limit was breached
- **Impact**: Each breach = HALT violation (trading stops for day)

**Trades Per Day**:
```
Trades Per Day = Total Number of Trades / Total Trading Days
```
- **Required**: Not a primary success metric
- **Calculation**: Simple average
- **Purpose**: Understand trading frequency

**Time In Market**:
```
Time In Market = Sum of Days with Open Position / Total Trading Days
```
- **Required**: Not a primary success metric
- **Calculation**: Count days with non-zero position
- **Purpose**: Understand position holding behavior

### 7.3 Performance Metrics (NOT Primary Success Criteria)

**Total Net Profit**:
- ❌ **NOT** a primary success metric
- Can be misleading if driven by few large trades
- Use expectancy and profit factor instead

**Smoothness of Equity Curve**:
- ❌ **NOT** a primary success metric
- Smooth curves can hide risk
- Focus on max drawdown and daily loss breaches

**Sharpe Ratio**:
- ❌ **NOT** used in v1 (too early, need more data)
- May be added in future versions

### 7.4 Metric Calculation Rules

**Cost Inclusion**:
- All metrics must include execution costs (commission + slippage)
- No "gross" metrics (always net of costs)

**Precision**:
- All dollar amounts: 2 decimal places
- All percentages: 2 decimal places
- All ratios: 4 decimal places

**Missing Data Handling**:
- If metric cannot be calculated (e.g., no trades): Report as "N/A"
- Do not use zero or default values

---

## 8. Hard Constraints

### 8.1 No Parameter Optimization

**Constraint**: Do NOT optimize parameters in v1

**Rationale**:
- v1 is truth discovery, not optimization
- Optimization requires separate phase
- Must establish baseline first

**Allowed**:
- Testing different parameter values manually
- Comparing results across parameter values
- Documenting parameter sensitivity

**Not Allowed**:
- Automated parameter search
- Grid search
- Genetic algorithms
- Any optimization algorithm

### 8.2 No Cherry-Picking Date Ranges

**Constraint**: Use fixed date ranges, no selective periods

**Rationale**:
- Cherry-picking inflates performance
- Real trading includes all periods
- Must test across full ranges

**Allowed**:
- Testing different fixed date ranges
- Comparing results across different periods
- Documenting period-specific performance

**Not Allowed**:
- Selecting only profitable periods
- Excluding losing periods
- Adjusting dates based on results

### 8.3 No Logic Adjustments Based on Results

**Constraint**: Do NOT change strategy logic based on backtest results

**Rationale**:
- Results-based changes = overfitting
- Strategy must be defined before backtesting
- Changes require new spec version

**Allowed**:
- Fixing bugs (not logic changes)
- Improving code quality
- Adding logging/debugging

**Not Allowed**:
- Changing entry/exit rules based on results
- Adjusting parameters based on results
- Adding filters based on results

### 8.4 Profitability Requirements

**Constraint**: If expectancy ≤ 0 after costs, strategy is NOT profitable

**Rationale**:
- Negative expectancy = guaranteed long-term loss
- Execution costs are real
- Must account for all costs

**Enforcement**:
- Calculate expectancy including all costs
- If expectancy <= 0: Strategy fails
- No exceptions

### 8.5 Trade Concentration Requirements

**Constraint**: If results depend on a few trades, strategy fails

**Rationale**:
- Few large wins = unreliable strategy
- Need consistent performance
- Must have sufficient trade sample

**Enforcement**:
- If single trade > 50% of total profit: FAIL
- If top 3 trades > 80% of total profit: FAIL
- Minimum 10 trades for statistical validity (future)

---

## 9. Ambiguity Resolution

### 9.1 If Anything is Ambiguous

**Rule**: Flag it and stop

**Process**:
1. Document the ambiguity
2. Do NOT make assumptions
3. Update this spec to resolve ambiguity
4. Re-run affected backtests

**Examples of Ambiguities**:
- Unclear data source
- Unclear execution price
- Unclear cost calculation
- Unclear metric definition

### 9.2 Specification Updates

**Version Control**:
- All spec changes create new version
- Previous versions must be preserved
- Changes must be documented

**Change Log**:
- Document all changes
- Explain rationale
- List affected backtests

---

## 10. Deliverable Checklist

### 10.1 Pre-Backtest Checklist

- [x] Instruments defined (ES, NQ, CL)
- [x] Data source defined (SimpleResearchEngine, synthetic)
- [x] Execution assumptions defined (slippage, commission, latency)
- [x] Capital model defined ($50,000, position sizing)
- [x] Strategy defined (buy_hold, parameters explicit)
- [x] Backtest layers defined (sanity, statistical, robustness)
- [x] Metrics defined (expectancy, win rate, profit factor, etc.)
- [x] Constraints defined (no optimization, no cherry-picking)
- [x] Ambiguity resolution process defined

### 10.2 Post-Backtest Checklist

- [ ] All backtest layers executed
- [ ] All metrics calculated
- [ ] Results documented
- [ ] Pass/fail criteria evaluated
- [ ] Any ambiguities resolved
- [ ] Spec updated if needed

---

## 11. Success Criteria

### 11.1 Specification Completeness

✅ **Backtest Spec v1 is fully defined**
- All sections complete
- No implicit assumptions
- All constraints explicit

✅ **Ready to run sanity backtests without reinterpretation**
- Two independent engineers could run same backtest
- Results would be comparable
- No ambiguity in execution

### 11.2 Backtest Execution (Future)

**After running backtests**:
- [ ] All metrics calculated correctly
- [ ] All constraints enforced
- [ ] Results documented
- [ ] Pass/fail criteria evaluated
- [ ] Strategy profitability determined

---

## 12. Version History

**v1.0** (2024-01-XX):
- Initial specification
- Defines instruments, data, execution, capital, strategy, layers, metrics
- Establishes constraints and success criteria

---

**END OF SPECIFICATION**

