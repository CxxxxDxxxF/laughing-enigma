#!/usr/bin/env python3
"""
Dashboard CLI for Antigravity Trading System.

Provides a read-only view into the system state, metrics, and history
derived from on-disk artifacts.

Usage:
    python scripts/dashboard.py --portfolio <id> <command>

Commands:
    status      Show system health, halt status, and mode.
    metrics     Show current equity, PnL, and drawdown.
    positions   Show current open positions.
    history     Show recent trade history.
    manage_cash Set or add to cash balance.
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.core.artifacts import LocalArtifactStore
from src.lifecycle.state_store import LocalPortfolioStateStore
from src.lifecycle.runner import HaltFlagStore
from src.core.market_hours import get_session, is_market_open, time_until_open, time_until_close, CME_FUTURES, US_EQUITIES, ALWAYS_OPEN

def get_latest_state(portfolio_id: str, artifact_store: LocalArtifactStore) -> Optional[Any]:
    """Load the latest portfolio state."""
    state_store = LocalPortfolioStateStore(artifact_store)
    return state_store.load_latest_state(portfolio_id)

def cmd_status(args, artifact_store: LocalArtifactStore):
    """Implement status command."""
    print(f"--- Portfolio Status: {args.portfolio} ---")
    
    # Check Halt Status
    halt_store = HaltFlagStore(artifact_store)
    is_halted = halt_store.halt_flag_exists(args.portfolio)
    
    if is_halted:
        print("\n[!] SYSTEM HALTED")
        # Try to read halt details
        try:
            flag_path = Path(artifact_store.base_path) / "portfolio" / args.portfolio / "HALTED"
            if flag_path.exists():
                data = json.loads(flag_path.read_bytes())
                print(f"Reason: {data.get('reason', 'Unknown')}")
                print(f"Halted At: {data.get('halted_at', 'Unknown')}")
                if data.get('violations_summary'):
                    print("Violations:")
                    for v in data['violations_summary']:
                        print(f"  - {v.get('message', 'Unknown violation')}")
        except Exception as e:
            print(f"Error reading halt details: {e}")
    else:
        print("\n[ok] System Running (No Halt Flag)")
    
    # Check Latest State Time
    state = get_latest_state(args.portfolio, artifact_store)
    if state:
        print(f"\nLatest State Timestamp: {state.timestamp}")
        print(f"Total Capital: ${state.total_capital:,.2f}")
    else:
        print("\nNo state found.")

def cmd_market(args, artifact_store: LocalArtifactStore):
    """Show current market hours status for all sessions."""
    print("--- Market Hours Status ---")
    now = datetime.now()
    print(f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
    
    sessions = [
        ("CME Futures", CME_FUTURES),
        ("US Equities", US_EQUITIES),
        ("Always Open", ALWAYS_OPEN),
    ]
    
    for name, session in sessions:
        is_open = is_market_open(now, session)
        status = "[OK] OPEN" if is_open else "[X] CLOSED"
        
        if is_open:
            remaining = time_until_close(now, session)
            remaining_str = f"Closes in {remaining.total_seconds()/3600:.1f}h" if remaining else "N/A"
        else:
            until_open = time_until_open(now, session)
            remaining_str = f"Opens in {until_open.total_seconds()/3600:.1f}h" if until_open else "N/A"
        
        print(f"  {name:15} {status:12} ({remaining_str})")
    
    print("\nUse --session flag with run_live.py to select trading hours.")

def cmd_metrics(args, artifact_store: LocalArtifactStore):
    """Implement metrics command."""
    print(f"--- Portfolio Metrics: {args.portfolio} ---")
    
    state = get_latest_state(args.portfolio, artifact_store)
    if not state:
        print("No state found.")
        return

    print(f"Timestamp: {state.timestamp}")
    print(f"Equity: ${state.total_capital:,.2f}")
    if hasattr(state, 'cash_balance'):
        print(f"Cash Balance: ${state.cash_balance:,.2f}")
    
    if state.drawdown_tracker:
        dt = state.drawdown_tracker
        # Assuming snapshots are available
        if dt.snapshots:
            last = dt.snapshots[-1]
            print(f"Daily PnL: ${dt.get_daily_loss(last.equity):,.2f}")
            # Note: get_daily_pnl might need exact logic, but let's just print what we have
            print(f"Realized PnL: ${last.realized_pnl:,.2f}")
            print(f"Unrealized PnL: ${last.unrealized_pnl:,.2f}")
        
        print(f"High Water Mark: ${dt.high_water_mark:,.2f}")
        current_dd_pct = 0.0
        if dt.high_water_mark > 0:
            current_dd_pct = (dt.high_water_mark - state.total_capital) / dt.high_water_mark * 100.0
        print(f"Drawdown: {current_dd_pct:.2f}%")
        print(f"Tracker Locked: {dt.is_locked}")
    else:
        print("No Drawdown Tracker available.")

def cmd_positions(args, artifact_store: LocalArtifactStore):
    """Implement positions command."""
    print(f"--- Open Positions: {args.portfolio} ---")
    
    state = get_latest_state(args.portfolio, artifact_store)
    if not state:
        print("No state found.")
        return
        
    if not state.positions_by_instrument:
        print("No positions.")
        return
        
    print(f"{'Instrument':<10} {'Qty':<10} {'Cost Basis':<15} {'Value (Est)':<15}")
    print("-" * 50)
    
    for inst, data in state.positions_by_instrument.items():
        if hasattr(data, 'quantity'):
            # It's a Position object
            qty = data.quantity
            cost = data.cost_basis
        else:
            # It's a dict (fallback or legacy)
            qty = data.get('quantity', 0.0)
            cost = data.get('cost_basis', 0.0)
            
        # We don't have current price here unless we fetch it. 
        # For now, just show Cost Value.
        print(f"{inst:<10} {qty:<10.2f} ${cost:<14.2f} {'N/A':<15}")

def cmd_history(args, artifact_store: LocalArtifactStore):
    """Implement history command."""
    print(f"--- Trade History: {args.portfolio} ---")
    print("(Not fully implemented - listing recent states as proxy for activity)")
    
    state_store = LocalPortfolioStateStore(artifact_store)
    states = state_store.list_states(args.portfolio)
    
    if not states:
        print("No history found.")
        return
        
    print(f"Found {len(states)} states.")
    print("Most recent 5 states:")
    for sid in states[:5]:
        print(f"  - {sid}")
        
    # TODO: To really show trade history, we'd need to index `runs/{id}/rebalance_execution.json`
    # or iterate through past states to diff positions.
    # For MVP, listing states proves connectivity.

def cmd_sync(args, artifact_store: LocalArtifactStore):
    """Sync with Alpaca broker and display live account data."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    print(f"--- Broker Sync: {args.portfolio} ---")
    
    # Load environment variables
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_BASE_URL")
    
    if not all([api_key, secret_key, base_url]):
        print("[X] Missing Alpaca credentials in environment variables")
        return
    
    try:
        from src.core.config import AlpacaConfig
        from src.execution.alpaca_client import AlpacaClient
        
        config = AlpacaConfig(base_url=base_url, api_key=api_key, secret_key=secret_key)
        client = AlpacaClient(config)
        client.connect()
        
        # Fetch account
        account = client.get_account()
        print(f"\\n[i] Account Status: {account.status}")
        print(f"   Paper Account: {'Yes' if account.is_paper else 'No'}")
        print(f"   Equity: ${account.portfolio_value:,.2f}")
        print(f"   Cash: ${account.cash:,.2f}")
        print(f"   Buying Power: ${account.buying_power:,.2f}")
        
        # Fetch positions
        positions = client.get_positions()
        if positions:
            print(f"\\n[+] Open Positions ({len(positions)}):")
            print(f"{'Symbol':<8} {'Qty':<8} {'Side':<6} {'Entry':<12} {'Value':<12} {'P/L':<12}")
            print("-" * 60)
            for pos in positions:
                print(f"{pos.symbol:<8} {pos.qty:<8.0f} {pos.side:<6} "
                      f"${pos.avg_entry_price:<11.2f} ${pos.market_value:<11.2f} "
                      f"${pos.unrealized_pl:>10.2f}")
        else:
            print("\\n[+] No open positions")
        
        # Compare with local state
        state = get_latest_state(args.portfolio, artifact_store)
        if state:
            print(f"\\n📋 Local State Comparison:")
            print(f"   Local Total Capital: ${state.total_capital:,.2f}")
            print(f"   Local Cash Balance: ${state.cash_balance:,.2f}")
            delta = account.portfolio_value - state.total_capital
            if abs(delta) > 1.0:
                print(f"   [!]  Delta: ${delta:+,.2f} (broker vs local)")
            else:
                print(f"   [OK] In sync (delta: ${delta:+.2f})")
        
    except Exception as e:
        print(f"[X] Sync failed: {e}")

def cmd_trades(args, artifact_store: LocalArtifactStore):
    """Show recent trades/orders from Alpaca."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    print(f"--- Recent Trades: {args.portfolio} ---")
    
    # Load environment variables
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_BASE_URL")
    
    if not all([api_key, secret_key, base_url]):
        print("[X] Missing Alpaca credentials in environment variables")
        return
    
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import OrderSide, QueryOrderStatus
        
        client = TradingClient(api_key, secret_key, paper=("paper" in base_url))
        
        # Get orders (default: last 50, all statuses)
        limit = getattr(args, 'limit', 20)
        request = GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            limit=limit
        )
        orders = client.get_orders(filter=request)
        
        if not orders:
            print("\n📋 No recent orders found")
            return
        
        print(f"\n📋 Recent Orders ({len(orders)}):")
        print(f"{'Symbol':<8} {'Side':<6} {'Type':<8} {'Qty':<8} {'Filled':<8} {'Status':<12} {'Time':<20}")
        print("-" * 80)
        
        for order in orders:
            side = "BUY" if order.side == OrderSide.BUY else "SELL"
            qty = float(order.qty) if order.qty else 0
            filled = float(order.filled_qty) if order.filled_qty else 0
            status = order.status.name if hasattr(order.status, 'name') else str(order.status).split('.')[-1]
            created = order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else "N/A"
            order_type = order.order_type.name if hasattr(order.order_type, 'name') else str(order.order_type).split('.')[-1]
            
            # Status emoji
            if status == "FILLED":
                status_display = f"[OK] {status}"
            elif status in ["CANCELED", "EXPIRED", "REJECTED"]:
                status_display = f"[X] {status}"
            elif status in ["NEW", "ACCEPTED", "PENDING_NEW"]:
                status_display = f"⏳ {status}"
            else:
                status_display = f"   {status}"
            
            print(f"{order.symbol:<8} {side:<6} {order_type:<8} {qty:<8.0f} {filled:<8.0f} {status_display:<12} {created}")
        
        # Summary
        def get_status_name(s):
            return s.name if hasattr(s, 'name') else str(s).split('.')[-1]
        filled_orders = [o for o in orders if get_status_name(o.status) == "filled"]
        pending_orders = [o for o in orders if get_status_name(o.status) in ["new", "accepted", "pending_new"]]
        
        print(f"\n[i] Summary:")
        print(f"   Total Orders: {len(orders)}")
        print(f"   Filled: {len(filled_orders)}")
        print(f"   Pending: {len(pending_orders)}")
        
        if filled_orders:
            # Show last few fills with prices
            print(f"\n💰 Recent Fills:")
            for order in filled_orders[:5]:
                side = "BUY" if order.side == OrderSide.BUY else "SELL"
                filled_price = float(order.filled_avg_price) if order.filled_avg_price else 0
                filled_qty = float(order.filled_qty) if order.filled_qty else 0
                value = filled_price * filled_qty
                print(f"   {side} {filled_qty:.0f} {order.symbol} @ ${filled_price:.2f} = ${value:,.2f}")
                
    except Exception as e:
        print(f"[X] Failed to fetch trades: {e}")

def cmd_manage_cash(args, artifact_store: LocalArtifactStore):
    """Implement manage_cash command."""
    print(f"--- Manage Cash: {args.portfolio} ---")
    
    state_store = LocalPortfolioStateStore(artifact_store)
    state = state_store.load_latest_state(args.portfolio)
    
    if not state:
        print("No state found. Cannot manage cash.")
        return
        
    print(f"Current Cash Balance: ${state.cash_balance:,.2f}")
    
    if args.set is not None:
        old_cash = state.cash_balance
        new_cash = float(args.set)
        
        # Calculate delta to adjust total_capital
        delta = new_cash - old_cash
        state.cash_balance = new_cash
        state.total_capital += delta
        state.timestamp = datetime.now()
        
        # Save new state
        new_id = f"manual_cash_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        saved_id = state_store.save_state(args.portfolio, state, state_id=new_id)
        
        print(f"Updated Cash Balance to ${state.cash_balance:,.2f}")
        print(f"Updated Total Capital to ${state.total_capital:,.2f}")
        print(f"Saved new state: {saved_id}")
        
    elif args.add is not None:
        old_cash = state.cash_balance
        add_amount = float(args.add)
        
        state.cash_balance += add_amount
        state.total_capital += add_amount
        state.timestamp = datetime.now()
        
        # Save new state
        new_id = f"manual_cash_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        saved_id = state_store.save_state(args.portfolio, state, state_id=new_id)
        
        print(f"Updated Cash Balance to ${state.cash_balance:,.2f}")
        print(f"Updated Total Capital to ${state.total_capital:,.2f}")
        print(f"Saved new state: {saved_id}")
    else:
        print("No action specified. Use --set or --add.")

def cmd_watch(args, artifact_store: LocalArtifactStore):
    """Real-time monitoring dashboard - refreshes every N seconds."""
    import os
    import time
    from dotenv import load_dotenv
    load_dotenv()
    
    interval = getattr(args, 'interval', 30)
    
    # Load environment variables
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_BASE_URL")
    
    if not all([api_key, secret_key, base_url]):
        print("[X] Missing Alpaca credentials in environment variables")
        return
    
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import OrderSide, QueryOrderStatus
        
        client = TradingClient(api_key, secret_key, paper=("paper" in base_url))
        
        while True:
            # Clear screen
            os.system('clear' if os.name == 'posix' else 'cls')
            
            print("═" * 60)
            print(f"  [*] ANTIGRAVITY TRADING DASHBOARD - {args.portfolio}")
            print(f"  Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("═" * 60)
            
            # Account info
            try:
                account = client.get_account()
                print(f"\n[i] ACCOUNT STATUS: {account.status}")
                print(f"   Equity:       ${float(account.portfolio_value):>12,.2f}")
                print(f"   Cash:         ${float(account.cash):>12,.2f}")
                print(f"   Buying Power: ${float(account.buying_power):>12,.2f}")
                print(f"   Day P/L:      ${float(account.equity) - float(account.last_equity):>+12,.2f}")
            except Exception as e:
                print(f"\n[X] Failed to fetch account: {e}")
            
            # Positions
            try:
                positions = client.get_all_positions()
                if positions:
                    print(f"\n[+] POSITIONS ({len(positions)}):")
                    print(f"   {'Symbol':<8} {'Qty':>8} {'P/L':>12} {'Value':>12}")
                    print("   " + "-" * 44)
                    for pos in positions:
                        print(f"   {pos.symbol:<8} {float(pos.qty):>8.0f} "
                              f"${float(pos.unrealized_pl):>+11,.2f} ${float(pos.market_value):>11,.2f}")
                else:
                    print("\n[+] POSITIONS: None")
            except Exception as e:
                print(f"\n[X] Failed to fetch positions: {e}")
            
            # Recent Orders
            try:
                request = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=5)
                orders = client.get_orders(filter=request)
                if orders:
                    print(f"\n📋 RECENT ORDERS ({len(orders)}):")
                    for order in orders:
                        side = "BUY" if order.side == OrderSide.BUY else "SELL"
                        status = order.status.name if hasattr(order.status, 'name') else str(order.status).split('.')[-1]
                        emoji = "[OK]" if status == "filled" else ("⏳" if status in ["new", "accepted"] else "[X]")
                        print(f"   {emoji} {side} {float(order.qty):.0f} {order.symbol} - {status}")
            except Exception as e:
                print(f"\n[X] Failed to fetch orders: {e}")
            
            # Halt Status
            halt_store = HaltFlagStore(artifact_store)
            is_halted = halt_store.halt_flag_exists(args.portfolio)
            if is_halted:
                print(f"\n[X] SYSTEM HALTED - Run: dashboard.py --portfolio {args.portfolio} clear-halt")
            else:
                print("\n[OK] SYSTEM RUNNING")
            
            print(f"\n[>] Refreshing every {interval}s | Press Ctrl+C to exit")
            
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n\n👋 Dashboard closed.")
                break
                
    except Exception as e:
        print(f"[X] Dashboard failed: {e}")

def cmd_clear_halt(args, artifact_store: LocalArtifactStore):
    """Clear the HALT flag to resume trading."""
    print(f"--- Clear Halt: {args.portfolio} ---")
    
    halt_store = HaltFlagStore(artifact_store)
    
    if not halt_store.halt_flag_exists(args.portfolio):
        print("[OK] No HALT flag found. System is not halted.")
        return
    
    # Show halt details first
    try:
        halt_path = Path(artifact_store.base_path) / "portfolio" / args.portfolio / "HALTED"
        if halt_path.exists():
            with open(halt_path, 'r') as f:
                halt_info = json.load(f)
            print(f"\n[!]  Current Halt Info:")
            print(f"   Reason: {halt_info.get('reason', 'Unknown')}")
            print(f"   Time:   {halt_info.get('halted_at', 'Unknown')}")
    except:
        pass
    
    # Clear the halt
    halt_path = Path(artifact_store.base_path) / "portfolio" / args.portfolio / "HALTED"
    if halt_path.exists():
        halt_path.unlink()
        print("\n[OK] HALT flag cleared. Trading can resume.")

def main():
    parser = argparse.ArgumentParser(description="Antigravity Dashboard")
    parser.add_argument("--portfolio", required=True, help="Portfolio ID")
    parser.add_argument("--artifacts", default="data/artifacts", help="Path to artifacts directory")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    subparsers.add_parser("status", help="System status")
    subparsers.add_parser("metrics", help="Performance metrics")
    subparsers.add_parser("positions", help="Open positions")
    subparsers.add_parser("history", help="Trade history")
    subparsers.add_parser("report", help="Generate evidence report")
    subparsers.add_parser("market", help="Show market hours status")
    subparsers.add_parser("sync", help="Sync with Alpaca broker and show live account data")
    
    trades_parser = subparsers.add_parser("trades", help="Show recent trades/orders from Alpaca")
    trades_parser.add_argument("--limit", type=int, default=20, help="Number of orders to show (default: 20)")
    
    cash_parser = subparsers.add_parser("manage_cash", help="Manage cash balance")
    cash_parser.add_argument("--set", type=float, help="Set absolute cash balance")
    cash_parser.add_argument("--add", type=float, help="Add (or subtract) amount to cash balance")
    
    watch_parser = subparsers.add_parser("watch", help="Real-time monitoring dashboard (refreshes automatically)")
    watch_parser.add_argument("--interval", type=int, default=30, help="Refresh interval in seconds (default: 30)")
    
    subparsers.add_parser("clear-halt", help="Clear HALT flag to resume trading")
    
    args = parser.parse_args()
    
    artifact_store = LocalArtifactStore(Path(args.artifacts))
    
    if args.command == "status":
        cmd_status(args, artifact_store)
    elif args.command == "metrics":
        cmd_metrics(args, artifact_store)
    elif args.command == "positions":
        cmd_positions(args, artifact_store)
    elif args.command == "history":
        cmd_history(args, artifact_store)
    elif args.command == "manage_cash":
        cmd_manage_cash(args, artifact_store)
    elif args.command == "market":
        cmd_market(args, artifact_store)
    elif args.command == "sync":
        cmd_sync(args, artifact_store)
    elif args.command == "trades":
        cmd_trades(args, artifact_store)
    elif args.command == "watch":
        cmd_watch(args, artifact_store)
    elif args.command == "clear-halt":
        cmd_clear_halt(args, artifact_store)
    elif args.command == "report":
        # Generate evidence report using the existing script
        import subprocess, shlex, sys
        cmd = f"python {Path(__file__).parent / 'generate_report.py'} --portfolio {args.portfolio}"
        try:
            result = subprocess.run(shlex.split(cmd), capture_output=True, text=True, check=True)
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error generating report: {e}", file=sys.stderr)
            print(e.stdout)
            print(e.stderr, file=sys.stderr)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
