# Strategy Validation Gates

Three validation gates to prove strategy robustness before deployment.

## Overview

These gates use the existing backtest infrastructure:
- `scripts/backtest_runner.py` - SIMULATION mode backtesting
- `parameter_grid` in evaluation config - Parameter perturbation
- Time-based date ranges - Walk-forward separation
- Evidence reports - Performance comparison

---

## Gate 1: Walk-Forward Validation

**Purpose**: Prove you are not peeking (no lookahead bias).

**Script**: `scripts/run_walkforward.py`

### Usage

```bash
python3 scripts/run_walkforward.py \
  --config configs/backtest/topstep_50k_backtest.json \
  --output-dir artifacts_g1 \
  --train-split 0.5 \
  --cycles 30
```

### Implementation Pattern

```python
# Training period: earlier dates
train_config = {
    "inputs": {
        "start_date": "2023-01-01",
        "end_date": "2023-06-30",  # 6 months training
        ...
    }
}

# Testing period: later dates (no overlap)
test_config = {
    "inputs": {
        "start_date": "2023-07-01",  # Start AFTER training ends
        "end_date": "2023-12-31",    # 6 months testing
        ...
    }
}
```

### Success Criteria

1. **Time-separated**: Training and testing periods must not overlap
   - `test_start_date > train_end_date` (enforced by config)

2. **No state leaks**: Each backtest uses isolated state
   - ✅ Already enforced: Each backtest run creates fresh artifacts
   - ✅ State is cycle-bound, not cross-backtest

3. **Performance degrades but does not collapse**:
   - Training Sharpe > 0 (or positive return)
   - Test Sharpe ≥ 0.5 × Training Sharpe (reasonable degradation)
   - Test equity curve doesn't collapse (no catastrophic drawdowns)

4. **Red flag if test > train**: 
   - Test Sharpe > Training Sharpe → potential overfitting or data leakage

### Comparison Metrics

From evidence reports:
- **Training**: `evidence_report_train.json` → `final_equity`, `max_drawdown`, Sharpe
- **Testing**: `evidence_report_test.json` → compare metrics

```bash
# Run training backtest
python3 scripts/backtest_runner.py \
  --config configs/backtest/train_period.json \
  --artifacts artifacts_walkforward_train

# Run testing backtest (separate artifacts, later dates)
python3 scripts/backtest_runner.py \
  --config configs/backtest/test_period.json \
  --artifacts artifacts_walkforward_test

# Compare results (manual or script)
python3 scripts/compare_walkforward.py \
  artifacts_walkforward_train \
  artifacts_walkforward_test
```

---

## Gate 2: Parameter Perturbation

**Purpose**: Kill curve-fit strategies (test robustness to small parameter changes).

**Script**: `scripts/run_parameter_perturbation.py`

### Usage

```bash
# Using percentage perturbation
python3 scripts/run_parameter_perturbation.py \
  --config configs/backtest/topstep_50k_backtest.json \
  --param daily_trend \
  --pct 0.2 \
  --artifacts artifacts_g2 \
  --cycles 30

# Using explicit values
python3 scripts/run_parameter_perturbation.py \
  --config configs/backtest/topstep_50k_backtest.json \
  --param daily_trend \
  --values -0.0015 -0.001 -0.0005 \
  --artifacts artifacts_g2 \
  --cycles 30

# Target specific strategy (if multiple in config)
python3 scripts/run_parameter_perturbation.py \
  --config configs/backtest/topstep_50k_backtest.json \
  --param daily_trend \
  --pct 0.2 \
  --strategy-id test_strategy_v1 \
  --artifacts artifacts_g2 \
  --cycles 30
```

### Success Criteria

1. **Equity curve correlation**: Correlation between base and variant equity returns ≥ 0.8
   - If insufficient data for correlation, check is SKIPPED (not failed)

2. **Drawdown bounded**: No variant drawdown > 2× base drawdown
   - Special case: If base drawdown == 0, any variant drawdown > 0 fails

3. **Sharpe ratio bounded**: No variant Sharpe < 0.3× base Sharpe
   - If Sharpe is missing/unavailable, check is SKIPPED (not failed)

### Implementation Pattern

Use existing `parameter_grid` feature:

```json
{
  "evaluation_config": {
    "strategies": [{
      "strategy_id": "momentum_v1",
      "experiment_config": {
        "daily_trend": 0.00005  // Base parameter
      }
    }],
    "parameter_grid": {
      "daily_trend": [0.00004, 0.00005, 0.00006]  // ±20% perturbation
    }
  }
}
```

This creates 3 strategy variants:
- `momentum_v1_param_0`: daily_trend=0.00004 (-20%)
- `momentum_v1_param_1`: daily_trend=0.00005 (base)
- `momentum_v1_param_2`: daily_trend=0.00006 (+20%)

### Success Criteria

1. **Similar equity shapes**: All variants should produce similar equity curves
   - Visual inspection: curves should be parallel, not divergent
   - Quantitative: correlation > 0.8 between variant equity curves

2. **Drawdown does not explode**: 
   - No variant should have drawdown > 2× base drawdown
   - If base drawdown = 5%, variants should be < 10%

3. **No single magic number**:
   - All variants should be profitable (or at least non-catastrophic)
   - Performance should degrade gradually, not collapse

4. **Red flag if performance collapses**:
   - Variant Sharpe < 0.3 × base Sharpe → strategy too sensitive
   - Variant drawdown > 3× base drawdown → fragile strategy

### Implementation

```bash
# Run with parameter grid
python3 scripts/backtest_runner.py \
  --config configs/backtest/momentum_perturb.json \
  --artifacts artifacts_perturb

# Analyze parameter sensitivity
python3 scripts/analyze_parameter_sensitivity.py \
  artifacts_perturb
```

---

## Gate 3: Regime Stress

**Purpose**: See how the strategy fails (test across different market regimes).

**Script**: `scripts/run_regime_stress.py`

### Usage

```bash
# Run all default regimes (trending, mean_reverting, flat, volatile)
python3 scripts/run_regime_stress.py \
  --config configs/backtest/topstep_50k_backtest.json \
  --artifacts artifacts_g3 \
  --cycles 30

# Run specific regimes
python3 scripts/run_regime_stress.py \
  --config configs/backtest/topstep_50k_backtest.json \
  --artifacts artifacts_g3 \
  --regimes trending volatile \
  --cycles 30
```

### Success Criteria

1. **NOT catastrophic**: 
   - `final_equity > 0` AND `total_pnl > -0.5 * account_size`
   - If either condition fails, regime fails

2. **Drawdown bounded**:
   - `max_drawdown_pct <= 2 × ruleset_config.max_trailing_drawdown_pct`
   - If `max_trailing_drawdown_pct` not available, default threshold is 20%

3. **All regimes must pass**: If any regime fails, gate fails

### Implementation Pattern

Create multiple configs with different price series representing regimes:

```json
// configs/backtest/regime_trending.json
{
  "evaluation_config": {
    "price_series": [100, 105, 110, 115, 120, 125, 130]  // Upward trend
  }
}

// configs/backtest/regime_mean_reverting.json  
{
  "evaluation_config": {
    "price_series": [100, 105, 100, 105, 100, 105, 100]  // Oscillating
  }
}

// configs/backtest/regime_flat.json
{
  "evaluation_config": {
    "price_series": [100, 100, 100, 100, 100, 100, 100]  // No movement
  }
}

// configs/backtest/regime_volatile.json
{
  "evaluation_config": {
    "price_series": [100, 110, 90, 115, 85, 120, 80]  // High volatility
  }
}
```

### Success Criteria

1. **Trending regime**: Strategy should perform as designed
   - For momentum: should capture trend, positive returns
   - For mean-reversion: may underperform (expected)

2. **Mean-reverting regime**: Opposite of trending
   - For momentum: may struggle (expected)
   - For mean-reversion: should perform well

3. **Flat regime**: Low/no returns expected
   - Equity should be relatively stable
   - Drawdowns from fees/spreads (acceptable)

4. **Volatile regime**: Stress test
   - Strategy should not blow up
   - Drawdowns should be bounded (not catastrophic)
   - May have larger drawdowns than trending (acceptable)

5. **Predictable failures**:
   - Strategy should fail gracefully in unfavorable regimes
   - Failure mode should be documented and understood
   - No unexpected catastrophic losses

### Implementation

```bash
# Run across all regimes
for regime in trending mean_reverting flat volatile; do
  python3 scripts/backtest_runner.py \
    --config configs/backtest/regime_${regime}.json \
    --artifacts artifacts_regime_${regime}
done

# Compare regime performance
python3 scripts/compare_regimes.py \
  artifacts_regime_trending \
  artifacts_regime_mean_reverting \
  artifacts_regime_flat \
  artifacts_regime_volatile
```

---

## Complete Validation Suite

**Script**: `scripts/validate_strategy.py`

### Usage

```bash
# Run all three gates with default parameters
python3 scripts/validate_strategy.py \
  --config configs/backtest/topstep_50k_backtest.json \
  --artifacts artifacts_suite \
  --cycles 30

# Customize gate parameters
python3 scripts/validate_strategy.py \
  --config configs/backtest/topstep_50k_backtest.json \
  --artifacts artifacts_suite \
  --train-split 0.6 \
  --param daily_trend \
  --pct 0.2 \
  --strategy-id test_strategy_v1 \
  --regimes trending mean_reverting \
  --cycles 30
```

### Output

The script runs all three gates sequentially and produces:
- Individual gate results in subdirectories (`gate1_walkforward/`, `gate2_parameter_perturbation/`, `gate3_regime_stress/`)
- Aggregated results in `validation_suite_result.json`
- Console summary with PASS/FAIL status for each gate and overall

### Exit Codes

- `0`: All gates passed
- `1`: One or more gates failed
- `2`: Invalid inputs/config

---

## Automated Validation Script (Legacy Reference)

The following was the original design pattern (now implemented):
    # Compare performance metrics
    # Return pass/fail with metrics

def gate2_parameter_perturbation(base_config, param_name, perturbation_pct):
    """Gate 2: Parameter perturbation."""
    # Generate parameter grid (±perturbation_pct)
    # Run all variants
    # Compare equity curves and drawdowns
    # Return pass/fail with sensitivity metrics

def gate3_regime_stress(base_config, regimes):
    """Gate 3: Regime stress testing."""
    # Run across all regimes
    # Check for catastrophic failures
    # Document failure modes
    # Return pass/fail with regime performance

def main():
    """Run all gates and produce validation report."""
    # Load base config
    # Run each gate
    # Generate validation report
    # Exit with appropriate code
```

---

## Integration with Existing System

### Leveraging Current Infrastructure

1. **Backtest Runner**: Already supports SIMULATION mode with full turnover
2. **Parameter Grid**: Already implemented in `BatchEvaluationConfig`
3. **Time Separation**: Already enforced via date ranges in configs
4. **Evidence Reports**: Already generated with equity curves and metrics
5. **State Isolation**: Already guaranteed (each backtest uses separate artifacts)

### Next Steps

1. Create example configs for each gate
2. Create comparison/analysis scripts
3. Document pass/fail thresholds
4. Integrate into pre-deployment validation pipeline

---

## Quick Reference

### Run Individual Gates

```bash
# Gate 1: Walk-Forward Validation
python3 scripts/run_walkforward.py \
  --config configs/backtest/topstep_50k_backtest.json \
  --output-dir artifacts_g1 \
  --cycles 30

# Gate 2: Parameter Perturbation
python3 scripts/run_parameter_perturbation.py \
  --config configs/backtest/topstep_50k_backtest.json \
  --param daily_trend \
  --pct 0.2 \
  --artifacts artifacts_g2 \
  --cycles 30

# Gate 3: Regime Stress
python3 scripts/run_regime_stress.py \
  --config configs/backtest/topstep_50k_backtest.json \
  --artifacts artifacts_g3 \
  --cycles 30
```

### Run Complete Suite

```bash
python3 scripts/validate_strategy.py \
  --config configs/backtest/topstep_50k_backtest.json \
  --artifacts artifacts_suite \
  --param daily_trend \
  --pct 0.2 \
  --cycles 30
```

---

## Notes

- All gates use **SIMULATION mode** (not LIVE_DRY) to allow full backtesting
- Gates can be run independently or as a suite
- Gates should be run before any LIVE_DRY rehearsal
- Failed gates don't necessarily reject a strategy, but document expected behavior
- The goal is **predictable failure modes**, not perfection in all regimes
- All scripts output JSON result files for programmatic analysis

