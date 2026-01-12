#!/usr/bin/env python3
"""Offline Backtesting Script.

Run backtests using local CSV data - no broker connection required.
Uses Yahoo Finance to download data, then runs strategy evaluation.

Usage:
    python scripts/offline_backtest.py --symbols SPY QQQ IWM --years 5
    python scripts/offline_backtest.py --download  # Download fresh data
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))


def download_data(symbols: list, years: int = 5):
    """Download historical data from Yahoo Finance."""
    from src.data.yahoo_provider import download_backtest_data
    
    print(f"\n📥 Downloading {years} years of data for: {', '.join(symbols)}")
    download_backtest_data(symbols, years=years)
    print("✅ Download complete\n")


def run_backtest(symbols: list, initial_capital: float = 100000):
    """Run backtest using local CSV data."""
    from src.data.csv_provider import CSVDataProvider
    from src.strategy.strategies.dual_momentum import DualMomentumStrategy
    
    print(f"\n📊 Running Dual Momentum Backtest")
    print(f"   Symbols: {', '.join(symbols)}")
    print(f"   Capital: ${initial_capital:,.0f}")
    print("-" * 50)
    
    # Load data
    provider = CSVDataProvider()
    available = provider.list_available_symbols()
    
    missing = [s for s in symbols if s not in available]
    if missing:
        print(f"❌ Missing data for: {', '.join(missing)}")
        print("   Run with --download flag first")
        return
    
    # Load all data
    data = {}
    for symbol in symbols:
        df = provider.get_historical_data(symbol)
        data[symbol] = df
        print(f"   Loaded {symbol}: {len(df)} bars")
    
    # Simple backtest simulation
    print("\n🔄 Simulating strategy...")
    
    # Get aligned dates
    all_dates = set()
    for df in data.values():
        all_dates.update(df.index.tolist())
    dates = sorted(all_dates)
    
    # Track portfolio
    cash = initial_capital
    positions = {s: 0 for s in symbols}
    portfolio_values = []
    
    lookback = 126  # 6 months
    threshold = 0.10  # 10% momentum threshold
    
    for i, date in enumerate(dates):
        if i < lookback:
            continue
        
        # Calculate momentum for each symbol
        momentum = {}
        for symbol in symbols:
            if date in data[symbol].index:
                current_idx = data[symbol].index.get_loc(date)
                if current_idx >= lookback:
                    current = data[symbol]['close'].iloc[current_idx]
                    past = data[symbol]['close'].iloc[current_idx - lookback]
                    momentum[symbol] = (current - past) / past
        
        # Rebalance logic (simplified)
        if i % 21 == 0:  # Monthly rebalance
            # Sell all positions
            for symbol in symbols:
                if positions[symbol] > 0 and date in data[symbol].index:
                    price = data[symbol].loc[date, 'close']
                    cash += positions[symbol] * price
                    positions[symbol] = 0
            
            # Buy symbols with momentum > threshold
            buy_symbols = [s for s, m in momentum.items() if m > threshold]
            if buy_symbols:
                allocation = cash / len(buy_symbols)
                for symbol in buy_symbols:
                    if date in data[symbol].index:
                        price = data[symbol].loc[date, 'close']
                        shares = int(allocation / price)
                        if shares > 0:
                            positions[symbol] = shares
                            cash -= shares * price
        
        # Calculate portfolio value
        total = cash
        for symbol in symbols:
            if positions[symbol] > 0 and date in data[symbol].index:
                total += positions[symbol] * data[symbol].loc[date, 'close']
        portfolio_values.append({'date': date, 'value': total})
    
    # Results
    if portfolio_values:
        start_value = initial_capital
        end_value = portfolio_values[-1]['value']
        total_return = (end_value - start_value) / start_value * 100
        
        # Calculate max drawdown
        peak = start_value
        max_dd = 0
        for pv in portfolio_values:
            if pv['value'] > peak:
                peak = pv['value']
            dd = (peak - pv['value']) / peak * 100
            if dd > max_dd:
                max_dd = dd
        
        years = (dates[-1] - dates[lookback]).days / 365
        annual_return = ((1 + total_return/100) ** (1/years) - 1) * 100 if years > 0 else 0
        
        print("\n" + "=" * 50)
        print("📈 BACKTEST RESULTS")
        print("=" * 50)
        print(f"   Start Date:    {dates[lookback].strftime('%Y-%m-%d')}")
        print(f"   End Date:      {dates[-1].strftime('%Y-%m-%d')}")
        print(f"   Initial:       ${start_value:,.2f}")
        print(f"   Final:         ${end_value:,.2f}")
        print(f"   Total Return:  {total_return:+.2f}%")
        print(f"   Annual Return: {annual_return:+.2f}%")
        print(f"   Max Drawdown:  {max_dd:.2f}%")
        print("=" * 50 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Offline Backtesting")
    parser.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "IWM"],
                        help="Symbols to backtest")
    parser.add_argument("--years", type=int, default=5,
                        help="Years of historical data")
    parser.add_argument("--capital", type=float, default=100000,
                        help="Initial capital")
    parser.add_argument("--download", action="store_true",
                        help="Download fresh data from Yahoo Finance")
    
    args = parser.parse_args()
    
    if args.download:
        download_data(args.symbols, args.years)
    
    run_backtest(args.symbols, args.capital)


if __name__ == "__main__":
    main()
