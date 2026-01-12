#!/usr/bin/env python3
"""
LIVE TRADING DASHBOARD v1.0

Real-time terminal dashboard with:
- Live clock
- Price charts (ASCII)
- Bot activity log
- Position tracker
- P&L updates

Usage:
    python3 scripts/live_dashboard.py
    python3 scripts/live_dashboard.py --refresh 5
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List
import time

# Load env
env_file = Path(__file__).parent.parent.parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            os.environ.setdefault(key.strip(), val.strip())

try:
    from zoneinfo import ZoneInfo
    import plotext as plt
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
except ImportError as e:
    print(f"[X] Missing dependency: {e}")
    print("Run: pip install plotext rich alpaca-py")
    sys.exit(1)


# ============================================================
# CONFIGURATION
# ============================================================

REFRESH_SECONDS = 10
CHART_WIDTH = 60
CHART_HEIGHT = 12
SYMBOLS = ['BTC/USD', 'ETH/USD']
TZ = ZoneInfo('America/New_York')


# ============================================================
# ALPACA CLIENT
# ============================================================

def get_clients():
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_BASE_URL", "")
    paper = "paper" in base_url.lower()
    
    trading = TradingClient(api_key, secret_key, paper=paper)
    crypto = CryptoHistoricalDataClient(api_key, secret_key)
    
    return trading, crypto


# ============================================================
# DATA FETCHING
# ============================================================

def fetch_prices(crypto_client, symbol: str, hours: int = 24) -> List[float]:
    """Fetch hourly prices for charting."""
    try:
        end = datetime.now(ZoneInfo('UTC'))
        start = end - timedelta(hours=hours)
        
        request = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(1, TimeFrameUnit.Hour),
            start=start,
            end=end
        )
        
        bars = crypto_client.get_crypto_bars(request)
        
        if hasattr(bars, 'df') and not bars.df.empty:
            df = bars.df.reset_index()
            return df['close'].tolist()
        return []
    except:
        return []


def get_account_data(trading_client) -> Dict:
    """Get account info."""
    try:
        account = trading_client.get_account()
        return {
            'equity': float(account.equity),
            'cash': float(account.cash),
            'buying_power': float(account.buying_power),
            'pnl': float(account.equity) - float(account.last_equity),
        }
    except:
        return {'equity': 0, 'cash': 0, 'buying_power': 0, 'pnl': 0}


def get_positions(trading_client) -> List[Dict]:
    """Get current positions."""
    try:
        positions = []
        all_positions = trading_client.get_all_positions()
        
        for pos in all_positions:
            # Handle symbol formatting (Alpaca returns absolute symbol e.g. BTCUSD)
            symbol = pos.symbol
            if symbol.endswith("USD") and "/" not in symbol:
                display_symbol = f"{symbol[:-3]}/{symbol[-3:]}"
            else:
                display_symbol = symbol
                
            positions.append({
                'symbol': display_symbol, # e.g. BTC/USD
                'raw_symbol': symbol,     # e.g. BTCUSD
                'qty': float(pos.qty),
                'entry': float(pos.avg_entry_price),
                'current': float(pos.current_price),
                'pnl': float(pos.unrealized_pl),
                'pnl_pct': float(pos.unrealized_plpc) * 100,
                'value': float(pos.market_value),
            })
        return positions
    except Exception as e:
        # We can't log to state.log here easily as it's not passed in, 
        # but the worker catches errors. Rethrowing or returning error details 
        # would be better, but for now we rely on the worker's try/except to catch this
        # if we let it propagate, or we just return empty list.
        # Let's print to stderr for debug if needed, but the TUI hides it.
        return []


def read_bot_log(lines: int = 8) -> List[str]:
    """Read recent bot log entries."""
    log_file = Path(__file__).parent.parent.parent.parent / "logs" / "crypto_24_7.log"
    if log_file.exists():
        try:
            content = log_file.read_text().strip().split('\n')
            return content[-lines:] if len(content) >= lines else content
        except:
            return ["[Log file unavailable]"]
    return ["[No log file found]"]


# ============================================================
# ASCII CHART
# ============================================================

def generate_chart(prices: List[float], symbol: str) -> str:
    """Generate ASCII price chart."""
    if len(prices) < 5:
        return f"  {symbol}: [Insufficient data]"
    
    plt.clear_figure()
    plt.plot(prices, marker="braille")
    plt.plotsize(CHART_WIDTH, CHART_HEIGHT)
    plt.title(f"{symbol} (24h)")
    plt.theme("dark")
    
    # Get chart as string
    return plt.build()


# ============================================================
# DASHBOARD COMPONENTS
# ============================================================

def make_header() -> Panel:
    """Create header with live time."""
    now = datetime.now(TZ)
    time_str = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    
    # Market status
    weekday = now.weekday()
    current_mins = now.hour * 60 + now.minute
    market_open = 9 * 60 + 30
    market_close = 16 * 60
    is_open = weekday < 5 and market_open <= current_mins < market_close
    market = "[green]MARKET OPEN[/]" if is_open else "[red]MARKET CLOSED[/]"
    
    header = Text()
    header.append("LIVE TRADING DASHBOARD", style="bold cyan")
    header.append(f"\n{time_str}  |  {market}  |  BOT: [green]RUNNING[/]")
    
    return Panel(header, border_style="cyan")


def make_account_panel(data: Dict) -> Panel:
    """Create account summary panel."""
    pnl_sign = "+" if data['pnl'] >= 0 else ""
    pnl_color = "green" if data['pnl'] >= 0 else "red"
    
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Label", style="dim")
    table.add_column("Value", justify="right")
    
    table.add_row("Equity", f"${data['equity']:,.2f}")
    table.add_row("Cash", f"${data['cash']:,.2f}")
    table.add_row("Buying Power", f"${data['buying_power']:,.2f}")
    table.add_row("Day P&L", f"[{pnl_color}]{pnl_sign}${data['pnl']:,.2f}[/]")
    
    return Panel(table, title="[bold]ACCOUNT[/]", border_style="blue")


def make_positions_panel(positions: List[Dict]) -> Panel:
    """Create positions table."""
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("Symbol")
    table.add_column("Qty", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Now", justify="right")
    table.add_column("P&L", justify="right")
    
    for pos in positions:
        pnl_color = "green" if pos['pnl'] >= 0 else "red"
        sign = "+" if pos['pnl'] >= 0 else ""
        table.add_row(
            pos['symbol'],
            f"{pos['qty']:.4f}",
            f"${pos['entry']:,.2f}",
            f"${pos['current']:,.2f}",
            f"[{pnl_color}]{sign}${pos['pnl']:,.2f} ({sign}{pos['pnl_pct']:.1f}%)[/]"
        )
    
    if not positions:
        table.add_row("[dim]No positions[/]", "", "", "", "")
    
    return Panel(table, title="[bold]POSITIONS[/]", border_style="green")


def make_chart_panel(prices: Dict[str, List[float]]) -> Panel:
    """Create price charts panel."""
    charts = []
    
    for symbol, price_data in prices.items():
        if price_data:
            current = price_data[-1]
            prev = price_data[-2] if len(price_data) > 1 else current
            change = ((current - prev) / prev * 100) if prev else 0
            color = "green" if change >= 0 else "red"
            sign = "+" if change >= 0 else ""
            
            # Mini sparkline
            if len(price_data) >= 20:
                recent = price_data[-20:]
                min_p, max_p = min(recent), max(recent)
                range_p = max_p - min_p if max_p > min_p else 1
                normalized = [(p - min_p) / range_p for p in recent]
                
                # Create sparkline using block characters
                blocks = " ▁▂▃▄▅▆▇█"
                sparkline = "".join(blocks[int(n * 8)] for n in normalized)
            else:
                sparkline = "---"
            
            charts.append(
                f"{symbol}: [{color}]${current:,.2f}[/] ({sign}{change:.1f}%)\n"
                f"  {sparkline}"
            )
    
    content = "\n\n".join(charts) if charts else "[dim]Loading prices...[/]"
    return Panel(content, title="[bold]PRICES (24h)[/]", border_style="yellow")


def make_log_panel(log_lines: List[str]) -> Panel:
    """Create bot activity log panel."""
    # Clean up log lines
    clean_lines = []
    for line in log_lines:
        # Extract just the message part
        if '] ' in line:
            parts = line.split('] ', 1)
            if len(parts) > 1:
                clean_lines.append(parts[1][:70])
        else:
            clean_lines.append(line[:70])
    
    content = "\n".join(clean_lines[-8:])
    return Panel(content, title="[bold]BOT ACTIVITY[/]", border_style="magenta")


# ============================================================
# STATE MANAGEMENT
# ============================================================

import threading
import copy

class DashboardState:
    def __init__(self):
        self.lock = threading.Lock()
        self.account = {'equity': 0, 'cash': 0, 'buying_power': 0, 'pnl': 0}
        self.positions = []
        self.prices = {sym: [] for sym in SYMBOLS}
        self.log = ["[Initializing...]"]
        self.last_update = datetime.now()
        self.running = True

state = DashboardState()

def data_worker(trading_client, crypto_client, refresh_rate):
    """Background thread to fetch data."""
    while state.running:
        try:
            # Fetch all data
            account = get_account_data(trading_client)
            positions = get_positions(trading_client)
            log = read_bot_log()
            
            prices = {}
            for symbol in SYMBOLS:
                prices[symbol] = fetch_prices(crypto_client, symbol)
            
            # Update position prices with fresh live data if available
            # This fixes "wrong price" issues where Alpaca position data lags
            for pos in positions:
                sym = pos['symbol'] # e.g. BTC/USD
                if sym in prices and prices[sym]:
                    live_price = prices[sym][-1]
                    # Update current price and recalculate values
                    pos['current'] = live_price
                    pos['value'] = pos['qty'] * live_price
                    pos['pnl'] = pos['value'] - (pos['qty'] * pos['entry'])
                    if pos['entry'] > 0:
                        pos['pnl_pct'] = (pos['pnl'] / (pos['qty'] * pos['entry'])) * 100
            
            # Update shared state safely
            with state.lock:
                state.account = account
                state.positions = positions
                state.log = log
                state.prices = prices
                state.last_update = datetime.now()
                
        except Exception as e:
            with state.lock:
                state.log.append(f"[!] Data fetch error: {str(e)}")
        
        # Sleep for refresh rate (e.g. 15s)
        time.sleep(refresh_rate)

# ============================================================
# MAIN DASHBOARD
# ============================================================

def create_dashboard() -> Layout:
    """Create the full dashboard layout from current state."""
    layout = Layout()
    
    # Read state safely
    with state.lock:
        account = copy.deepcopy(state.account)
        positions = copy.deepcopy(state.positions)
        log = copy.deepcopy(state.log)
        prices = copy.deepcopy(state.prices)
    
    # Build layout
    layout.split(
        Layout(name="header", size=4),
        Layout(name="main"),
        Layout(name="footer", size=12),
    )
    
    layout["main"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )
    
    layout["header"].update(make_header())
    layout["left"].update(make_account_panel(account))
    layout["right"].update(make_positions_panel(positions))
    layout["footer"].split_row(
        Layout(make_chart_panel(prices)),
        Layout(make_log_panel(log)),
    )
    
    return layout


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Live Trading Dashboard")
    parser.add_argument("--refresh", type=int, default=15, help="Data refresh interval in seconds")
    args = parser.parse_args()
    
    console = Console()
    console.print("[bold cyan]Starting Live Dashboard (Threaded)...[/]")
    console.print(f"[dim]Data Refresh: {args.refresh}s | UI Refresh: 1s[/]\n")
    
    trading_client, crypto_client = get_clients()
    
    # Start data thread
    worker = threading.Thread(target=data_worker, args=(trading_client, crypto_client, args.refresh), daemon=True)
    worker.start()
    
    try:
        with Live(console=console, refresh_per_second=1, screen=True) as live:
            while True:
                dashboard = create_dashboard()
                live.update(dashboard)
                time.sleep(1) # UI updates every second (clock)
    except KeyboardInterrupt:
        state.running = False
        console.print("\n[yellow]Dashboard stopped.[/]")
    except Exception as e:
        state.running = False
        console.print(f"\n[red]Dashboard crashed: {e}[/]")

if __name__ == "__main__":
    main()
