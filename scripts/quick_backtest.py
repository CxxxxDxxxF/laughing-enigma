#!/usr/bin/env python3
"""Quick Multi-Year Backtest for SPY/QQQ/IWM with optimal params"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import numpy as np

def run_backtest(tickers, lookback, threshold, years=5):
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    client = StockHistoricalDataClient(api_key, secret_key)

    end = datetime.now()
    start = end - timedelta(days=years * 365)

    print(f"[i] Fetching {years} years of data ({start.date()} to {end.date()})...")

    prices_dict = {}
    for ticker in tickers:
        request = StockBarsRequest(symbol_or_symbols=ticker, timeframe=TimeFrame.Day, start=start, end=end)
        bars = client.get_stock_bars(request).df
        if isinstance(bars.index, pd.MultiIndex):
            bars = bars.xs(ticker, level='symbol')
        prices_dict[ticker] = bars[['close']].rename(columns={'close': 'price'})
        print(f"   {ticker}: {len(prices_dict[ticker])} days")

    # Combine and backtest
    all_prices = pd.DataFrame({t: df['price'] for t, df in prices_dict.items()}).dropna()
    print(f"\n[OK] Combined dataset: {len(all_prices)} trading days")

    initial_capital = 100000.0
    momentum = all_prices.pct_change(lookback)
    portfolio_values = [initial_capital]
    positions = {t: 0 for t in tickers}
    cash = initial_capital

    print(f"\n[~] Backtesting: Lookback={lookback}, Threshold={threshold*100:.0f}%\n")

    for i in range(lookback, len(all_prices) - 1):
        current_prices = all_prices.iloc[i]
        next_prices = all_prices.iloc[i + 1]
        current_momentum = momentum.iloc[i]
        
        to_hold = [t for t in tickers if current_momentum[t] > threshold]
        
        # Sell what we don't want
        for ticker in list(positions.keys()):
            if positions[ticker] > 0 and ticker not in to_hold:
                cash += positions[ticker] * current_prices[ticker]
                positions[ticker] = 0
        
        # Buy equal weight
        if to_hold:
            portfolio_value = cash + sum(positions[t] * current_prices[t] for t in positions)
            target = portfolio_value / len(to_hold)
            for ticker in to_hold:
                current_value = positions[ticker] * current_prices[ticker]
                delta_value = target - current_value
                delta_shares = delta_value / current_prices[ticker]
                if delta_shares > 0 and delta_value <= cash:
                    positions[ticker] += delta_shares
                    cash -= delta_value
                elif delta_shares < 0:
                    shares_to_sell = min(-delta_shares, positions[ticker])
                    cash += shares_to_sell * current_prices[ticker]
                    positions[ticker] -= shares_to_sell
        
        next_value = cash + sum(positions[t] * next_prices[t] for t in positions)
        portfolio_values.append(next_value)

    # Calculate metrics
    portfolio_series = pd.Series(portfolio_values)
    returns = portfolio_series.pct_change().dropna()

    total_return = (portfolio_values[-1] - initial_capital) / initial_capital
    annual_return = (1 + total_return) ** (252 / len(returns)) - 1 if len(returns) > 0 else 0
    sharpe = (returns.mean() * 252) / (returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
    peak = portfolio_series.expanding().max()
    drawdown = (portfolio_series - peak) / peak
    max_dd = drawdown.min()
    win_rate = (returns > 0).mean() if len(returns) > 0 else 0

    print("=" * 60)
    print(f"  [+] {years}-YEAR BACKTEST RESULTS")
    print("=" * 60)
    print(f"  Strategy: Dual Momentum (Lookback={lookback}, Threshold={threshold*100:.0f}%)")
    print(f"  Tickers: {', '.join(tickers)}")
    print(f"  Period: {start.date()} to {end.date()}")
    print("=" * 60)
    print(f"  Initial Capital: ${initial_capital:,.0f}")
    print(f"  Final Value:     ${portfolio_values[-1]:,.0f}")
    print(f"  Total Return:    {total_return*100:+.1f}%")
    print(f"  Annual Return:   {annual_return*100:+.1f}%")
    print(f"  Sharpe Ratio:    {sharpe:.2f}")
    print(f"  Max Drawdown:    {max_dd*100:.1f}%")
    print(f"  Win Rate:        {win_rate*100:.1f}%")
    print("=" * 60)
    print(f"  💰 Profit: ${portfolio_values[-1] - initial_capital:+,.0f}")
    print("=" * 60)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Quick Backtest")
    parser.add_argument("--tickers", nargs="+", default=["SPY", "QQQ", "IWM"])
    parser.add_argument("--lookback", type=int, default=189)
    parser.add_argument("--threshold", type=float, default=0.10)
    parser.add_argument("--years", type=int, default=5)
    
    args = parser.parse_args()
    run_backtest(args.tickers, args.lookback, args.threshold, args.years)
