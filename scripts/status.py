#!/usr/bin/env python3
"""
Quick Status Check - Shows live time, positions, and recent orders.
"""

import os
from datetime import datetime
from pathlib import Path

# Load env manually
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            os.environ[key.strip()] = val.strip()

from zoneinfo import ZoneInfo
from alpaca.trading.client import TradingClient

def main():
    # Get current time
    tz = ZoneInfo('America/New_York')
    now = datetime.now(tz)
    
    print("=" * 60)
    print(f"  LIVE STATUS CHECK - {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 60)
    
    # Market status
    weekday = now.weekday()
    current_mins = now.hour * 60 + now.minute
    market_open = 9 * 60 + 30
    market_close = 16 * 60
    is_open = weekday < 5 and market_open <= current_mins < market_close
    
    print(f"\nMARKET: {'[OPEN]' if is_open else '[CLOSED]'}")
    print(f"  Day: {now.strftime('%A')}")
    print(f"  Time: {now.strftime('%I:%M %p')} ET")
    
    # Connect to Alpaca
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_BASE_URL", "")
    paper = "paper" in base_url.lower()
    
    if not api_key or not secret_key:
        print("\n[X] Missing Alpaca credentials")
        return
    
    client = TradingClient(api_key, secret_key, paper=paper)
    
    # Account info
    account = client.get_account()
    equity = float(account.equity)
    last_equity = float(account.last_equity)
    day_pnl = equity - last_equity
    day_pnl_pct = (day_pnl / last_equity * 100) if last_equity > 0 else 0
    
    print(f"\nACCOUNT ({'PAPER' if paper else 'LIVE'}):")
    print(f"  Equity:       ${equity:,.2f}")
    print(f"  Cash:         ${float(account.cash):,.2f}")
    print(f"  Buying Power: ${float(account.buying_power):,.2f}")
    print(f"  Day P&L:      {'+'if day_pnl>=0 else ''}${day_pnl:,.2f} ({'+'if day_pnl>=0 else ''}{day_pnl_pct:.2f}%)")
    
    # Current positions
    positions = client.get_all_positions()
    print(f"\nPOSITIONS ({len(positions)} total):")
    
    if positions:
        # Check what symbols are held
        symbols_held = [pos.symbol for pos in positions]
        has_spy = 'SPY' in symbols_held
        has_other = any(s != 'SPY' for s in symbols_held)
        
        for pos in positions:
            pnl = float(pos.unrealized_pl)
            pnl_pct = float(pos.unrealized_plpc) * 100
            sign = "+" if pnl >= 0 else ""
            qty = float(pos.qty)
            entry = float(pos.avg_entry_price)
            current = float(pos.current_price)
            mkt_val = float(pos.market_value)
            
            print(f"  {pos.symbol:<10} | Qty: {qty:>8.2f} | Entry: ${entry:>10,.2f} | Now: ${current:>10,.2f} | Value: ${mkt_val:>10,.2f} | P&L: {sign}${pnl:,.2f} ({sign}{pnl_pct:.1f}%)")
        
        print(f"\n  STRATEGY CHECK:")
        if has_spy and not has_other:
            print("  [!] Only holding SPY - strategy may not be diversifying")
        elif not has_spy and has_other:
            print("  [OK] Holding non-SPY assets - strategy is active")
        elif has_spy and has_other:
            print("  [OK] Mixed portfolio (SPY + others) - strategy working")
        else:
            print("  [?] Unknown state")
    else:
        print("  [No positions - all cash]")
    
    # Recent orders (last 10)
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus
    
    request = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=10)
    orders = client.get_orders(filter=request)
    print(f"\nRECENT ORDERS (last {len(orders)}):")
    
    if orders:
        # Count unique symbols
        order_symbols = set(o.symbol for o in orders)
        
        for o in orders:
            status = o.status.name if hasattr(o.status, 'name') else str(o.status).split('.')[-1]
            side = o.side.name if hasattr(o.side, 'name') else str(o.side).split('.')[-1]
            created = o.created_at.astimezone(tz).strftime("%m/%d %H:%M") if o.created_at else "---"
            qty = float(o.qty or 0)
            print(f"  {created}  {side:<4} {qty:>8.2f} {o.symbol:<10}  [{status}]")
        
        print(f"\n  DIVERSIFICATION: Orders for {len(order_symbols)} unique symbols: {', '.join(order_symbols)}")
        if len(order_symbols) == 1 and 'SPY' in order_symbols:
            print("  [!] WARNING: Only trading SPY - check strategy logic")
        elif len(order_symbols) > 1:
            print("  [OK] Trading multiple symbols - strategy is diversifying")
    else:
        print("  [No recent orders]")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
