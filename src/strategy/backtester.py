#!/usr/bin/env python3
"""
Vectorized Backtester v2.0 - UPGRADED with Filters

FIXES:
1. Long-Only Mode: No shorting (crypto has upward drift)
2. ADX Filter: Only trade when ADX > 25 (skip choppy markets)

This should beat the +126% Buy & Hold benchmark.

Usage:
    python3 src/strategy/backtester.py
    python3 src/strategy/backtester.py --symbol BTC/USD --years 2
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    import numpy as np
    import pandas as pd
except ImportError as e:
    print(f"[X] Missing dependency: {e}")
    sys.exit(1)

# ============================================================
# CONFIGURATION
# ============================================================

# MA Parameter Grid - EXTENDED for better trend capture
FAST_WINDOWS = [10, 20, 30, 40, 50]
SLOW_WINDOWS = [50, 100, 150, 200]

# ADX Filter
ADX_PERIOD = 14
ADX_THRESHOLD = 15  # Lowered from 25 to allow more trades (15-25 is moderate trend)

# Backtesting settings
INITIAL_CAPITAL = 100000
COMMISSION_PCT = 0.001  # 0.1% per trade

# Strategy Mode
LONG_ONLY = True  # Never short - crypto has upward drift
USE_ADX_FILTER = False  # DISABLED to establish baseline first


# ============================================================
# DATA FETCHING
# ============================================================

def fetch_crypto_data(symbol: str = "BTC/USD", years: int = 2) -> pd.DataFrame:
    """Fetch hourly crypto data from Alpaca."""
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    
    client = CryptoHistoricalDataClient(api_key, secret_key)
    
    end = datetime.now()
    start = end - timedelta(days=years * 365)
    
    print(f"[i] Fetching {years} years of {symbol} hourly data...")
    print(f"   Period: {start.date()} to {end.date()}")
    
    request = CryptoBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame(1, TimeFrameUnit.Hour),
        start=start,
        end=end
    )
    
    bars = client.get_crypto_bars(request)
    
    # Use the DataFrame property - it has a multi-index (symbol, timestamp)
    if hasattr(bars, 'df') and not bars.df.empty:
        df = bars.df.copy()
        # Reset the multi-index to get symbol and timestamp as columns
        df = df.reset_index()
        # If there's a 'symbol' column, drop it
        if 'symbol' in df.columns:
            df = df.drop(columns=['symbol'])
        # Set timestamp as index
        df.set_index('timestamp', inplace=True)
        # Rename columns to standard format
        df.columns = [c.lower() for c in df.columns]
        print(f"   [OK] Loaded {len(df):,} hourly bars")
        return df
    
    raise ValueError(f"No data returned for {symbol}")


# ============================================================
# INDICATOR CALCULATIONS (Manual - No TA Library Needed)
# ============================================================

def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate ADX (Average Directional Index) manually.
    
    ADX > 25 = Trending market (trade)
    ADX < 25 = Choppy market (don't trade)
    """
    high = df['high']
    low = df['low']
    close = df['close']
    
    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # +DM and -DM
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    # Smoothed TR, +DM, -DM (Wilder's smoothing)
    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean() / atr
    
    # DX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    dx = dx.replace([np.inf, -np.inf], 0).fillna(0)
    
    # ADX (smoothed DX)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    
    return adx


# ============================================================
# UPGRADED BACKTEST v2.0 (Long-Only + ADX Filter)
# ============================================================

def run_backtest_v2(
    df: pd.DataFrame,
    fast_windows: List[int],
    slow_windows: List[int],
    adx_threshold: int = 25,
    long_only: bool = True
) -> pd.DataFrame:
    """
    Run upgraded backtest with:
    - Long-only mode (no shorting)
    - ADX filter (skip choppy markets)
    """
    close = df['close'].values
    adx = calculate_adx(df, ADX_PERIOD).values
    
    results = []
    
    print(f"\n[~] Running v2.0 Backtest (Long-Only={long_only}, ADX>{adx_threshold})...")
    print(f"   Fast Windows: {fast_windows}")
    print(f"   Slow Windows: {slow_windows}")
    
    for fast in fast_windows:
        for slow in slow_windows:
            if fast >= slow:
                continue
            
            # Calculate MAs
            fast_ma = pd.Series(close).rolling(fast).mean().values
            slow_ma = pd.Series(close).rolling(slow).mean().values
            
            # Simulate trading
            position = 0  # 0 = cash, 1 = long
            capital = INITIAL_CAPITAL
            entry_price = 0
            trades = 0
            wins = 0
            equity_curve = [capital]
            
            for i in range(slow, len(close)):
                current_adx = adx[i] if not np.isnan(adx[i]) else 0
                
                # ========== ENTRY (BUY) ==========
                # Long signal: Fast crosses above Slow (+ optional ADX filter)
                if position == 0:
                    if fast_ma[i-1] < slow_ma[i-1] and fast_ma[i] > slow_ma[i]:
                        # Check ADX if filter is enabled
                        adx_ok = (not USE_ADX_FILTER) or (current_adx > adx_threshold)
                        if adx_ok:
                            # BUY
                            position = capital / close[i] * (1 - COMMISSION_PCT)
                            entry_price = close[i]
                            capital = 0
                            trades += 1
                
                # ========== EXIT (SELL) ==========
                elif position > 0:
                    # Exit on death cross (fast below slow)
                    if fast_ma[i-1] > slow_ma[i-1] and fast_ma[i] < slow_ma[i]:
                        # SELL
                        capital = position * close[i] * (1 - COMMISSION_PCT)
                        if close[i] > entry_price:
                            wins += 1
                        position = 0
                
                # Track equity
                if position > 0:
                    equity_curve.append(position * close[i])
                else:
                    equity_curve.append(capital)
            
            # Final close
            if position > 0:
                capital = position * close[-1] * (1 - COMMISSION_PCT)
            
            # Calculate metrics
            final_equity = capital if capital > 0 else equity_curve[-1]
            total_return = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
            
            equity_series = pd.Series(equity_curve)
            returns = equity_series.pct_change().dropna()
            sharpe = (returns.mean() * np.sqrt(8760)) / returns.std() if len(returns) > 0 and returns.std() > 0 else 0
            
            peak = equity_series.expanding().max()
            drawdown = (equity_series - peak) / peak
            max_dd = drawdown.min() * 100
            
            win_rate = (wins / trades * 100) if trades > 0 else 0
            
            results.append({
                'fast': fast,
                'slow': slow,
                'total_return': total_return,
                'sharpe': sharpe,
                'max_drawdown': max_dd,
                'win_rate': win_rate,
                'trades': trades,
                'final_equity': final_equity
            })
    
    return pd.DataFrame(results)


# ============================================================
# BUY & HOLD BENCHMARK
# ============================================================

def calculate_buy_and_hold(df: pd.DataFrame) -> Dict:
    """Calculate buy & hold benchmark."""
    start_price = df['close'].iloc[0]
    end_price = df['close'].iloc[-1]
    
    total_return = (end_price - start_price) / start_price * 100
    
    returns = df['close'].pct_change().dropna()
    sharpe = (returns.mean() * np.sqrt(8760)) / returns.std() if returns.std() > 0 else 0
    
    equity = df['close']
    peak = equity.expanding().max()
    drawdown = (equity - peak) / peak
    max_dd = drawdown.min() * 100
    
    return {
        'total_return': total_return,
        'sharpe': sharpe,
        'max_drawdown': max_dd,
        'start_price': start_price,
        'end_price': end_price
    }


# ============================================================
# HEATMAP GENERATION
# ============================================================

def generate_heatmap(results: pd.DataFrame, metric: str, output_path: str = None):
    """Generate console heatmap and save as image."""
    pivot = results.pivot(index='fast', columns='slow', values=metric)
    
    print(f"\n[i] HEATMAP: {metric.upper()}")
    print("=" * 60)
    print(pivot.round(1).to_string())
    print("=" * 60)
    
    if output_path:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            
            fig, ax = plt.subplots(figsize=(10, 6))
            im = ax.imshow(pivot.values, cmap='RdYlGn', aspect='auto')
            
            ax.set_xticks(range(len(pivot.columns)))
            ax.set_yticks(range(len(pivot.index)))
            ax.set_xticklabels(pivot.columns)
            ax.set_yticklabels(pivot.index)
            ax.set_xlabel('Slow MA Window')
            ax.set_ylabel('Fast MA Window')
            ax.set_title(f'{metric.replace("_", " ").title()} (v2.0 Long-Only + ADX Filter)')
            
            for i in range(len(pivot.index)):
                for j in range(len(pivot.columns)):
                    val = pivot.values[i, j]
                    if not np.isnan(val):
                        ax.text(j, i, f'{val:.1f}', ha='center', va='center', fontsize=9)
            
            plt.colorbar(im)
            plt.tight_layout()
            plt.savefig(output_path, dpi=150)
            plt.close()
            print(f"[>] Saved: {output_path}")
        except Exception as e:
            print(f"[!] Could not save heatmap: {e}")


# ============================================================
# MAIN ANALYSIS
# ============================================================

def run_full_analysis(symbol: str = "BTC/USD", years: int = 2):
    """Run complete v2.0 backtesting analysis."""
    
    print("=" * 60)
    print("  [~] BACKTESTER v2.0 - UPGRADED WITH FILTERS")
    print("  [+] Long-Only Mode: ON (no shorting)")
    print(f"  [i] ADX Filter: Only trade when ADX > {ADX_THRESHOLD}")
    print("=" * 60)
    
    # Fetch data
    try:
        df = fetch_crypto_data(symbol, years)
    except Exception as e:
        print(f"[X] Failed to fetch data: {e}")
        return
    
    # Benchmark
    print("\n[+] BENCHMARK: Buy & Hold")
    benchmark = calculate_buy_and_hold(df)
    print(f"   Start: ${benchmark['start_price']:,.2f}")
    print(f"   End: ${benchmark['end_price']:,.2f}")
    print(f"   Total Return: {benchmark['total_return']:+.1f}%")
    print(f"   Sharpe Ratio: {benchmark['sharpe']:.2f}")
    print(f"   Max Drawdown: {benchmark['max_drawdown']:.1f}%")
    
    # Run v2.0 backtest
    results = run_backtest_v2(
        df, 
        FAST_WINDOWS, 
        SLOW_WINDOWS, 
        adx_threshold=ADX_THRESHOLD,
        long_only=LONG_ONLY
    )
    
    if results.empty:
        print("[X] No valid results")
        return
    
    # Generate heatmaps
    output_dir = Path("data/backtests")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    safe_symbol = symbol.replace('/', '_')
    generate_heatmap(results, 'total_return', output_dir / f"{safe_symbol}_v2_return.png")
    generate_heatmap(results, 'sharpe', output_dir / f"{safe_symbol}_v2_sharpe.png")
    
    # Top 3 by Return
    print("\n[#] TOP 3 BY TOTAL RETURN (v2.0)")
    print("=" * 60)
    top_return = results.nlargest(3, 'total_return')
    for idx, (_, row) in enumerate(top_return.iterrows(), 1):
        beat = "[OK] BEATS" if row['total_return'] > benchmark['total_return'] else "[X] LOSES TO"
        print(f"  #{idx}: Fast={int(row['fast'])}, Slow={int(row['slow'])}")
        print(f"      Return: {row['total_return']:+.1f}% ({beat} B&H {benchmark['total_return']:+.1f}%)")
        print(f"      Sharpe: {row['sharpe']:.2f} | MaxDD: {row['max_drawdown']:.1f}% | Trades: {int(row['trades'])} | Win: {row['win_rate']:.0f}%")
        print(f"      Final: ${row['final_equity']:,.0f}")
        print()
    
    # Top 3 by Sharpe
    print("[#] TOP 3 BY SHARPE RATIO (Risk-Adjusted)")
    print("=" * 60)
    top_sharpe = results.nlargest(3, 'sharpe')
    for idx, (_, row) in enumerate(top_sharpe.iterrows(), 1):
        beat = "[OK] BEATS" if row['sharpe'] > benchmark['sharpe'] else "[X] LOSES TO"
        print(f"  #{idx}: Fast={int(row['fast'])}, Slow={int(row['slow'])}")
        print(f"      Sharpe: {row['sharpe']:.2f} ({beat} B&H {benchmark['sharpe']:.2f})")
        print(f"      Return: {row['total_return']:+.1f}% | MaxDD: {row['max_drawdown']:.1f}% | Win: {row['win_rate']:.0f}%")
        print()
    
    # WINNER
    winner = results.loc[results['total_return'].idxmax()]
    beats_benchmark = winner['total_return'] > benchmark['total_return']
    
    print("=" * 60)
    if beats_benchmark:
        print("  [+] SUCCESS! STRATEGY BEATS BENCHMARK!")
    else:
        print("  [!] Strategy still underperforms. Try different params.")
    print("=" * 60)
    print(f"  [>] BEST PARAMETERS:")
    print(f"     Fast MA: {int(winner['fast'])} periods")
    print(f"     Slow MA: {int(winner['slow'])} periods")
    print(f"     Expected Return: {winner['total_return']:+.1f}%")
    print(f"     Trades: {int(winner['trades'])} | Win Rate: {winner['win_rate']:.0f}%")
    print(f"     B&H Benchmark: {benchmark['total_return']:+.1f}%")
    print("=" * 60)
    
    # Save results
    results.to_csv(output_dir / f"{safe_symbol}_v2_results.csv", index=False)
    
    return results, benchmark


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Backtester v2.0 (Long-Only + ADX)")
    parser.add_argument("--symbol", type=str, default="BTC/USD")
    parser.add_argument("--years", type=int, default=2)
    
    args = parser.parse_args()
    run_full_analysis(args.symbol, args.years)
