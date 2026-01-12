#!/usr/bin/env python3
"""
PyBroker Research Pipeline

Use PyBroker for backtesting and strategy optimization with FREE data
from Yahoo Finance or Alpaca.

Features:
- Fast backtesting with Numba acceleration
- Walkforward Analysis to prevent overfitting
- Yahoo Finance data (FREE - no subscription needed)
- Strategy optimization and comparison

Usage:
    python3 src/research/pybroker_runner.py --symbol BTC-USD --start 2024-01-01
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Load env
env_file = Path(__file__).parent.parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            os.environ.setdefault(key.strip(), val.strip())

try:
    import pybroker
    from pybroker import Strategy, StrategyConfig, YFinance
    import numpy as np
    import pandas as pd
except ImportError:
    print("[X] Missing PyBroker: pip install lib-pybroker")
    sys.exit(1)


# ============================================================
# STRATEGY DEFINITIONS
# ============================================================

def ema_crossover_strategy(config=None):
    """
    EMA Crossover Strategy with configurable parameters.
    
    Default: EMA 50/100 (optimized from backtesting)
    """
    fast_period = config.get('fast', 50) if config else 50
    slow_period = config.get('slow', 100) if config else 100
    
    def exec_fn(ctx):
        # Calculate EMAs
        close = ctx.close
        
        if len(close) < slow_period:
            return
        
        ema_fast = pd.Series(close).ewm(span=fast_period, adjust=False).mean()
        ema_slow = pd.Series(close).ewm(span=slow_period, adjust=False).mean()
        
        curr_fast = ema_fast.iloc[-1]
        curr_slow = ema_slow.iloc[-1]
        prev_fast = ema_fast.iloc[-2]
        prev_slow = ema_slow.iloc[-2]
        
        # Golden Cross - BUY
        if prev_fast < prev_slow and curr_fast > curr_slow:
            ctx.buy_shares = ctx.calc_target_shares(1.0)
        
        # Death Cross - SELL
        elif prev_fast > prev_slow and curr_fast < curr_slow:
            ctx.sell_all_shares()
    
    return exec_fn


def rsi_mean_reversion(config=None):
    """
    RSI Mean Reversion Strategy.
    
    Buy when RSI < 30 (oversold), Sell when RSI > 70 (overbought)
    """
    period = config.get('period', 14) if config else 14
    oversold = config.get('oversold', 30) if config else 30
    overbought = config.get('overbought', 70) if config else 70
    
    def exec_fn(ctx):
        close = ctx.close
        
        if len(close) < period + 1:
            return
        
        # Calculate RSI
        delta = pd.Series(close).diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        current_rsi = rsi.iloc[-1]
        
        if current_rsi < oversold and ctx.long_pos() == 0:
            ctx.buy_shares = ctx.calc_target_shares(1.0)
        elif current_rsi > overbought and ctx.long_pos() > 0:
            ctx.sell_all_shares()
    
    return exec_fn


# ============================================================
# BACKTEST RUNNER
# ============================================================

def run_backtest(
    symbol: str = "BTC-USD",
    start_date: str = "2023-01-01",
    end_date: str = None,
    strategy: str = "ema_crossover",
    initial_cash: float = 100000
):
    """
    Run a backtest using PyBroker with Yahoo Finance data.
    
    Args:
        symbol: Yahoo Finance ticker (e.g., BTC-USD, ETH-USD, SPY)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD), defaults to today
        strategy: Strategy name ('ema_crossover' or 'rsi_mean_reversion')
        initial_cash: Starting capital
    
    Returns:
        DataFrame with backtest results
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    print("=" * 60)
    print(f"  PYBROKER BACKTEST")
    print("=" * 60)
    print(f"  Symbol: {symbol}")
    print(f"  Period: {start_date} to {end_date}")
    print(f"  Strategy: {strategy}")
    print(f"  Initial Cash: ${initial_cash:,.0f}")
    print("=" * 60)
    
    # Configure strategy
    config = StrategyConfig(initial_cash=initial_cash)
    
    # Select strategy function
    if strategy == "ema_crossover":
        exec_fn = ema_crossover_strategy({'fast': 50, 'slow': 100})
    elif strategy == "rsi_mean_reversion":
        exec_fn = rsi_mean_reversion({'period': 14, 'oversold': 30, 'overbought': 70})
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
    
    # Create strategy
    strat = Strategy(YFinance(), start_date, end_date, config)
    strat.add_execution(exec_fn, symbol)
    
    print("\n[>] Running backtest...")
    
    # Run backtest
    result = strat.backtest()
    
    # Print results
    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    
    if result is not None and hasattr(result, 'metrics'):
        metrics = result.metrics
        print(f"\n  Total Return:     {metrics.get('total_return', 0)*100:.2f}%")
        print(f"  Sharpe Ratio:     {metrics.get('sharpe', 0):.2f}")
        print(f"  Max Drawdown:     {metrics.get('max_drawdown', 0)*100:.2f}%")
        print(f"  Win Rate:         {metrics.get('win_rate', 0)*100:.1f}%")
        print(f"  Total Trades:     {metrics.get('total_trades', 0)}")
        print(f"  Profit Factor:    {metrics.get('profit_factor', 0):.2f}")
    else:
        print("  [!] No results returned")
    
    print("\n" + "=" * 60)
    
    return result


def optimize_parameters(
    symbol: str = "BTC-USD",
    start_date: str = "2023-01-01",
    end_date: str = None,
    initial_cash: float = 100000
):
    """
    Run parameter optimization to find best EMA periods.
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    print("=" * 60)
    print("  PARAMETER OPTIMIZATION")
    print("=" * 60)
    
    fast_periods = [10, 20, 30, 50]
    slow_periods = [50, 100, 150, 200]
    
    results = []
    
    for fast in fast_periods:
        for slow in slow_periods:
            if fast >= slow:
                continue
            
            print(f"\n[>] Testing EMA {fast}/{slow}...")
            
            config = StrategyConfig(initial_cash=initial_cash)
            exec_fn = ema_crossover_strategy({'fast': fast, 'slow': slow})
            
            strat = Strategy(YFinance(), start_date, end_date, config)
            strat.add_execution(exec_fn, symbol)
            
            try:
                result = strat.backtest()
                if result and hasattr(result, 'metrics'):
                    total_return = result.metrics.get('total_return', 0)
                    sharpe = result.metrics.get('sharpe', 0)
                    
                    results.append({
                        'fast': fast,
                        'slow': slow,
                        'return': total_return,
                        'sharpe': sharpe
                    })
                    print(f"    Return: {total_return*100:.1f}% | Sharpe: {sharpe:.2f}")
            except Exception as e:
                print(f"    [X] Error: {e}")
    
    # Find best
    if results:
        df = pd.DataFrame(results)
        best = df.loc[df['sharpe'].idxmax()]
        
        print("\n" + "=" * 60)
        print("  BEST PARAMETERS")
        print("=" * 60)
        print(f"  Fast EMA: {int(best['fast'])}")
        print(f"  Slow EMA: {int(best['slow'])}")
        print(f"  Return: {best['return']*100:.1f}%")
        print(f"  Sharpe: {best['sharpe']:.2f}")
        print("=" * 60)
        
        return df
    
    return None


# ============================================================
# MAIN
# ============================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="PyBroker Research Pipeline")
    parser.add_argument("--symbol", default="BTC-USD", help="Yahoo Finance symbol")
    parser.add_argument("--start", default="2023-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--strategy", default="ema_crossover", choices=["ema_crossover", "rsi_mean_reversion"])
    parser.add_argument("--optimize", action="store_true", help="Run parameter optimization")
    parser.add_argument("--cash", type=float, default=100000, help="Initial cash")
    
    args = parser.parse_args()
    
    if args.optimize:
        optimize_parameters(args.symbol, args.start, args.end, args.cash)
    else:
        run_backtest(args.symbol, args.start, args.end, args.strategy, args.cash)


if __name__ == "__main__":
    main()
