#!/usr/bin/env python3
"""
Core & Explore Trading Strategy

Allocation:
- CORE (80%): Buy & hold SPY/QQQ for steady growth
- EXPLORE (20%): Intraday scalping on high-volatility stocks

Risk Rules:
- Core never uses margin
- Explore limited to 20% of equity (leveraged to 4x intraday)
- Strict stop-loss: 1% of explore allocation per trade
- All explore positions closed before market close
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import zoneinfo

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

# Allocation split
CORE_ALLOCATION = 0.80  # 80% to safe ETFs
EXPLORE_ALLOCATION = 0.20  # 20% to scalping

# Core portfolio (buy & hold)
CORE_TICKERS = ['SPY', 'QQQ']

# Explore portfolio (intraday scalping)
EXPLORE_TICKERS = ['NVDA', 'TSLA', 'AAPL', 'AMD']

# Risk management
MAX_LOSS_PER_TRADE_PCT = 0.01  # 1% stop loss
MAX_DAILY_LOSS_PCT = 0.02  # 2% max daily loss on explore
PROFIT_TARGET_PCT = 0.005  # 0.5% profit target per trade

# Scalping parameters
MOMENTUM_LOOKBACK_MINUTES = 5
MIN_VOLUME_MULTIPLIER = 1.5  # Volume must be 1.5x average

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


# ============================================================
# ALPACA CLIENT
# ============================================================

def get_alpaca_client():
    """Initialize Alpaca trading client."""
    from alpaca.trading.client import TradingClient
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_BASE_URL", "")
    
    paper = "paper" in base_url.lower()
    return TradingClient(api_key, secret_key, paper=paper)


def get_data_client():
    """Initialize Alpaca data client."""
    from alpaca.data.historical import StockHistoricalDataClient
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    
    return StockHistoricalDataClient(api_key, secret_key)


# ============================================================
# ACCOUNT & POSITION HELPERS
# ============================================================

def get_account_info(client) -> Dict:
    """Get account balances and buying power."""
    account = client.get_account()
    return {
        'equity': float(account.equity),
        'cash': float(account.cash),
        'buying_power': float(account.buying_power),
        'daytrading_buying_power': float(account.daytrading_buying_power),
        'portfolio_value': float(account.portfolio_value),
    }


def get_positions(client) -> Dict[str, Dict]:
    """Get all current positions."""
    positions = {}
    for pos in client.get_all_positions():
        positions[pos.symbol] = {
            'qty': float(pos.qty),
            'market_value': float(pos.market_value),
            'avg_entry': float(pos.avg_entry_price),
            'unrealized_pl': float(pos.unrealized_pl),
            'unrealized_plpc': float(pos.unrealized_plpc),
        }
    return positions


def get_latest_price(data_client, symbol: str) -> float:
    """Get latest trade price for a symbol."""
    from alpaca.data.requests import StockLatestQuoteRequest
    
    request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
    quotes = data_client.get_stock_latest_quote(request)
    if symbol in quotes:
        return float(quotes[symbol].ask_price + quotes[symbol].bid_price) / 2
    return 0.0


# ============================================================
# CORE STRATEGY (80% - Buy & Hold)
# ============================================================

def manage_core_portfolio(client, data_client, account_info: Dict, positions: Dict):
    """
    Manage the CORE allocation (80% of equity in SPY/QQQ).
    
    Strategy: Equal-weight SPY and QQQ. Rebalance weekly if drift > 5%.
    """
    equity = account_info['equity']
    core_target = equity * CORE_ALLOCATION
    target_per_ticker = core_target / len(CORE_TICKERS)
    
    logger.info(f"[i] CORE: Target ${core_target:,.0f} ({CORE_ALLOCATION*100:.0f}% of ${equity:,.0f})")
    
    for ticker in CORE_TICKERS:
        current_value = positions.get(ticker, {}).get('market_value', 0)
        diff = target_per_ticker - current_value
        diff_pct = abs(diff) / target_per_ticker if target_per_ticker > 0 else 0
        
        price = get_latest_price(data_client, ticker)
        if price <= 0:
            logger.warning(f"  {ticker}: Could not get price, skipping")
            continue
        
        # Only rebalance if drift > 5%
        if diff_pct > 0.05:
            shares = int(abs(diff) / price)
            
            if shares > 0:
                if diff > 0:
                    # Need to buy
                    logger.info(f"  [+] {ticker}: Buying {shares} shares (${diff:,.0f} underweight)")
                    submit_order(client, ticker, shares, 'buy')
                else:
                    # Need to sell
                    logger.info(f"  [-] {ticker}: Selling {shares} shares (${abs(diff):,.0f} overweight)")
                    submit_order(client, ticker, shares, 'sell')
        else:
            logger.info(f"  [OK] {ticker}: In balance (${current_value:,.0f} / ${target_per_ticker:,.0f})")


# ============================================================
# EXPLORE STRATEGY (20% - Intraday Scalping)
# ============================================================

def run_explore_scalping(client, data_client, account_info: Dict, positions: Dict):
    """
    Run the EXPLORE scalping strategy (20% of equity, leveraged intraday).
    
    Strategy:
    - Use day trading buying power
    - Look for momentum breakouts on NVDA, TSLA, etc.
    - Strict stop loss (1% of position)
    - Profit target (0.5%)
    - All positions closed before market close
    """
    equity = account_info['equity']
    explore_cash = equity * EXPLORE_ALLOCATION
    daytrading_bp = account_info['daytrading_buying_power']
    
    # Limit to 4x leverage on explore allocation
    max_explore_bp = explore_cash * 4
    available_bp = min(daytrading_bp, max_explore_bp)
    
    logger.info(f"[*] EXPLORE: Cash ${explore_cash:,.0f} → BP ${available_bp:,.0f} (Day Trading)")
    
    # Calculate current explore exposure
    explore_exposure = sum(
        positions.get(t, {}).get('market_value', 0) 
        for t in EXPLORE_TICKERS
    )
    
    if explore_exposure >= explore_cash:
        logger.info(f"  [||]  Already at explore capacity (${explore_exposure:,.0f} / ${explore_cash:,.0f})")
        return
    
    # Check each ticker for momentum
    for ticker in EXPLORE_TICKERS:
        if ticker in positions:
            # Manage existing position
            manage_explore_position(client, data_client, ticker, positions[ticker])
        else:
            # Look for entry
            check_scalp_entry(client, data_client, ticker, available_bp / len(EXPLORE_TICKERS))


def check_scalp_entry(client, data_client, ticker: str, max_position_value: float):
    """
    Check if ticker meets entry criteria for a scalp trade.
    
    Entry Criteria:
    - Price above 5-minute VWAP
    - Volume > 1.5x average
    - Momentum positive (price up in last 5 mins)
    """
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    
    try:
        # Get recent 1-minute bars
        end = datetime.now(zoneinfo.ZoneInfo('America/New_York'))
        start = end - timedelta(minutes=10)
        
        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end
        )
        
        bars = data_client.get_stock_bars(request)
        if ticker not in bars or len(bars[ticker]) < 5:
            return
        
        recent_bars = list(bars[ticker])[-5:]
        
        # Calculate momentum
        start_price = float(recent_bars[0].close)
        end_price = float(recent_bars[-1].close)
        momentum = (end_price - start_price) / start_price
        
        # Calculate average volume
        avg_volume = sum(b.volume for b in recent_bars) / len(recent_bars)
        last_volume = recent_bars[-1].volume
        
        # Entry criteria
        if momentum > 0.001 and last_volume > avg_volume * MIN_VOLUME_MULTIPLIER:
            # Calculate position size
            price = end_price
            shares = int(max_position_value / price)
            
            if shares > 0:
                logger.info(f"  [>] {ticker}: ENTRY - Momentum +{momentum*100:.2f}%, Volume {last_volume/avg_volume:.1f}x")
                submit_order(client, ticker, shares, 'buy')
        else:
            logger.debug(f"  ⏳ {ticker}: No entry (Mom: {momentum*100:.2f}%, Vol: {last_volume/avg_volume:.1f}x)")
            
    except Exception as e:
        logger.warning(f"  {ticker}: Error checking entry - {e}")


def manage_explore_position(client, data_client, ticker: str, position: Dict):
    """
    Manage existing explore position with stop loss and profit target.
    """
    entry = position['avg_entry']
    current_pl_pct = position['unrealized_plpc']
    qty = int(position['qty'])
    
    # Check stop loss
    if current_pl_pct <= -MAX_LOSS_PER_TRADE_PCT:
        logger.warning(f"  [X] {ticker}: STOP LOSS triggered ({current_pl_pct*100:.2f}%)")
        submit_order(client, ticker, qty, 'sell')
        return
    
    # Check profit target
    if current_pl_pct >= PROFIT_TARGET_PCT:
        logger.info(f"  💰 {ticker}: PROFIT TARGET hit ({current_pl_pct*100:.2f}%)")
        submit_order(client, ticker, qty, 'sell')
        return
    
    logger.info(f"  [i] {ticker}: Holding ({current_pl_pct*100:+.2f}%)")


def close_all_explore_positions(client, positions: Dict):
    """Close all explore positions before market close."""
    logger.info("🌅 Closing all EXPLORE positions before market close...")
    
    for ticker in EXPLORE_TICKERS:
        if ticker in positions:
            qty = int(positions[ticker]['qty'])
            if qty > 0:
                logger.info(f"  [>] {ticker}: Closing {qty} shares")
                submit_order(client, ticker, qty, 'sell')


# ============================================================
# ORDER EXECUTION
# ============================================================

def submit_order(client, symbol: str, qty: int, side: str):
    """Submit a market order."""
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    
    try:
        order_side = OrderSide.BUY if side == 'buy' else OrderSide.SELL
        
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY
        )
        
        order = client.submit_order(request)
        logger.info(f"    [OK] Order submitted: {side.upper()} {qty} {symbol}")
        return order
        
    except Exception as e:
        logger.error(f"    [X] Order failed: {e}")
        return None


# ============================================================
# MARKET HOURS
# ============================================================

def is_market_open() -> bool:
    """Check if US market is currently open."""
    tz = zoneinfo.ZoneInfo('America/New_York')
    now = datetime.now(tz)
    
    # Weekday check
    if now.weekday() >= 5:
        return False
    
    # Time check (9:30 AM - 4:00 PM ET)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= now < market_close


def is_near_market_close() -> bool:
    """Check if within 15 minutes of market close."""
    tz = zoneinfo.ZoneInfo('America/New_York')
    now = datetime.now(tz)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return (market_close - now).total_seconds() <= 900  # 15 minutes


# ============================================================
# MAIN LOOP
# ============================================================

def run_cycle(client, data_client):
    """Run one trading cycle."""
    account_info = get_account_info(client)
    positions = get_positions(client)
    
    logger.info("=" * 60)
    logger.info(f"[>] Account: Equity ${account_info['equity']:,.0f}, BP ${account_info['buying_power']:,.0f}")
    logger.info("=" * 60)
    
    # 1. Manage Core Portfolio (weekly rebalance)
    manage_core_portfolio(client, data_client, account_info, positions)
    
    # 2. Run Explore Scalping (during market hours only)
    if is_near_market_close():
        # Close all explore positions 15 mins before close
        close_all_explore_positions(client, positions)
    else:
        run_explore_scalping(client, data_client, account_info, positions)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Core & Explore Trading Strategy")
    parser.add_argument("--interval", type=int, default=5, help="Minutes between cycles (default: 5)")
    parser.add_argument("--max-cycles", type=int, default=0, help="Max cycles (0 = unlimited)")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  [*] CORE & EXPLORE TRADING BOT")
    print("=" * 60)
    print(f"  Core (80%): {', '.join(CORE_TICKERS)}")
    print(f"  Explore (20%): {', '.join(EXPLORE_TICKERS)}")
    print(f"  Stop Loss: {MAX_LOSS_PER_TRADE_PCT*100:.1f}%")
    print(f"  Profit Target: {PROFIT_TARGET_PCT*100:.1f}%")
    print(f"  Interval: {args.interval} minutes")
    print("=" * 60)
    
    client = get_alpaca_client()
    data_client = get_data_client()
    
    cycle = 0
    while True:
        cycle += 1
        
        if not is_market_open():
            logger.info("⏳ Market closed. Waiting for open...")
            time.sleep(60)
            continue
        
        logger.info(f"\n━━━ Cycle #{cycle} [{datetime.now().strftime('%H:%M:%S')}] ━━━")
        
        try:
            run_cycle(client, data_client)
        except Exception as e:
            logger.error(f"Cycle error: {e}")
        
        if args.max_cycles > 0 and cycle >= args.max_cycles:
            logger.info("Max cycles reached. Exiting.")
            break
        
        logger.info(f"[.] Sleeping {args.interval} minutes...")
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
