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
sys.path.insert(0, str(Path(__file__).parent.parent))

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
        status = "✅ OPEN" if is_open else "🔴 CLOSED"
        
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
    
    cash_parser = subparsers.add_parser("manage_cash", help="Manage cash balance")
    cash_parser.add_argument("--set", type=float, help="Set absolute cash balance")
    cash_parser.add_argument("--add", type=float, help="Add (or subtract) amount to cash balance")
    
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
