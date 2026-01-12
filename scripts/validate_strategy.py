#!/usr/bin/env python3
"""Strategy Robustness Validation.

Performs rigorous validation to detect overfitting and assess real-world viability.
"""

import sys
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.csv_provider import CSVDataProvider
from src.strategy.enhanced_strategies import EnhancedDualMomentum


def run_backtest_with_costs(strategy, data, initial_capital=100000, slippage_bps=10, commission_per_trade=1.0):
    """Run backtest with realistic transaction costs."""
    cash = initial_capital
    positions = {}
    portfolio_values = []
    total_trades = 0
    total_slippage = 0
    total_commission = 0
    
    all_dates = set()
    for df in data.values():
        all_dates.update(df.index.tolist())
    dates = sorted(all_dates)
    
    start_idx = 200
    
    for i, date in enumerate(dates[start_idx:], start_idx):
        current_data = {}
        for symbol, df in data.items():
            mask = df.index <= date
            if mask.any():
                current_data[symbol] = df[mask].copy()
        
        if not current_data:
            continue
        
        current_weights = {}
        total_value = cash
        for symbol in positions:
            if symbol in current_data and date in current_data[symbol].index:
                price = current_data[symbol].loc[date, 'close']
                total_value += positions[symbol] * price
                current_weights[symbol] = (positions[symbol] * price) / total_value if total_value > 0 else 0
        
        if i % 5 == 0:
            signals = strategy.generate_signals(current_data, current_weights)
            
            for signal in signals:
                if signal.action == 'sell' and signal.symbol in positions and positions[signal.symbol] > 0:
                    if date in current_data[signal.symbol].index:
                        price = current_data[signal.symbol].loc[date, 'close']
                        # Apply slippage (negative for sells)
                        slippage = price * (slippage_bps / 10000)
                        effective_price = price - slippage
                        proceeds = positions[signal.symbol] * effective_price
                        cash += proceeds - commission_per_trade
                        total_slippage += positions[signal.symbol] * slippage
                        total_commission += commission_per_trade
                        total_trades += 1
                        positions[signal.symbol] = 0
            
            total_value = cash
            for symbol, shares in positions.items():
                if shares > 0 and symbol in current_data and date in current_data[symbol].index:
                    total_value += shares * current_data[symbol].loc[date, 'close']
            
            for signal in signals:
                if signal.action == 'buy' and signal.weight > 0:
                    if signal.symbol in current_data and date in current_data[signal.symbol].index:
                        price = current_data[signal.symbol].loc[date, 'close']
                        # Apply slippage (positive for buys)
                        slippage = price * (slippage_bps / 10000)
                        effective_price = price + slippage
                        target_value = total_value * signal.weight
                        shares = int(target_value / effective_price)
                        cost = shares * effective_price + commission_per_trade
                        if cost <= cash and shares > 0:
                            positions[signal.symbol] = positions.get(signal.symbol, 0) + shares
                            cash -= cost
                            total_slippage += shares * slippage
                            total_commission += commission_per_trade
                            total_trades += 1
        
        total_value = cash
        for symbol, shares in positions.items():
            if shares > 0 and symbol in current_data and date in current_data[symbol].index:
                total_value += shares * current_data[symbol].loc[date, 'close']
        
        portfolio_values.append({'date': date, 'value': total_value})
    
    return portfolio_values, total_trades, total_slippage, total_commission


def calculate_metrics(portfolio_values, initial_capital):
    """Calculate comprehensive metrics."""
    if not portfolio_values or len(portfolio_values) < 2:
        return None
    
    values = [pv['value'] for pv in portfolio_values]
    dates = [pv['date'] for pv in portfolio_values]
    
    start_value = initial_capital
    end_value = values[-1]
    total_return = (end_value - start_value) / start_value
    
    # Max drawdown
    peak = start_value
    max_dd = 0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd
    
    # Annualized return
    days = (dates[-1] - dates[0]).days
    years = days / 365 if days > 0 else 1
    cagr = ((1 + total_return) ** (1/years) - 1) if years > 0 else 0
    
    # Sharpe ratio
    returns = pd.Series(values).pct_change().dropna()
    if len(returns) > 0 and returns.std() > 0:
        sharpe = (returns.mean() * 252) / (returns.std() * np.sqrt(252))
    else:
        sharpe = 0
    
    return {
        'total_return': total_return * 100,
        'cagr': cagr * 100,
        'max_drawdown': max_dd * 100,
        'sharpe': sharpe,
        'final_value': end_value
    }


def main():
    print("\n" + "=" * 70)
    print("STRATEGY ROBUSTNESS VALIDATION")
    print("=" * 70)
    
    # Load data
    provider = CSVDataProvider()
    symbols = ["SPY", "QQQ", "IWM"]
    data = {}
    
    print("\n📊 Loading data...")
    for symbol in symbols:
        data[symbol] = provider.get_historical_data(symbol)
        print(f"   {symbol}: {len(data[symbol])} bars")
    
    initial_capital = 100000
    
    # =========================================================================
    # 1. PARAMETER SENSITIVITY ANALYSIS
    # =========================================================================
    print("\n" + "-" * 70)
    print("1. OVERFITTING CHECK: Parameter Sensitivity")
    print("-" * 70)
    
    base_lookback = 126
    base_trend = 200
    
    lookbacks = [int(base_lookback * 0.8), base_lookback, int(base_lookback * 1.2)]
    trends = [int(base_trend * 0.8), base_trend, int(base_trend * 1.2)]
    
    sensitivity_results = []
    
    for lb in lookbacks:
        for tr in trends:
            strategy = EnhancedDualMomentum(lookback_momentum=lb, lookback_trend=tr)
            pv, _, _, _ = run_backtest_with_costs(strategy, data, initial_capital, slippage_bps=0)
            metrics = calculate_metrics(pv, initial_capital)
            if metrics:
                sensitivity_results.append({
                    'lookback': lb,
                    'trend': tr,
                    'cagr': metrics['cagr'],
                    'sharpe': metrics['sharpe'],
                    'max_dd': metrics['max_drawdown']
                })
    
    cagrs = [r['cagr'] for r in sensitivity_results]
    cagr_mean = np.mean(cagrs)
    cagr_std = np.std(cagrs)
    cagr_range = max(cagrs) - min(cagrs)
    
    print(f"   Parameter variations tested: {len(sensitivity_results)}")
    print(f"   CAGR range: {min(cagrs):.2f}% to {max(cagrs):.2f}%")
    print(f"   CAGR std dev: {cagr_std:.2f}%")
    print(f"   CAGR coefficient of variation: {(cagr_std/cagr_mean)*100:.1f}%")
    
    # Flag overfitting if CV > 30%
    overfit_flag = (cagr_std / cagr_mean) > 0.30 if cagr_mean > 0 else True
    print(f"\n   OVERFITTING RISK: {'⚠️  HIGH' if overfit_flag else '✅ LOW'}")
    
    # =========================================================================
    # 2. OUT-OF-SAMPLE VALIDATION
    # =========================================================================
    print("\n" + "-" * 70)
    print("2. OUT-OF-SAMPLE VALIDATION")
    print("-" * 70)
    
    # Split data: first 70% = in-sample, last 30% = out-of-sample
    in_sample_data = {}
    out_sample_data = {}
    
    for symbol, df in data.items():
        split_idx = int(len(df) * 0.7)
        in_sample_data[symbol] = df.iloc[:split_idx]
        out_sample_data[symbol] = df.iloc[split_idx:]
    
    strategy = EnhancedDualMomentum(lookback_momentum=126, lookback_trend=200)
    
    # In-sample
    pv_in, _, _, _ = run_backtest_with_costs(strategy, in_sample_data, initial_capital, slippage_bps=0)
    metrics_in = calculate_metrics(pv_in, initial_capital)
    
    # Out-of-sample
    pv_out, _, _, _ = run_backtest_with_costs(strategy, out_sample_data, initial_capital, slippage_bps=0)
    metrics_out = calculate_metrics(pv_out, initial_capital)
    
    if metrics_in and metrics_out:
        print(f"\n   {'Metric':<20} {'In-Sample':<15} {'Out-of-Sample':<15} {'Degradation'}")
        print(f"   {'-'*65}")
        
        cagr_deg = metrics_in['cagr'] - metrics_out['cagr']
        sharpe_deg = metrics_in['sharpe'] - metrics_out['sharpe']
        
        print(f"   {'CAGR':<20} {metrics_in['cagr']:>+10.2f}%    {metrics_out['cagr']:>+10.2f}%    {cagr_deg:>+.2f}%")
        print(f"   {'Sharpe':<20} {metrics_in['sharpe']:>10.2f}     {metrics_out['sharpe']:>10.2f}     {sharpe_deg:>+.2f}")
        print(f"   {'Max Drawdown':<20} {metrics_in['max_drawdown']:>10.2f}%    {metrics_out['max_drawdown']:>10.2f}%")
        
        # Significant degradation if CAGR drops by more than 50%
        oos_flag = cagr_deg > (metrics_in['cagr'] * 0.5) if metrics_in['cagr'] > 0 else False
        print(f"\n   OUT-OF-SAMPLE: {'⚠️  SIGNIFICANT DEGRADATION' if oos_flag else '✅ ACCEPTABLE'}")
    else:
        print("   ❌ Insufficient data for out-of-sample test")
        oos_flag = True
    
    # =========================================================================
    # 3. DRAWDOWN ANALYSIS
    # =========================================================================
    print("\n" + "-" * 70)
    print("3. REGIME & DRAWDOWN ANALYSIS")
    print("-" * 70)
    
    pv_full, _, _, _ = run_backtest_with_costs(strategy, data, initial_capital, slippage_bps=0)
    
    if pv_full and len(pv_full) > 0:
        values = [pv['value'] for pv in pv_full]
        dates = [pv['date'] for pv in pv_full]
        
        # Find max drawdown period
        peak = initial_capital
        peak_date = dates[0]
        max_dd = 0
        max_dd_start = dates[0]
        max_dd_end = dates[0]
        
        for d, v in zip(dates, values):
            if v > peak:
                peak = v
                peak_date = d
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
                max_dd_start = peak_date
                max_dd_end = d
        
        print(f"   Max drawdown: {max_dd*100:.2f}%")
        print(f"   Drawdown period: {max_dd_start.strftime('%Y-%m-%d')} to {max_dd_end.strftime('%Y-%m-%d')}")
        print(f"   Drawdown duration: {(max_dd_end - max_dd_start).days} days")
        
        # Check if trend filter helped (compare to baseline)
        baseline = EnhancedDualMomentum(lookback_momentum=126, lookback_trend=200, use_sharpe_ranking=False)
        pv_base, _, _, _ = run_backtest_with_costs(baseline, data, initial_capital, slippage_bps=0)
        metrics_base = calculate_metrics(pv_base, initial_capital)
        metrics_enhanced = calculate_metrics(pv_full, initial_capital)
        
        if metrics_base and metrics_enhanced:
            # Calmar ratio = CAGR / Max DD
            calmar_base = metrics_base['cagr'] / metrics_base['max_drawdown'] if metrics_base['max_drawdown'] > 0 else 0
            calmar_enhanced = metrics_enhanced['cagr'] / metrics_enhanced['max_drawdown'] if metrics_enhanced['max_drawdown'] > 0 else 0
            
            print(f"\n   Risk-Adjusted Comparison:")
            print(f"   {'Metric':<20} {'Baseline':<15} {'Enhanced':<15}")
            print(f"   {'-'*50}")
            print(f"   {'Sharpe':<20} {metrics_base['sharpe']:>10.2f}     {metrics_enhanced['sharpe']:>10.2f}")
            print(f"   {'Calmar':<20} {calmar_base:>10.2f}     {calmar_enhanced:>10.2f}")
            
            risk_improved = calmar_enhanced > calmar_base
            print(f"\n   RISK-ADJUSTED: {'✅ IMPROVED' if risk_improved else '⚠️  NOT IMPROVED'}")
        else:
            risk_improved = False
    else:
        risk_improved = False
    
    # =========================================================================
    # 4. TRANSACTION COST ANALYSIS
    # =========================================================================
    print("\n" + "-" * 70)
    print("4. TRANSACTION COST & REALISM CHECK")
    print("-" * 70)
    
    # Test with realistic costs
    slippage_scenarios = [0, 5, 10, 20]  # basis points
    
    print(f"\n   {'Slippage (bps)':<20} {'CAGR':<12} {'# Trades':<12} {'Total Cost'}")
    print(f"   {'-'*60}")
    
    cost_results = []
    for slip in slippage_scenarios:
        pv, trades, slippage_cost, commission = run_backtest_with_costs(
            strategy, data, initial_capital, slippage_bps=slip, commission_per_trade=1.0
        )
        metrics = calculate_metrics(pv, initial_capital)
        if metrics:
            total_cost = slippage_cost + commission
            cost_results.append({'slip': slip, 'cagr': metrics['cagr'], 'trades': trades, 'cost': total_cost})
            print(f"   {slip:<20} {metrics['cagr']:>+8.2f}%    {trades:<12} ${total_cost:>,.0f}")
    
    # Impact of realistic costs
    if len(cost_results) >= 2:
        cagr_no_cost = cost_results[0]['cagr']
        cagr_realistic = cost_results[2]['cagr'] if len(cost_results) > 2 else cost_results[-1]['cagr']
        cost_impact = cagr_no_cost - cagr_realistic
        
        print(f"\n   Cost impact on CAGR: {cost_impact:+.2f}% (with 10bps slippage)")
        
        cost_excessive = cost_impact > 2.0  # More than 2% CAGR impact
        print(f"   TRANSACTION COSTS: {'⚠️  EXCESSIVE' if cost_excessive else '✅ ACCEPTABLE'}")
    else:
        cost_excessive = False
    
    # =========================================================================
    # FINAL VERDICT
    # =========================================================================
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    
    checks = {
        'Overfitting (Parameter Sensitivity)': 'FAIL' if overfit_flag else 'PASS',
        'Out-of-Sample Performance': 'FAIL' if oos_flag else 'PASS',
        'Risk-Adjusted Improvement': 'PASS' if risk_improved else 'FAIL',
        'Transaction Cost Impact': 'FAIL' if cost_excessive else 'PASS'
    }
    
    print(f"\n   {'Check':<40} {'Result'}")
    print(f"   {'-'*50}")
    for check, result in checks.items():
        icon = '✅' if result == 'PASS' else '❌'
        print(f"   {check:<40} {icon} {result}")
    
    passed = sum(1 for r in checks.values() if r == 'PASS')
    total = len(checks)
    
    print(f"\n   Overall: {passed}/{total} checks passed")
    
    # Decision
    print("\n" + "-" * 70)
    print("RECOMMENDATION")
    print("-" * 70)
    
    if passed == total:
        print("\n   ✅ PROCEED")
        print("   Strategy appears robust. Recommend:")
        print("   1. Push code to GitHub")
        print("   2. Begin paper trading with Enhanced Dual Momentum")
    elif passed >= 3:
        print("\n   ⚠️  PROCEED WITH CAUTION")
        print("   Strategy shows promise but has weaknesses.")
        print("   Recommend:")
        print("   1. Push code to GitHub (document known issues)")
        print("   2. Paper trade with smaller position sizes")
        print("   3. Monitor out-of-sample performance closely")
    elif passed >= 2:
        print("\n   ⏸️  HOLD")
        print("   Strategy requires further investigation before deployment.")
        print("   Recommend:")
        print("   1. Identify root cause of failing checks")
        print("   2. Consider simpler baseline strategy")
        print("   3. Do NOT push as production-ready")
    else:
        print("\n   🔙 ROLL BACK")
        print("   Strategy shows significant overfitting or fragility.")
        print("   Recommend:")
        print("   1. Revert to baseline Dual Momentum")
        print("   2. Investigate alternative improvements")
    
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
