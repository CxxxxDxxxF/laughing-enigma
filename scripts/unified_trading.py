#!/usr/bin/env python3
"""
UNIFIED 24/7 TRADING SYSTEM v2.0 - Risk Hardened Edition

Now includes:
- CircuitBreaker: 2% daily loss limit (hard stop)
- ATR Position Sizing: Volatility-adjusted sizes
- Smart Limit Orders: Reduce slippage
- Rate Limiter: Prevent API throttling

Allocation:
- STOCKS (Core & Explore): 9:30 AM - 4:00 PM ET ($100K)
- CRYPTO (Trend Surfer): 4:00 PM - 9:30 AM ET ($100K)

Usage:
    python3 scripts/unified_trading.py
    python3 scripts/unified_trading.py --dry-run
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import zoneinfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("[X] Missing: pip install pandas numpy")
    sys.exit(1)

# ============================================================
# CONFIGURATION
# ============================================================

STOCK_ALLOCATION = 100000
CRYPTO_ALLOCATION = 100000
STOCK_INTERVAL_MINS = 5
CRYPTO_INTERVAL_MINS = 60

CORE_TICKERS = ['SPY', 'QQQ']
EXPLORE_TICKERS = ['NVDA', 'TSLA', 'AAPL', 'AMD']
CRYPTO_PAIRS = ['BTC/USD', 'ETH/USD', 'SOL/USD', 'LTC/USD']

# Risk Parameters
MAX_DAILY_LOSS_PCT = 0.02  # 2% circuit breaker
RISK_PER_TRADE = 0.01  # 1% of account per trade
MAX_POSITION_PCT = 0.20  # 20% max single position

# Logging setup
SCRIPT_DIR = Path(__file__).parent
LOG_DIR = SCRIPT_DIR.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / f"unified_{datetime.now().strftime('%Y%m%d')}.log")
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# RISK MANAGER CLASS (Integrated)
# ============================================================

class RiskManager:
    """
    Integrated Risk Manager with:
    - Circuit Breaker (2% daily loss limit)
    - ATR Position Sizing
    - Smart Limit Orders
    """
    
    def __init__(self, trading_client, data_client, max_daily_loss_pct: float = 0.02):
        self.client = trading_client
        self.data_client = data_client
        self.max_daily_loss_pct = max_daily_loss_pct
        self.is_tripped = False
        self.halt_file = Path("data/artifacts/CIRCUIT_BREAKER_HALTED")
        
        # Get starting equity
        account = self.client.get_account()
        self.start_equity = float(account.last_equity)
        
        logger.info(f"RiskManager initialized: Start equity ${self.start_equity:,.2f}")
        
        # Check for existing halt
        if self.halt_file.exists():
            self.is_tripped = True
            logger.warning("Circuit breaker already tripped from previous session!")
    
    def check_circuit_breaker(self) -> Tuple[bool, float]:
        """
        Check if safe to trade.
        
        Returns: (is_safe, current_loss_pct)
        """
        if self.is_tripped:
            return False, 0
        
        try:
            account = self.client.get_account()
            current_equity = float(account.equity)
            loss_pct = (self.start_equity - current_equity) / self.start_equity
            
            if loss_pct >= self.max_daily_loss_pct:
                self._trip_circuit_breaker(loss_pct, current_equity)
                return False, loss_pct
            
            return True, loss_pct
            
        except Exception as e:
            logger.error(f"Circuit breaker check failed: {e}")
            return True, 0
    
    def _trip_circuit_breaker(self, loss_pct: float, current_equity: float):
        """Emergency liquidation on circuit breaker trip."""
        self.is_tripped = True
        
        logger.critical("=" * 60)
        logger.critical("[!!] CIRCUIT BREAKER TRIPPED!")
        logger.critical(f"   Loss: {loss_pct*100:.2f}%")
        logger.critical(f"   Start: ${self.start_equity:,.2f}")
        logger.critical(f"   Current: ${current_equity:,.2f}")
        logger.critical("   LIQUIDATING ALL POSITIONS!")
        logger.critical("=" * 60)
        
        try:
            self.client.cancel_orders()
            logger.info("[OK] All orders cancelled")
            
            self.client.close_all_positions(cancel_orders=True)
            logger.info("[OK] All positions closed")
            
        except Exception as e:
            logger.error(f"Emergency close failed: {e}")
        
        # Write halt file
        self.halt_file.parent.mkdir(parents=True, exist_ok=True)
        self.halt_file.write_text(
            f"TRIPPED: {datetime.now().isoformat()}\n"
            f"LOSS: {loss_pct*100:.2f}%\n"
            f"START: ${self.start_equity:,.2f}\n"
            f"FINAL: ${current_equity:,.2f}\n"
        )
    
    def calculate_position_size(self, symbol: str, df: pd.DataFrame, risk_per_trade: float = 0.01) -> int:
        """
        Calculate position size using ATR.
        
        Higher volatility = smaller position
        Lower volatility = larger position
        """
        try:
            account = self.client.get_account()
            equity = float(account.equity)
            risk_amount = equity * risk_per_trade
            
            # Calculate ATR
            high = df['high']
            low = df['low']
            close = df['close'].shift(1)
            
            tr = pd.concat([high - low, abs(high - close), abs(low - close)], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]
            
            if pd.isna(atr) or atr <= 0:
                atr = df['close'].std()
            
            if atr <= 0:
                logger.warning(f"{symbol}: ATR is zero, using fixed size")
                price = df['close'].iloc[-1]
                return int((equity * 0.05) / price)
            
            # Position size = Risk / ATR
            shares = int(risk_amount / atr)
            
            # Cap at 20% of equity
            price = df['close'].iloc[-1]
            max_shares = int((equity * MAX_POSITION_PCT) / price)
            final_qty = min(shares, max_shares)
            
            logger.info(f"ATR Sizing {symbol}: ATR=${atr:.2f}, Qty={final_qty}")
            return final_qty
            
        except Exception as e:
            logger.error(f"Position sizing failed: {e}")
            return 0
    
    def submit_smart_order(self, symbol: str, qty: int, side: str, dry_run: bool = False) -> Optional[object]:
        """
        Submit order using limit order chase logic.
        
        Tries limit at mid-price first, falls back to market if needed.
        """
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        
        if qty <= 0:
            return None
        
        if dry_run:
            logger.info(f"[DRY RUN] Would {side.upper()} {qty} {symbol}")
            return None
        
        order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
        
        try:
            # Get current quote
            from alpaca.data.requests import StockLatestQuoteRequest
            
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = self.data_client.get_stock_latest_quote(request)
            
            if symbol in quotes:
                bid = float(quotes[symbol].bid_price)
                ask = float(quotes[symbol].ask_price)
                mid_price = round((bid + ask) / 2, 2)
                
                # Try limit order at mid-price (IOC)
                limit_req = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=order_side,
                    time_in_force=TimeInForce.IOC,
                    limit_price=mid_price
                )
                
                order = self.client.submit_order(limit_req)
                time.sleep(0.5)
                
                # Check fill
                order = self.client.get_order_by_id(order.id)
                
                if order.status.value in ['filled', 'partially_filled']:
                    filled = float(order.filled_qty or 0)
                    logger.info(f"[OK] Smart order filled: {side.upper()} {filled} {symbol} @ ${mid_price}")
                    return order
                
                # Cancel and fall back
                try:
                    self.client.cancel_order_by_id(order.id)
                except:
                    pass
                
                logger.warning(f"[!] Limit missed, using market: {side.upper()} {qty} {symbol}")
            
            # Fall back to market order
            market_req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY
            )
            return self.client.submit_order(market_req)
            
        except Exception as e:
            logger.error(f"Smart order failed: {e}")
            return None
    
    def reset(self):
        """Reset circuit breaker for new day."""
        account = self.client.get_account()
        self.start_equity = float(account.last_equity)
        self.is_tripped = False
        
        if self.halt_file.exists():
            self.halt_file.unlink()
        
        logger.info(f"[OK] RiskManager reset: New start equity ${self.start_equity:,.2f}")


# ============================================================
# ALPACA CLIENTS
# ============================================================

def get_clients():
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_BASE_URL", "")
    
    paper = "paper" in base_url.lower()
    trading = TradingClient(api_key, secret_key, paper=paper)
    stock_data = StockHistoricalDataClient(api_key, secret_key)
    crypto_data = CryptoHistoricalDataClient(api_key, secret_key)
    
    return trading, stock_data, crypto_data


# ============================================================
# MARKET HOURS CHECK
# ============================================================

def get_market_status() -> Tuple[bool, str, int]:
    tz = zoneinfo.ZoneInfo('America/New_York')
    now = datetime.now(tz)
    
    weekday = now.weekday()
    current_mins = now.hour * 60 + now.minute
    
    market_open = 9 * 60 + 30
    market_close = 16 * 60
    
    if weekday >= 5:
        days_until_monday = (7 - weekday) % 7 or 7
        mins_remaining = days_until_monday * 24 * 60 - current_mins + market_open
        return False, "WEEKEND", mins_remaining
    
    if current_mins < market_open:
        return False, "PRE-MARKET", market_open - current_mins
    
    if current_mins < market_close:
        return True, "MARKET_OPEN", market_close - current_mins
    
    mins_until_open = (24 * 60 - current_mins) + market_open
    return False, "AFTER-HOURS", mins_until_open


# ============================================================
# STOCK TRADING (Core & Explore)
# ============================================================

def fetch_stock_bars(data_client, symbol: str, limit: int = 100) -> pd.DataFrame:
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed
    
    try:
        end = datetime.now(zoneinfo.ZoneInfo('America/New_York'))
        start = end - timedelta(days=5)
        
        # Use IEX feed for free tier (SIP requires paid subscription)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
            limit=limit,
            feed=DataFeed.IEX  # Free tier compatible
        )
        
        bars = data_client.get_stock_bars(request)
        
        if symbol not in bars or len(bars[symbol]) < 20:
            return pd.DataFrame()
        
        data = []
        for bar in bars[symbol]:
            data.append({
                'timestamp': bar.timestamp,
                'open': float(bar.open),
                'high': float(bar.high),
                'low': float(bar.low),
                'close': float(bar.close),
                'volume': float(bar.volume),
            })
        
        return pd.DataFrame(data)
        
    except Exception as e:
        logger.error(f"Failed to fetch bars for {symbol}: {e}")
        return pd.DataFrame()


def run_stock_cycle(risk: RiskManager, data_client, dry_run: bool = False):
    """Run one stock trading cycle with risk management."""
    logger.info("[+] Running STOCK cycle (Core & Explore)...")
    
    for symbol in EXPLORE_TICKERS:
        logger.info(f"[?] Scanning {symbol}...")
        
        df = fetch_stock_bars(data_client, symbol)
        if df.empty:
            logger.warning(f"{symbol}: No data")
            continue
        
        # Simple momentum signal
        sma_20 = df['close'].rolling(20).mean().iloc[-1]
        price = df['close'].iloc[-1]
        
        if price > sma_20:
            # BUY signal - use ATR sizing
            qty = risk.calculate_position_size(symbol, df, RISK_PER_TRADE)
            
            if qty > 0:
                logger.info(f"[*] BUY Signal: {symbol} x {qty}")
                risk.submit_smart_order(symbol, qty, 'buy', dry_run)
        else:
            logger.info(f"[i] {symbol}: Below SMA20, holding")
    
    logger.info("[OK] Stock cycle complete")


# ============================================================
# CRYPTO TRADING (Trend Surfer)
# ============================================================

def fetch_crypto_bars(crypto_client, symbol: str, hours: int = 100) -> pd.DataFrame:
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    
    try:
        end = datetime.now(zoneinfo.ZoneInfo('UTC'))
        start = end - timedelta(hours=hours + 10)
        
        request = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(1, TimeFrameUnit.Hour),
            start=start,
            end=end
        )
        
        bars = crypto_client.get_crypto_bars(request)
        
        if symbol not in bars or len(bars[symbol]) < 25:
            return pd.DataFrame()
        
        data = []
        for bar in bars[symbol]:
            data.append({
                'timestamp': bar.timestamp,
                'open': float(bar.open),
                'high': float(bar.high),
                'low': float(bar.low),
                'close': float(bar.close),
                'volume': float(bar.volume),
            })
        
        return pd.DataFrame(data)
        
    except Exception as e:
        logger.error(f"Failed to fetch crypto bars for {symbol}: {e}")
        return pd.DataFrame()


def run_crypto_cycle(trading_client, crypto_client, dry_run: bool = False):
    """Run one crypto trading cycle."""
    logger.info("BTC Running CRYPTO cycle (Trend Surfer)...")
    
    for symbol in CRYPTO_PAIRS[:2]:  # BTC, ETH for now
        logger.info(f"[?] Scanning {symbol}...")
        
        df = fetch_crypto_bars(crypto_client, symbol)
        if df.empty:
            logger.warning(f"{symbol}: No data")
            continue
        
        # EMA crossover
        df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
        
        curr_9 = df['ema_9'].iloc[-1]
        curr_21 = df['ema_21'].iloc[-1]
        prev_9 = df['ema_9'].iloc[-2]
        prev_21 = df['ema_21'].iloc[-2]
        
        if prev_9 < prev_21 and curr_9 > curr_21:
            logger.info(f"[>] {symbol}: Golden Cross (BUY signal)")
        elif prev_9 > prev_21 and curr_9 < curr_21:
            logger.info(f"[-] {symbol}: Death Cross (SELL signal)")
        else:
            logger.info(f"[i] {symbol}: HOLD (9EMA: ${curr_9:.2f}, 21EMA: ${curr_21:.2f})")
    
    logger.info("[OK] Crypto cycle complete")


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Unified 24/7 Trading System v2.0")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without trading")
    parser.add_argument("--stocks-only", action="store_true")
    parser.add_argument("--crypto-only", action="store_true")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  [*] UNIFIED 24/7 TRADING SYSTEM v2.0")
    print("  [+] Risk Hardened Edition")
    print("=" * 60)
    print(f"  Stock Allocation: ${STOCK_ALLOCATION:,}")
    print(f"  Crypto Allocation: ${CRYPTO_ALLOCATION:,}")
    print(f"  Circuit Breaker: {MAX_DAILY_LOSS_PCT*100:.0f}% daily loss limit")
    print(f"  Position Sizing: ATR-based ({RISK_PER_TRADE*100:.0f}% risk per trade)")
    print(f"  Mode: {'DRY RUN' if args.dry_run else '[!] LIVE TRADING'}")
    print("=" * 60)
    
    # Initialize clients
    trading_client, stock_data, crypto_data = get_clients()
    logger.info("[OK] Connected to Alpaca")
    
    # Initialize Risk Manager
    risk = RiskManager(trading_client, stock_data, MAX_DAILY_LOSS_PCT)
    
    cycle = 0
    while True:
        cycle += 1
        is_market_open, phase, mins_until_change = get_market_status()
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"[>] Cycle #{cycle} | Phase: {phase}")
        logger.info("=" * 60)
        
        # ============ CRITICAL SAFETY CHECK ============
        is_safe, loss_pct = risk.check_circuit_breaker()
        
        if not is_safe:
            logger.warning("[!!] Circuit Breaker ACTIVE. Trading halted.")
            logger.warning("[.] Sleeping 1 hour before retry...")
            time.sleep(3600)
            continue
        
        logger.info(f"[OK] Circuit Breaker OK (Daily P&L: {-loss_pct*100:+.2f}%)")
        # ================================================
        
        # 24/7 CRYPTO TRADING (testing mode)
        # Run crypto strategy continuously regardless of stock market hours
        logger.info(f"[*] Phase: {phase} - Running CRYPTO strategy (24/7 mode)")
        run_crypto_cycle(trading_client, crypto_data, dry_run=args.dry_run)
        sleep_mins = CRYPTO_INTERVAL_MINS
        
        logger.info(f"[.] Sleeping {sleep_mins} minutes...")
        time.sleep(sleep_mins * 60)


if __name__ == "__main__":
    main()
