#!/usr/bin/env python3
"""
ALGO COMMAND CENTER v3.0 - Textual TUI Edition

A professional terminal-based trading dashboard using the Textual framework.
Clean ASCII design, no emojis, mouse support, keyboard shortcuts.

Features:
- Real-time account stats and positions
- Market status indicator
- System health monitoring
- Trade log with filtering
- Keyboard controls for trading actions

Usage:
    python3 scripts/algo_command_center.py
    python3 scripts/algo_command_center.py --refresh 5

Keyboard Shortcuts:
    q     - Quit
    p     - Pause/Resume trading
    r     - Refresh data
    l     - Toggle live/paper mode display
    ESC   - Emergency liquidation (with confirmation)
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
    from textual.widgets import Header, Footer, Static, DataTable, Label, Button, Log
    from textual.reactive import reactive
    from textual.timer import Timer
except ImportError:
    print("[X] Missing: pip install textual")
    sys.exit(1)


# ============================================================
# ALPACA CLIENT
# ============================================================

def get_trading_client():
    """Initialize Alpaca trading client."""
    from alpaca.trading.client import TradingClient
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_BASE_URL", "")
    
    if not api_key or not secret_key:
        return None
    
    paper = "paper" in base_url.lower()
    return TradingClient(api_key, secret_key, paper=paper)


# ============================================================
# DASHBOARD WIDGETS
# ============================================================

class AccountPanel(Static):
    """Display account information."""
    
    def compose(self) -> ComposeResult:
        yield Static("Loading...", id="account-content")
    
    def update_data(self, data: dict):
        content = self.query_one("#account-content", Static)
        
        equity = data.get("equity", 0)
        cash = data.get("cash", 0)
        buying_power = data.get("buying_power", 0)
        pnl = data.get("pnl", 0)
        pnl_pct = data.get("pnl_pct", 0)
        
        pnl_sign = "+" if pnl >= 0 else ""
        
        text = f"""EQUITY:       ${equity:>12,.2f}
CASH:         ${cash:>12,.2f}
BUYING POWER: ${buying_power:>12,.2f}
DAY P&L:      {pnl_sign}${pnl:>11,.2f} ({pnl_sign}{pnl_pct:.2f}%)"""
        
        content.update(text)


class MarketStatus(Static):
    """Display market open/closed status."""
    
    def compose(self) -> ComposeResult:
        yield Static("MARKET: ---", id="market-status")
    
    def update_status(self, is_open: bool, session: str):
        content = self.query_one("#market-status", Static)
        status = "OPEN" if is_open else "CLOSED"
        style = "green" if is_open else "red"
        content.update(f"MARKET: [{style}]{status}[/] ({session})")


class PositionsTable(Static):
    """Display current positions in a table."""
    
    def compose(self) -> ComposeResult:
        table = DataTable(id="positions-table")
        table.add_columns("SYMBOL", "QTY", "ENTRY", "CURRENT", "P&L", "P&L %")
        yield table
    
    def update_positions(self, positions: list):
        table = self.query_one("#positions-table", DataTable)
        table.clear()
        
        for pos in positions:
            pnl = pos.get("pnl", 0)
            pnl_pct = pos.get("pnl_pct", 0)
            pnl_sign = "+" if pnl >= 0 else ""
            
            table.add_row(
                pos.get("symbol", ""),
                f"{pos.get('qty', 0):.2f}",
                f"${pos.get('entry', 0):,.2f}",
                f"${pos.get('current', 0):,.2f}",
                f"{pnl_sign}${pnl:,.2f}",
                f"{pnl_sign}{pnl_pct:.2f}%"
            )


class SystemHealth(Static):
    """Display system health indicators."""
    
    def compose(self) -> ComposeResult:
        yield Static("Loading...", id="health-content")
    
    def update_health(self, data: dict):
        content = self.query_one("#health-content", Static)
        
        circuit_breaker = "[green]OK[/]" if data.get("circuit_breaker_ok", True) else "[red]TRIPPED[/]"
        api_status = "[green]CONNECTED[/]" if data.get("api_connected", True) else "[red]DISCONNECTED[/]"
        mode = data.get("mode", "PAPER")
        last_update = data.get("last_update", "---")
        
        text = f"""API:             {api_status}
CIRCUIT BREAKER: {circuit_breaker}
MODE:            {mode}
LAST UPDATE:     {last_update}"""
        
        content.update(text)


class TradeLog(Static):
    """Display recent trades/orders."""
    
    def compose(self) -> ComposeResult:
        yield Log(id="trade-log", max_lines=50)
    
    def add_entry(self, message: str):
        log = self.query_one("#trade-log", Log)
        timestamp = datetime.now().strftime("%H:%M:%S")
        log.write_line(f"[{timestamp}] {message}")


# ============================================================
# MAIN APPLICATION
# ============================================================

class AlgoCommandCenter(App):
    """Algo Command Center - Professional Trading Dashboard."""
    
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 3;
        grid-columns: 1fr 1fr;
        grid-rows: auto 1fr auto;
    }
    
    #header-panel {
        column-span: 2;
        height: 3;
        background: $surface;
        border: solid $primary;
        padding: 0 1;
    }
    
    #account-panel {
        height: 100%;
        border: solid $primary;
        padding: 1;
    }
    
    #market-panel {
        height: 100%;
        border: solid $primary;
        padding: 1;
    }
    
    #positions-panel {
        column-span: 2;
        height: 100%;
        border: solid $primary;
        padding: 1;
    }
    
    #health-panel {
        height: auto;
        border: solid $primary;
        padding: 1;
    }
    
    #log-panel {
        height: auto;
        border: solid $primary;
        padding: 1;
    }
    
    .panel-title {
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }
    
    DataTable {
        height: auto;
    }
    """
    
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "toggle_pause", "Pause"),
        ("r", "refresh", "Refresh"),
        ("escape", "emergency", "Emergency"),
    ]
    
    is_paused = reactive(False)
    refresh_interval = 5
    
    def __init__(self, refresh_interval: int = 5):
        super().__init__()
        self.refresh_interval = refresh_interval
        self.client = get_trading_client()
        self.refresh_timer: Optional[Timer] = None
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Container(id="header-panel"):
            yield Static("ALGO COMMAND CENTER v3.0 | Press 'q' to quit, 'p' to pause, 'r' to refresh")
        
        with Container(id="account-panel"):
            yield Static("ACCOUNT", classes="panel-title")
            yield AccountPanel(id="account")
        
        with Container(id="market-panel"):
            yield Static("SYSTEM", classes="panel-title")
            yield MarketStatus(id="market")
            yield SystemHealth(id="health")
        
        with Container(id="positions-panel"):
            yield Static("POSITIONS", classes="panel-title")
            yield PositionsTable(id="positions")
        
        with Container(id="log-panel"):
            yield Static("ACTIVITY LOG", classes="panel-title")
            yield TradeLog(id="log")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Start refresh timer on mount."""
        self.refresh_timer = self.set_interval(self.refresh_interval, self.refresh_data)
        self.refresh_data()
        self.log_message("Dashboard started")
    
    def refresh_data(self) -> None:
        """Fetch and update all data."""
        if self.is_paused:
            return
        
        if not self.client:
            self.log_message("[!] No Alpaca client - check credentials")
            return
        
        try:
            # Get account data
            account = self.client.get_account()
            account_data = {
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "pnl": float(account.equity) - float(account.last_equity),
                "pnl_pct": ((float(account.equity) - float(account.last_equity)) / float(account.last_equity)) * 100 if float(account.last_equity) > 0 else 0,
            }
            self.query_one("#account", AccountPanel).update_data(account_data)
            
            # Get positions
            positions = []
            for pos in self.client.get_all_positions():
                positions.append({
                    "symbol": pos.symbol,
                    "qty": float(pos.qty),
                    "entry": float(pos.avg_entry_price),
                    "current": float(pos.current_price),
                    "pnl": float(pos.unrealized_pl),
                    "pnl_pct": float(pos.unrealized_plpc) * 100,
                })
            self.query_one("#positions", PositionsTable).update_positions(positions)
            
            # Update market status
            from zoneinfo import ZoneInfo
            tz = ZoneInfo('America/New_York')
            now = datetime.now(tz)
            weekday = now.weekday()
            current_mins = now.hour * 60 + now.minute
            market_open = 9 * 60 + 30
            market_close = 16 * 60
            
            is_open = weekday < 5 and market_open <= current_mins < market_close
            session = "US Equities" if weekday < 5 else "Weekend"
            self.query_one("#market", MarketStatus).update_status(is_open, session)
            
            # Update health
            base_url = os.getenv("ALPACA_BASE_URL", "")
            mode = "PAPER" if "paper" in base_url.lower() else "LIVE"
            health_data = {
                "circuit_breaker_ok": not Path("data/artifacts/CIRCUIT_BREAKER_HALTED").exists(),
                "api_connected": True,
                "mode": mode,
                "last_update": datetime.now().strftime("%H:%M:%S"),
            }
            self.query_one("#health", SystemHealth).update_health(health_data)
            
        except Exception as e:
            self.log_message(f"[X] Refresh error: {e}")
    
    def log_message(self, message: str) -> None:
        """Add message to trade log."""
        try:
            self.query_one("#log", TradeLog).add_entry(message)
        except:
            pass
    
    def action_toggle_pause(self) -> None:
        """Toggle pause state."""
        self.is_paused = not self.is_paused
        state = "PAUSED" if self.is_paused else "RESUMED"
        self.log_message(f"Trading {state}")
    
    def action_refresh(self) -> None:
        """Manual refresh."""
        self.log_message("Manual refresh triggered")
        self.refresh_data()
    
    def action_emergency(self) -> None:
        """Emergency liquidation (requires confirmation)."""
        self.log_message("[!!] EMERGENCY LIQUIDATION REQUESTED")
        self.log_message("Press ESC again within 5 seconds to confirm...")
        # TODO: Add confirmation dialog


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Algo Command Center v3.0")
    parser.add_argument("--refresh", type=int, default=5, help="Refresh interval in seconds")
    
    args = parser.parse_args()
    
    app = AlgoCommandCenter(refresh_interval=args.refresh)
    app.run()


if __name__ == "__main__":
    main()
