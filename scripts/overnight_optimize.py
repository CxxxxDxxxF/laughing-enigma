#!/usr/bin/env python3
"""
Overnight Optimization Script

Runs during off-hours to find optimal strategy parameters:
1. Downloads historical data for tickers
2. Backtests multiple parameter combinations
3. Ranks by Sharpe ratio and max drawdown
4. Outputs best parameters for next trading day

Usage:
    python3 scripts/overnight_optimize.py --tickers SPY QQQ IWM
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
import itertools

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try to import dependencies
try:
    import numpy as np
    import pandas as pd
except ImportError:
    print("[X] Missing dependencies. Run: pip install numpy pandas")
    sys.exit(1)


def fetch_historical_data(ticker: str, days: int = 365) -> pd.DataFrame:
    """Fetch historical price data from Alpaca."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        
        api_key = os.getenv("ALPACA_API_KEY")
        secret_key = os.getenv("ALPACA_SECRET_KEY")
        
        client = StockHistoricalDataClient(api_key, secret_key)
        
        end = datetime.now()
        start = end - timedelta(days=days)
        
        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame.Day,
            start=start,
            end=end
        )
        
        bars = client.get_stock_bars(request)
        df = bars.df
        
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(ticker, level='symbol')
        
        return df[['close']].rename(columns={'close': 'price'})
        
    except Exception as e:
        print(f"[!] Failed to fetch {ticker}: {e}")
        return pd.DataFrame()


def calculate_momentum_returns(prices: pd.Series, lookback: int) -> pd.Series:
    """Calculate momentum returns over lookback period."""
    return prices.pct_change(lookback)


def backtest_momentum_strategy(
    prices_dict: Dict[str, pd.DataFrame],
    lookback_days: int,
    threshold: float,
    initial_capital: float = 100000.0
) -> Dict[str, float]:
    """
    Backtest dual momentum strategy on multiple tickers.
    
    Returns metrics: total_return, sharpe, max_drawdown, win_rate
    """
    # Combine all prices
    all_prices = pd.DataFrame({
        ticker: df['price'] for ticker, df in prices_dict.items() if not df.empty
    }).dropna()
    
    if all_prices.empty or len(all_prices) < lookback_days + 50:
        return {"total_return": 0, "sharpe": 0, "max_drawdown": -1, "win_rate": 0}
    
    # Calculate momentum for each ticker
    momentum = all_prices.pct_change(lookback_days)
    
    # Portfolio value tracking
    portfolio_values = [initial_capital]
    positions = {ticker: 0 for ticker in all_prices.columns}
    cash = initial_capital
    
    # Simulate trading
    for i in range(lookback_days, len(all_prices) - 1):
        current_prices = all_prices.iloc[i]
        next_prices = all_prices.iloc[i + 1]
        current_momentum = momentum.iloc[i]
        
        # Determine which tickers to hold (momentum > threshold)
        to_hold = [t for t in all_prices.columns if current_momentum[t] > threshold]
        
        # Rebalance: sell what we don't want, buy what we want
        # First, sell
        for ticker in list(positions.keys()):
            if positions[ticker] > 0 and ticker not in to_hold:
                cash += positions[ticker] * current_prices[ticker]
                positions[ticker] = 0
        
        # Then, buy equal weight in selected tickers
        if to_hold:
            portfolio_value = cash + sum(positions[t] * current_prices[t] for t in positions)
            target_value_per_ticker = portfolio_value / len(to_hold)
            
            for ticker in to_hold:
                current_value = positions[ticker] * current_prices[ticker]
                delta_value = target_value_per_ticker - current_value
                delta_shares = delta_value / current_prices[ticker]
                
                if delta_shares > 0:
                    cost = delta_shares * current_prices[ticker]
                    if cost <= cash:
                        positions[ticker] += delta_shares
                        cash -= cost
                elif delta_shares < 0:
                    shares_to_sell = min(-delta_shares, positions[ticker])
                    cash += shares_to_sell * current_prices[ticker]
                    positions[ticker] -= shares_to_sell
        
        # Calculate portfolio value at next day's prices
        next_value = cash + sum(positions[t] * next_prices[t] for t in positions)
        portfolio_values.append(next_value)
    
    # Calculate metrics
    portfolio_series = pd.Series(portfolio_values)
    returns = portfolio_series.pct_change().dropna()
    
    total_return = (portfolio_values[-1] - initial_capital) / initial_capital
    
    # Sharpe ratio (annualized, assuming 252 trading days)
    if returns.std() > 0:
        sharpe = (returns.mean() * 252) / (returns.std() * np.sqrt(252))
    else:
        sharpe = 0
    
    # Max drawdown
    peak = portfolio_series.expanding().max()
    drawdown = (portfolio_series - peak) / peak
    max_drawdown = drawdown.min()
    
    # Win rate
    win_rate = (returns > 0).sum() / len(returns) if len(returns) > 0 else 0
    
    return {
        "total_return": round(total_return * 100, 2),  # percentage
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(max_drawdown * 100, 2),  # percentage
        "win_rate": round(win_rate * 100, 2),  # percentage
        "final_value": round(portfolio_values[-1], 2)
    }


def run_optimization(
    tickers: List[str],
    lookback_range: List[int] = [63, 126, 189, 252],
    threshold_range: List[float] = [0.05, 0.08, 0.10, 0.12, 0.15, 0.20]
) -> List[Dict[str, Any]]:
    """
    Run optimization over parameter grid.
    
    Returns sorted list of results (best first).
    """
    print(f"\n[~] Starting Overnight Optimization")
    print(f"   Tickers: {', '.join(tickers)}")
    print(f"   Lookback values: {lookback_range}")
    print(f"   Threshold values: {threshold_range}")
    print(f"   Total combinations: {len(lookback_range) * len(threshold_range)}")
    print()
    
    # Fetch historical data for all tickers
    print("[i] Fetching historical data...")
    prices_dict = {}
    for ticker in tickers:
        print(f"   Downloading {ticker}...", end=" ")
        df = fetch_historical_data(ticker, days=500)  # ~2 years
        if not df.empty:
            prices_dict[ticker] = df
            print(f"[OK] {len(df)} days")
        else:
            print("[X] Failed")
    
    if not prices_dict:
        print("[X] No data fetched. Check Alpaca credentials.")
        return []
    
    # Run backtests for each parameter combination
    print("\n[~] Running backtests...")
    results = []
    
    for lookback in lookback_range:
        for threshold in threshold_range:
            metrics = backtest_momentum_strategy(
                prices_dict,
                lookback_days=lookback,
                threshold=threshold
            )
            
            result = {
                "lookback_days": lookback,
                "threshold": threshold,
                **metrics
            }
            results.append(result)
            
            print(f"   Lookback={lookback:3d} Threshold={threshold:.2f} → "
                  f"Return={metrics['total_return']:+6.1f}% "
                  f"Sharpe={metrics['sharpe']:5.2f} "
                  f"MaxDD={metrics['max_drawdown']:6.1f}%")
    
    # Sort by Sharpe ratio (higher is better)
    results.sort(key=lambda x: x['sharpe'], reverse=True)
    
    return results


def save_results(results: List[Dict], output_path: Path):
    """Save optimization results to JSON."""
    output = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "best_params": results[0] if results else None
    }
    
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n[>] Results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Overnight Strategy Optimization")
    parser.add_argument("--tickers", nargs="+", default=["SPY", "QQQ", "IWM"],
                        help="Tickers to optimize (default: SPY QQQ IWM)")
    parser.add_argument("--output", type=str, default="data/optimization_results.json",
                        help="Output file for results")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  🌙 OVERNIGHT OPTIMIZATION")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    results = run_optimization(args.tickers)
    
    if results:
        # Save results
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_results(results, output_path)
        
        # Print top 5 results
        print("\n" + "=" * 60)
        print("  [#] TOP 5 PARAMETER COMBINATIONS")
        print("=" * 60)
        
        for i, r in enumerate(results[:5], 1):
            print(f"\n  #{i}: Lookback={r['lookback_days']} days, Threshold={r['threshold']:.0%}")
            print(f"      Total Return: {r['total_return']:+.1f}%")
            print(f"      Sharpe Ratio: {r['sharpe']:.2f}")
            print(f"      Max Drawdown: {r['max_drawdown']:.1f}%")
            print(f"      Win Rate: {r['win_rate']:.1f}%")
        
        # Recommend best params
        best = results[0]
        print("\n" + "=" * 60)
        print("  [>] RECOMMENDED PARAMETERS FOR TOMORROW")
        print("=" * 60)
        print(f"  lookback_days: {best['lookback_days']}")
        print(f"  threshold: {best['threshold']}")
        print(f"  Expected Sharpe: {best['sharpe']:.2f}")
        print("=" * 60)
    else:
        print("\n[X] Optimization failed. No results generated.")
    
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
