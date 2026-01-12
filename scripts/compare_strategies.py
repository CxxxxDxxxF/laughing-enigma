#!/usr/bin/env python3
"""Strategy Comparison Script.

Compare multiple strategies on historical data to find the best performer.

Usage:
    python scripts/compare_strategies.py --symbols SPY QQQ IWM --years 5
"""

import sys
from pathlib import Path
from datetime import datetime
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.csv_provider import CSVDataProvider
from src.strategy.enhanced_strategies import (
    EnhancedDualMomentum,
    RSIMeanReversion,
    BollingerBands,
    MovingAverageCrossover
)


def run_backtest(strategy, data, initial_capital=100000):
    """Run backtest for a single strategy."""
    cash = initial_capital
    positions = {}
    portfolio_values = []
    
    # Get aligned dates
    all_dates = set()
    for df in data.values():
        all_dates.update(df.index.tolist())
    dates = sorted(all_dates)
    
    # Need at least 200 bars for 200-day SMA
    start_idx = 200
    
    for i, date in enumerate(dates[start_idx:], start_idx):
        # Prepare data up to current date
        current_data = {}
        for symbol, df in data.items():
            mask = df.index <= date
            if mask.any():
                current_data[symbol] = df[mask].copy()
        
        if not current_data:
            continue
        
        # Get current position weights
        current_weights = {}
        total_value = cash
        for symbol in positions:
            if symbol in current_data and date in current_data[symbol].index:
                price = current_data[symbol].loc[date, 'close']
                total_value += positions[symbol] * price
                current_weights[symbol] = (positions[symbol] * price) / total_value if total_value > 0 else 0
        
        # Rebalance weekly
        if i % 5 == 0:
            signals = strategy.generate_signals(current_data, current_weights)
            
            # Sell first
            for signal in signals:
                if signal.action == 'sell' and signal.symbol in positions:
                    if date in current_data[signal.symbol].index:
                        price = current_data[signal.symbol].loc[date, 'close']
                        cash += positions[signal.symbol] * price
                        positions[signal.symbol] = 0
            
            # Recalculate total value
            total_value = cash
            for symbol, shares in positions.items():
                if shares > 0 and symbol in current_data and date in current_data[symbol].index:
                    total_value += shares * current_data[symbol].loc[date, 'close']
            
            # Buy
            for signal in signals:
                if signal.action == 'buy' and signal.weight > 0:
                    if signal.symbol in current_data and date in current_data[signal.symbol].index:
                        price = current_data[signal.symbol].loc[date, 'close']
                        target_value = total_value * signal.weight
                        shares = int(target_value / price)
                        cost = shares * price
                        if cost <= cash and shares > 0:
                            positions[signal.symbol] = positions.get(signal.symbol, 0) + shares
                            cash -= cost
        
        # Calculate portfolio value
        total_value = cash
        for symbol, shares in positions.items():
            if shares > 0 and symbol in current_data and date in current_data[symbol].index:
                total_value += shares * current_data[symbol].loc[date, 'close']
        
        portfolio_values.append({'date': date, 'value': total_value})
    
    return portfolio_values


def calculate_metrics(portfolio_values, initial_capital):
    """Calculate performance metrics."""
    if not portfolio_values:
        return {}
    
    start_value = initial_capital
    end_value = portfolio_values[-1]['value']
    total_return = (end_value - start_value) / start_value * 100
    
    # Max drawdown
    peak = start_value
    max_dd = 0
    for pv in portfolio_values:
        if pv['value'] > peak:
            peak = pv['value']
        dd = (peak - pv['value']) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    # Annualized return
    days = (portfolio_values[-1]['date'] - portfolio_values[0]['date']).days
    years = days / 365 if days > 0 else 1
    annual_return = ((1 + total_return/100) ** (1/years) - 1) * 100 if years > 0 else 0
    
    return {
        'total_return': total_return,
        'annual_return': annual_return,
        'max_drawdown': max_dd,
        'final_value': end_value
    }


def main():
    parser = argparse.ArgumentParser(description="Compare Trading Strategies")
    parser.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "IWM"])
    parser.add_argument("--capital", type=float, default=100000)
    
    args = parser.parse_args()
    
    # Load data
    provider = CSVDataProvider()
    data = {}
    
    print("\n📊 Loading data...")
    for symbol in args.symbols:
        try:
            data[symbol] = provider.get_historical_data(symbol)
            print(f"   ✓ {symbol}: {len(data[symbol])} bars")
        except FileNotFoundError:
            print(f"   ✗ {symbol}: Not found - run offline_backtest.py --download first")
            return
    
    # Define strategies
    strategies = {
        "Enhanced Dual Momentum": EnhancedDualMomentum(
            lookback_momentum=126,
            use_sharpe_ranking=True
        ),
        "RSI Mean Reversion": RSIMeanReversion(
            rsi_period=14,
            oversold=30,
            overbought=70
        ),
        "Bollinger Bands": BollingerBands(
            period=20,
            std_dev=2.0,
            mode='mean_reversion'
        ),
        "MA Crossover (50/200)": MovingAverageCrossover(
            fast_period=50,
            slow_period=200
        )
    }
    
    print("\n🔄 Running backtests...")
    print("-" * 70)
    
    results = []
    
    for name, strategy in strategies.items():
        print(f"   Testing: {name}...", end=" ")
        portfolio = run_backtest(strategy, data, args.capital)
        metrics = calculate_metrics(portfolio, args.capital)
        
        if metrics:
            results.append({
                'name': name,
                **metrics
            })
            print(f"Return: {metrics['total_return']:+.1f}%")
        else:
            print("Failed")
    
    # Sort by annual return
    results.sort(key=lambda x: x['annual_return'], reverse=True)
    
    # Display results
    print("\n" + "=" * 70)
    print("📈 STRATEGY COMPARISON RESULTS")
    print("=" * 70)
    print(f"{'Strategy':<30} {'Ann. Ret.':<12} {'Tot. Ret.':<12} {'Max DD':<10} {'Final':<12}")
    print("-" * 70)
    
    for r in results:
        print(f"{r['name']:<30} {r['annual_return']:>+8.2f}%   {r['total_return']:>+8.2f}%   {r['max_drawdown']:>6.2f}%   ${r['final_value']:>10,.0f}")
    
    print("=" * 70)
    
    if results:
        best = results[0]
        print(f"\n🏆 Best Strategy: {best['name']}")
        print(f"   Annual Return: {best['annual_return']:+.2f}%")
        print(f"   Max Drawdown: {best['max_drawdown']:.2f}%\n")


if __name__ == "__main__":
    main()
