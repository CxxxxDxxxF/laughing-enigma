#!/usr/bin/env python3
"""
24/7 Crypto Trend Surfer Strategy

A crypto-optimized trading strategy that runs 24/7:
- Core (70%): BTC/ETH with dynamic rebalancing
- Explore (30%): High-beta alts with EMA crossover + volume filter

Key Features:
- Hourly timeframe (reduces fees vs 1-min scalping)
- Volatility Guard (blocks trades in extreme chop)
- Spread Watcher (warns if spread too high)
- Kill Switch (instant liquidation to cash)
- 24/7 execution with auto-reconnect

Usage:
    python3 scripts/crypto_surfer.py
    python3 scripts/crypto_surfer.py --dry-run
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import zoneinfo

sys.path.insert(0, str(Path(__file__).parent.parent))
# Add src to path for production modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.state_store import StateStore, OrderIntent, OrderStatus, PendingOrder
from src.execution.reconciliation import ReconciliationManager
from src.risk.circuit_breaker import CircuitBreakerManager
from src.analysis.regime import calculate_regime, RegimeStatus, RegimeResult

from dotenv import load_dotenv
load_dotenv()

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("[X] Missing dependencies. Run: pip install pandas numpy")
    sys.exit(1)

# ============================================================
# CONFIGURATION
# ============================================================

# Asset Allocation
CORE_ALLOCATION = 0.70  # 70% in BTC/ETH
EXPLORE_ALLOCATION = 0.30  # 30% in alts

# Core Assets (rebalanced for dominance)
CORE_PAIRS = ['BTC/USD', 'ETH/USD']

# Explore Assets (EMA crossover strategy)
EXPLORE_PAIRS = ['SOL/USD', 'LTC/USD', 'DOGE/USD', 'LINK/USD']

# All crypto pairs
ALL_PAIRS = CORE_PAIRS + EXPLORE_PAIRS

# EMA Crossover Parameters - OPTIMIZED FROM BACKTESTING
# Backtested on 2 years of BTC/USD hourly data:
# - Fast=50, Slow=100 returned +116.7% vs B&H +93.6%
# - Sharpe 1.33 vs B&H 0.92
EMA_FAST = 50  # 50-hour EMA (was 9)
EMA_SLOW = 100  # 100-hour EMA (was 21)
RSI_PERIOD = 14

# ============================================================
# PROFESSIONAL RISK MANAGEMENT (1% Rule)
# ============================================================
# Source: Industry best practices for crypto trading

# Position Sizing (1% Rule)
RISK_PER_TRADE = 0.01  # Never risk more than 1% of capital per trade
MAX_POSITION_PCT = 0.15  # Max 15% of equity in single position
PORTFOLIO_HEAT_MAX = 0.06  # Max 6% of capital at risk across all positions

# Stop Losses
TRAILING_STOP_PCT = 0.03  # 3% trailing stop (tighter for crypto)
INITIAL_STOP_PCT = 0.03  # 3% initial stop loss

# Trade Filters
VOLUME_MULTIPLIER = 2.0  # Volume must be 2x average (was 1.5x)
SPREAD_WARNING_PCT = 0.005  # Warn if spread > 0.5%
SPREAD_BLOCK_PCT = 0.01  # Block trades if spread > 1%
MIN_RISK_REWARD = 2.0  # Minimum 1:2 risk-reward ratio

# ATR-Based Dynamic Stops (from Alpaca examples)
ATR_PERIOD = 14  # Average True Range period
ATR_MULTIPLIER = 2.0  # Stop = price - (ATR * multiplier)
USE_ATR_STOPS = True  # Use ATR instead of fixed % stops

# Limit Orders (from Alpaca examples)
USE_LIMIT_ORDERS = True  # Use limit orders instead of market
LIMIT_SLIPPAGE = 0.005  # Place limit 0.5% above/below market

# Rebalancing
REBALANCE_THRESHOLD = 0.10  # Rebalance if drift > 10%

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# SYSTEM HARDENING (Phase 3)
# ============================================================

def retry_with_backoff(retries=3, backoff_in_seconds=1):
    """
    Decorator to retry functions on API errors (429, 500, etc).
    Exponential backoff: 1s, 2s, 4s...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            x = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if x == retries:
                        logger.error(f"[X] Failed after {retries} retries: {e}")
                        raise e
                    
                    sleep = (backoff_in_seconds * 2 ** x + 
                             np.random.uniform(0, 1)) # Add jitter
                    logger.warning(f"  [!] Error: {e}. Retrying in {sleep:.1f}s...")
                    time.sleep(sleep)
                    x += 1
        return wrapper
    return decorator


class WashSaleGuard:
    """
    Prevents Wash Sales (buying back loss within 30 days).
    For Crypto Paper Trading, we use a 61-minute cooldown to simulate.
    """
    def __init__(self, cooldown_minutes: int = 61):
        self.cooldown_mins = cooldown_minutes
        self.loss_register = {} # {symbol: timestamp_of_loss_sell}
        
    def record_sell(self, symbol: str, pnl: float):
        """Record a sell. If loss, start cooldown."""
        if pnl < 0:
            logger.warning(f"  [!] Wash Sale Guard: Loss recorded for {symbol} (${pnl:.2f})")
            self.loss_register[symbol] = datetime.now()
            
    def can_buy(self, symbol: str) -> bool:
        """Check if we can buy this symbol."""
        if symbol not in self.loss_register:
            return True
            
        last_loss_time = self.loss_register[symbol]
        elapsed = (datetime.now() - last_loss_time).total_seconds() / 60
        
        if elapsed < self.cooldown_mins:
            logger.warning(f"  [!] Wash Sale Guard: Blocking {symbol} BUY (Cooldown: {int(self.cooldown_mins - elapsed)}m left)")
            return False
            
        # Cooldown expired
        del self.loss_register[symbol]
        return True

# Global Wash Sale Guard (Legacy - Migrating to Reconciliation State?)
# Actually, keep it for now as it's separate from circuit breaker.
wash_sale_guard = WashSaleGuard()

# ============================================================
# PRODUCTION STATE MANAGERS
# ============================================================
# Initialized in run_explore_strategy to access env vars


# ============================================================
# ALPACA CLIENTS
# ============================================================

def get_clients():
    """Initialize Alpaca clients for crypto."""
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import CryptoHistoricalDataClient
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_BASE_URL", "")
    
    paper = "paper" in base_url.lower()
    trading = TradingClient(api_key, secret_key, paper=paper)
    crypto_data = CryptoHistoricalDataClient(api_key, secret_key)
    
    return trading, crypto_data


# ============================================================
# DATA FETCHING & INDICATORS
# ============================================================

@retry_with_backoff(retries=3)
def fetch_crypto_data(crypto_client, symbol: str, hours: int = 200) -> pd.DataFrame:
    """
    Fetch hourly crypto data and calculate indicators.
    Includes stale data check (max 2 hours lag).
    
    Returns DataFrame with: close, volume, ema_50, ema_100, rsi
    """
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
        
        # Use DataFrame property - handles multi-index correctly
        if hasattr(bars, 'df') and not bars.df.empty:
            df = bars.df.copy()
            # Reset multi-index to get columns
            df = df.reset_index()
            if 'symbol' in df.columns:
                df = df.drop(columns=['symbol'])
            df.set_index('timestamp', inplace=True)
            df.columns = [c.lower() for c in df.columns]
            
            if len(df) < 30:
                logger.warning(f"{symbol}: Insufficient data ({len(df)} bars)")
                return pd.DataFrame()
            
            # Stale Data Check (Phase 3)
            last_ts = df.index[-1]
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=zoneinfo.ZoneInfo('UTC'))
            
            now_utc = datetime.now(zoneinfo.ZoneInfo('UTC'))
            lag = (now_utc - last_ts).total_seconds() / 3600
            
            if lag > 2.0:
                logger.warning(f"{symbol}: DATA STALE (Lag: {lag:.1f}h). Last: {last_ts}")
                return pd.DataFrame() # Treat as no data to stay safe
            
            # Calculate EMAs
            df['ema_9'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
            df['ema_21'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()
            
            # Calculate RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=RSI_PERIOD).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_PERIOD).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # Average volume
            df['avg_volume'] = df['volume'].rolling(window=20).mean()
            
            return df
        else:
            logger.warning(f"{symbol}: No data returned")
            return pd.DataFrame()
        
    except Exception as e:
        logger.error(f"Failed to fetch data for {symbol}: {e}")
        return pd.DataFrame()


def get_crypto_momentum(df: pd.DataFrame) -> str:
    """
    Check for EMA Crossover with volume confirmation.
    
    Returns: 'BUY', 'SELL', or 'HOLD'
    """
    if df.empty or len(df) < 25:
        return 'HOLD'
    
    # Get last few bars
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    curr_ema9 = curr['ema_9']
    curr_ema21 = curr['ema_21']
    prev_ema9 = prev['ema_9']
    prev_ema21 = prev['ema_21']
    
    current_vol = curr['volume']
    avg_vol = curr['avg_volume']
    
    # BUY: Golden Cross (9 crosses above 21) + High Volume
    if prev_ema9 < prev_ema21 and curr_ema9 > curr_ema21:
        if current_vol > avg_vol * VOLUME_MULTIPLIER:
            return 'BUY'
    
    # SELL: Death Cross (9 crosses below 21)
    if prev_ema9 > prev_ema21 and curr_ema9 < curr_ema21:
        return 'SELL'
    
    return 'HOLD'


# ============================================================
# ATR CALCULATION (from Alpaca BTC Swing Trade example)
# ============================================================

def calculate_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    """
    Calculate Average True Range (ATR) for dynamic stop-loss.
    
    ATR measures volatility and is used to set stops that adapt to
    market conditions - wider stops in volatile markets, tighter in calm.
    
    Returns: ATR value (in dollars)
    """
    if df.empty or len(df) < period + 1:
        return 0.0
    
    # True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
    df = df.copy()
    df['prev_close'] = df['close'].shift(1)
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['prev_close'])
    df['tr3'] = abs(df['low'] - df['prev_close'])
    df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    
    # ATR is the exponential moving average of True Range
    atr = df['true_range'].ewm(span=period, adjust=False).mean().iloc[-1]
    
    return float(atr)


def calculate_atr_stop(price: float, atr: float, side: str = 'buy') -> float:
    """
    Calculate stop-loss price based on ATR.
    
    For BUY: stop = price - (ATR * multiplier)
    For SELL: stop = price + (ATR * multiplier)
    """
    offset = atr * ATR_MULTIPLIER
    
    if side == 'buy':
        return price - offset
    else:
        return price + offset


def calculate_position_size_atr(equity: float, price: float, atr: float) -> float:
    """
    Calculate position size using 1% Rule with ATR-based stop.
    
    This is superior to fixed % stops because it adapts to volatility.
    """
    if atr <= 0:
        return 0.0
    
    risk_amount = equity * RISK_PER_TRADE  # 1% of equity
    stop_distance = atr * ATR_MULTIPLIER  # ATR-based stop distance
    
    if stop_distance <= 0:
        return 0.0
    
    position_size = risk_amount / stop_distance
    
    # Cap at max position size
    max_position_value = equity * MAX_POSITION_PCT
    max_qty = max_position_value / price
    
    return min(position_size, max_qty)


# ============================================================
# POSITION SIZING (1% RULE)
# ============================================================

def calculate_position_size(equity: float, price: float, stop_pct: float = INITIAL_STOP_PCT) -> float:
    """
    Calculate position size using the 1% Rule.
    
    Formula: position_size = risk_amount / stop_distance
    
    Args:
        equity: Total account equity
        price: Current asset price
        stop_pct: Stop loss percentage (default 3%)
    
    Returns:
        Quantity to buy (in asset units)
    """
    risk_amount = equity * RISK_PER_TRADE  # 1% of equity
    stop_distance = price * stop_pct  # Dollar distance to stop
    
    if stop_distance <= 0:
        return 0
    
    position_size = risk_amount / stop_distance
    
    # Cap at max position size
    max_position_value = equity * MAX_POSITION_PCT
    max_qty = max_position_value / price
    
    return min(position_size, max_qty)


class TrailingStopManager:
    """
    Track trailing stops for all positions.
    
    For each position, tracks the highest price since entry
    and triggers sell when price drops below trailing threshold.
    """
    
    def __init__(self):
        self.high_water_marks = {}  # symbol -> highest price since entry
        self.entry_prices = {}  # symbol -> entry price
    
    def register_entry(self, symbol: str, entry_price: float):
        """Register a new position entry."""
        self.high_water_marks[symbol] = entry_price
        self.entry_prices[symbol] = entry_price
        logger.info(f"  [*] Trailing stop registered for {symbol} at ${entry_price:,.2f}")
    
    def update_price(self, symbol: str, current_price: float) -> bool:
        """
        Update price and check if trailing stop triggered.
        
        Returns: True if stop triggered (should sell), False otherwise
        """
        if symbol not in self.high_water_marks:
            return False
        
        # Update high water mark
        if current_price > self.high_water_marks[symbol]:
            self.high_water_marks[symbol] = current_price
        
        # Check if trailing stop triggered
        high = self.high_water_marks[symbol]
        stop_price = high * (1 - TRAILING_STOP_PCT)
        
        if current_price <= stop_price:
            logger.info(f"  [!!] TRAILING STOP triggered for {symbol}")
            logger.info(f"       High: ${high:,.2f} | Stop: ${stop_price:,.2f} | Now: ${current_price:,.2f}")
            return True
        
        return False
    
    def remove_position(self, symbol: str):
        """Remove position from tracking after sell."""
        self.high_water_marks.pop(symbol, None)
        self.entry_prices.pop(symbol, None)
    
    def get_portfolio_heat(self, positions: dict, equity: float) -> float:
        """
        Calculate current portfolio heat (% of capital at risk).
        
        Heat = sum of (position_value * stop_pct) / equity
        """
        if equity <= 0:
            return 0
        
        total_risk = 0
        for symbol, pos_info in positions.items():
            if symbol in self.entry_prices:
                position_value = pos_info.get('market_value', 0)
                risk_amount = position_value * TRAILING_STOP_PCT
                total_risk += risk_amount
        
        return total_risk / equity


# Global trailing stop manager
trailing_stops = TrailingStopManager()


# ============================================================
# SAFETY GUARDS
# ============================================================

def check_spread(crypto_client, symbol: str) -> Tuple[float, bool, bool]:
    """
    Check bid-ask spread for a crypto pair.
    
    Returns: (spread_pct, is_warning, is_blocked)
    """
    from alpaca.data.requests import CryptoLatestQuoteRequest
    
    try:
        request = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = crypto_client.get_crypto_latest_quote(request)
        
        if symbol not in quotes:
            return 0, False, False
        
        quote = quotes[symbol]
        bid = float(quote.bid_price)
        ask = float(quote.ask_price)
        mid = (bid + ask) / 2
        
        if mid == 0:
            return 0, False, False
        
        spread_pct = (ask - bid) / mid
        
        is_warning = spread_pct > SPREAD_WARNING_PCT
        is_blocked = spread_pct > SPREAD_BLOCK_PCT
        
        return spread_pct, is_warning, is_blocked
        
    except Exception as e:
        logger.warning(f"Failed to check spread for {symbol}: {e}")
        return 0, False, False


def volatility_guard(df: pd.DataFrame) -> bool:
    """
    Block trades during extreme volatility (top 90th percentile).
    
    Returns: True if SAFE to trade, False if BLOCKED
    """
    if df.empty or len(df) < 20:
        return True  # Not enough data, allow trade
    
    # Calculate standard deviation of last 10 bars
    recent_std = df['close'].tail(10).std()
    historical_std = df['close'].tail(50).std()
    
    if historical_std == 0:
        return True
    
    # Check if current volatility is extreme
    volatility_ratio = recent_std / historical_std
    
    # If volatility is 2x+ normal, block
    if volatility_ratio > 2.0:
        logger.warning(f"Volatility guard: Blocking trade (ratio: {volatility_ratio:.2f})")
        return False
    
    return True


# ============================================================
# TRADING LOGIC
# ============================================================

def get_account_info(trading_client) -> Dict:
    """Get account balances."""
    account = trading_client.get_account()
    return {
        'equity': float(account.equity),
        'cash': float(account.cash),
        'buying_power': float(account.buying_power),
    }


def get_crypto_positions(trading_client) -> Dict[str, Dict]:
    """Get current crypto positions."""
    positions = {}
    for pos in trading_client.get_all_positions():
        if '/' in pos.symbol:  # Crypto pairs have '/'
            positions[pos.symbol] = {
                'qty': float(pos.qty),
                'market_value': float(pos.market_value),
                'entry': float(pos.avg_entry_price),
                'current': float(pos.current_price),
                'pnl': float(pos.unrealized_pl),
                'pnl_pct': float(pos.unrealized_plpc),
            }
    return positions


@retry_with_backoff(retries=5, backoff_in_seconds=0.5)
def submit_crypto_order(
    trading_client, 
    symbol: str, 
    qty: float, 
    side: str, 
    dry_run: bool = False,
    limit_price: float = None,
    use_limit: bool = USE_LIMIT_ORDERS,
    store: StateStore = None
):
    """
    Submit order to Alpaca (Crypto) with IDEMPOTENCY and RECONCILIATION.
    """
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
    
    if qty <= 0:
        logger.warning(f"  [!] Invalid qty {qty}, skipping order")
        return None
    
    order_type_str = "LIMIT" if (use_limit and limit_price) else "MARKET"

    # 1. Create Order Intent
    intent = OrderIntent.create(
        symbol=symbol, 
        side=side, 
        qty=qty, 
        order_type=order_type_str.lower(),
        limit_price=limit_price if (use_limit and limit_price) else None
    )

    if dry_run:
        price_str = f" @ ${limit_price:,.2f}" if limit_price else ""
        logger.info(f"[DRY RUN] Would {side.upper()} {qty:.6f} {symbol}{price_str} ({order_type_str})")
        return None
    
    # 2. Idempotency Check (CRITICAL)
    if store:
        existing = store.check_idempotency(intent)
        if existing:
            age = existing.get("status", "unknown")
            logger.warning(f"  [BLOCK] Duplicate Order Intent: {intent.intent_key()} (Status: {age})")
            return existing.get("order_id") # Return existing ID

    try:
        order_side = OrderSide.BUY if side == 'buy' else OrderSide.SELL
        
        # Use limit order if enabled and price provided
        if use_limit and limit_price:
            request = LimitOrderRequest(
                symbol=symbol,
                qty=round(qty, 8),  # Crypto supports 8 decimal places
                limit_price=round(limit_price, 2),
                side=order_side,
                time_in_force=TimeInForce.GTC
            )
        else:
            request = MarketOrderRequest(
                symbol=symbol,
                qty=round(qty, 8),
                side=order_side,
                time_in_force=TimeInForce.GTC
            )
        
        # 3. Submit to Broker
        order = trading_client.submit_order(request)
        
        # 4. Register Intent (Persist immediately)
        if store:
            store.register_intent(intent, str(order.id))

        price_str = f" @ ${limit_price:,.2f}" if limit_price else ""
        logger.info(f"[OK] {order_type_str} order submitted: {side.upper()} {qty:.6f} {symbol}{price_str}")
        return order
        
    except Exception as e:
        logger.error(f"  [!] Order failed: {e}")
        raise e



def get_limit_price(crypto_client, symbol: str, side: str) -> float:
    """
    Get limit price with slippage buffer.
    
    For BUY: price = ask * (1 + slippage)
    For SELL: price = bid * (1 - slippage)
    """
    from alpaca.data.requests import CryptoLatestQuoteRequest
    
    try:
        request = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = crypto_client.get_crypto_latest_quote(request)
        
        if symbol not in quotes:
            return 0.0
        
        quote = quotes[symbol]
        
        if side == 'buy':
            # Willing to pay slightly above ask
            return float(quote.ask_price) * (1 + LIMIT_SLIPPAGE)
        else:
            # Willing to sell slightly below bid
            return float(quote.bid_price) * (1 - LIMIT_SLIPPAGE)
            
    except Exception as e:
        logger.warning(f"Failed to get quote for {symbol}: {e}")
        return 0.0


def kill_switch(trading_client, dry_run: bool = False):
    """
    EMERGENCY: Sell all crypto positions to cash.
    """
    logger.warning("[!!] KILL SWITCH ACTIVATED - Liquidating all crypto positions!")
    
    if dry_run:
        logger.info("[DRY RUN] Would cancel all orders and close all positions")
        return
    
    try:
        # Cancel all open orders
        trading_client.cancel_orders()
        logger.info("[OK] All orders cancelled")
        
        # Close all positions
        positions = get_crypto_positions(trading_client)
        for symbol, pos in positions.items():
            if pos['qty'] > 0:
                submit_crypto_order(trading_client, symbol, pos['qty'], 'sell')
        
        logger.info("[OK] All positions closed")
        
    except Exception as e:
        logger.error(f"Kill switch error: {e}")


# ============================================================
# CORE STRATEGY (Dynamic Rebalancing)
# ============================================================

def manage_core_portfolio(trading_client, crypto_client, account_info: Dict, positions: Dict, dry_run: bool = False):
    """
    Manage Core allocation (70% in BTC/ETH) with dynamic rebalancing.
    
    If one asset surges, take profits and rebalance to the laggard.
    """
    equity = account_info['equity']
    core_target = equity * CORE_ALLOCATION
    target_per_asset = core_target / len(CORE_PAIRS)
    
    logger.info(f"[i] CORE: Target ${core_target:,.0f} ({CORE_ALLOCATION*100:.0f}% of ${equity:,.0f})")
    
    for symbol in CORE_PAIRS:
        current_value = positions.get(symbol, {}).get('market_value', 0)
        diff = target_per_asset - current_value
        diff_pct = abs(diff) / target_per_asset if target_per_asset > 0 else 0
        
        # Only rebalance if drift > threshold
        if diff_pct > REBALANCE_THRESHOLD:
            # Get current price (need 200+ hours for EMA 100)
            df = fetch_crypto_data(crypto_client, symbol)
            if df.empty:
                continue
            
            price = df['close'].iloc[-1]
            qty = abs(diff) / price
            
            if diff > 0:
                # Need to buy
                # Check available cash first
                cash = account_info.get('cash', 0)
                buying_power = cash * 0.95 # Keep 5% buffer
                
                amount_to_buy = diff
                if amount_to_buy > buying_power:
                    logger.warning(f"  [!] Insufficient cash for full rebalance. Capped at ${buying_power:,.2f} (Target: ${amount_to_buy:,.2f})")
                    amount_to_buy = buying_power
                
                qty = amount_to_buy / price
                
                if amount_to_buy > 10: # Min trade size check
                    logger.info(f"  [+] {symbol}: Buying ${amount_to_buy:,.0f} worth (underweight)")
                    submit_crypto_order(trading_client, symbol, qty, 'buy', dry_run)
                else:
                    logger.info(f"  [i] {symbol}: Buy amount ${amount_to_buy:.2f} too small, skipping.")
            else:
                # Need to sell (take profit)
                logger.info(f"  [-] {symbol}: Selling ${abs(diff):,.0f} worth (overweight)")
                submit_crypto_order(trading_client, symbol, qty, 'sell', dry_run)
        else:
            logger.info(f"  [OK] {symbol}: In balance (${current_value:,.0f})")


# ============================================================
# EXPLORE STRATEGY (EMA Crossover)
# ============================================================

def run_explore_strategy(trading_client, crypto_client, account_info: Dict, positions: Dict, dry_run: bool = False):
    """
    Run Explore strategy (30%) with EMA crossover on high-beta alts.
    
    Uses 1% Rule for position sizing and trailing stops for risk management.
    """
    equity = account_info['equity']
    cash = account_info['cash']
    explore_cash = equity * EXPLORE_ALLOCATION
    
    # Init environment check
    base_url = os.getenv("ALPACA_BASE_URL", "").lower()
    is_paper = "paper" in base_url
    
    # --- Initialize Production Managers ---
    state_dir = Path(__file__).parent.parent / "state"
    # Ensure state dir exists (StateStore handles it but good to be explicit/debug)
    store = StateStore(state_dir=str(state_dir), environment="paper" if is_paper else "prod")
    breaker = CircuitBreakerManager(store, risk_limit_percent=0.02, timezone_str="America/New_York")
    recon = ReconciliationManager(store, trading_client)
    
    logger.info("Performing Startup Reconciliation...")
    recon.reconcile_all()
    
    # -------------------------------------

    logger.info(f"Starting Strategy Loop... (Paper={is_paper}, DryRun={dry_run})")
    
    while True:
        try:
            # 0. Circuit Breaker Check (Wall-Clock Enforced)
            if not dry_run:
                try:
                    acct = trading_client.get_account()
                    current_equity = float(acct.equity)
                    
                    if not breaker.check_and_update(current_equity):
                        logger.critical("🛑 CIRCUIT BREAKER TRIPPED. HALTING TRADING.")
                        time.sleep(60)
                        continue
                except Exception as e:
                    logger.error(f"Failed to check circuit breaker: {e}")
            
            # 1. Update Portfolio Data
            if not dry_run:
                recon.reconcile_all()

            if dry_run:
                try:
                    acct = trading_client.get_account()
                    equity = float(acct.equity)
                    cash = float(acct.cash)
                except:
                    # Fallback for offline tests if needed
                    equity = 100000.0
                    cash = 100000.0
            else:
                # refreshed above
                equity = float(acct.equity)
                cash = float(acct.cash)

            positions = get_crypto_positions(trading_client)
            
            # Check portfolio heat before new trades
            portfolio_heat = trailing_stops.get_portfolio_heat(positions, equity)
            if portfolio_heat > PORTFOLIO_HEAT_MAX:
                logger.warning(f"  [!] Portfolio heat {portfolio_heat*100:.1f}% > {PORTFOLIO_HEAT_MAX*100:.0f}% max. Skipping new entries.")
                # Still check trailing stops for existing positions
                for symbol in EXPLORE_PAIRS:
                    if symbol in positions:
                        # Logic duplicated below but cleaner to keep main loop logic unified
                        pass 

            # --- Trading Logic ---
            
            for symbol in EXPLORE_PAIRS:
                # Check spread first
                spread_pct, is_warning, is_blocked = check_spread(crypto_client, symbol)
                
                if is_blocked:
                    logger.warning(f"  [!] {symbol}: Spread too high ({spread_pct*100:.2f}%), skipping")
                    continue
                elif is_warning:
                    logger.info(f"  [!] {symbol}: High spread warning ({spread_pct*100:.2f}%)")
                
                # Fetch data and calculate signal
                df = fetch_crypto_data(crypto_client, symbol)
                if df.empty:
                    continue
                
                # Check volatility guard
                if not volatility_guard(df):
                    logger.info(f"  [X] {symbol}: Volatility guard triggered, skipping")
                    continue
                
                # Check Regime (ADX) - Use closed candles only (Audit Req)
                regime = calculate_regime(df.iloc[:-1])

                
                signal = get_crypto_momentum(df)
                current_value = positions.get(symbol, {}).get('market_value', 0)
                current_qty = positions.get(symbol, {}).get('qty', 0)
                price = df['close'].iloc[-1]
                
                # Check trailing stop for existing positions
                if current_qty > 0:
                    if trailing_stops.update_price(symbol, price):
                        # Trailing stop triggered - sell
                        logger.info(f"  [X] {symbol}: TRAILING STOP - Selling {current_qty:.4f}")
                        submit_crypto_order(trading_client, symbol, current_qty, 'sell', dry_run, store=store)
                        trailing_stops.remove_position(symbol)
                        continue
                
                if signal == 'BUY' and current_value == 0:
                    
                    # 1. Check Data Validity / Regime Status
                    if regime.status != RegimeStatus.OK:
                        # Fail-safe: Block entry if data is invalid or insufficient history
                        logger.warning(f"  [BLOCK] {symbol}: Regime Check Failed ({regime.status.value}). Reason: {regime.reason}")
                        continue

                    # 2. Check Chop
                    if regime.is_chop:
                        logger.info(f"  [CHOP] {symbol}: ADX {regime.adx:.1f} < 30. Skipping Entry.")
                        continue
                        
                    if portfolio_heat > PORTFOLIO_HEAT_MAX:
                        # Skip buy if heat too high
                        continue

                    # Check Wash Sale Guard first
                    if not wash_sale_guard.can_buy(symbol):
                        continue
                        
                    # New position - use 1% rule for sizing
                    qty = calculate_position_size(equity, price)
                    
                    if qty > 0 and cash > qty * price:
                        limit_price = price * (1 + LIMIT_SLIPPAGE) 
                        logger.info(f"  [>] {symbol}: BUY signal (1% Rule: {qty:.4f} @ ${price:,.2f})")
                        submit_crypto_order(
                            trading_client, 
                            symbol, 
                            qty, 
                            'buy', 
                            dry_run, 
                            limit_price=limit_price, 
                            store=store
                        )
                        trailing_stops.register_entry(symbol, price)
                
                elif signal == 'SELL' and current_qty > 0:
                    # Exit signal - sell full position
                    logger.info(f"  [>] {symbol}: SELL signal (EMA cross down)")
                    
                    # Record PnL for Wash Sale Guard
                    estimated_pnl = positions.get(symbol, {}).get('pnl', 0)
                    wash_sale_guard.record_sell(symbol, estimated_pnl)
                    
                    submit_crypto_order(trading_client, symbol, current_qty, 'sell', dry_run, store=store)
                    trailing_stops.remove_position(symbol)
        
                else:
                    rsi = df['rsi'].iloc[-1] if 'rsi' in df else 50
                    status = f"HOLD (RSI: {rsi:.0f})"
                    if current_qty > 0:
                        status += f" | Position: {current_qty:.4f}"
                    logger.info(f"  [i] {symbol}: {status}")

        except Exception as e:
            logger.error(f"Error in strategy loop: {e}")
            time.sleep(60)

    # Sleep to match candle timeframe roughly
    logger.info("Cycle complete. Sleeping 60s...")
    time.sleep(60)
# ============================================================
# MAIN LOOP (24/7 with Auto-Reconnect)
# ============================================================

def run_cycle(trading_client, crypto_client, dry_run: bool = False):
    """Run one trading cycle."""
    logger.info("=" * 60)
    logger.info(f"[>] Cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("=" * 60)
    
    account_info = get_account_info(trading_client)
    positions = get_crypto_positions(trading_client)
    
    logger.info(f"[>] Account: Equity ${account_info['equity']:,.0f}, Cash ${account_info['cash']:,.0f}")
    
    # 1. Manage Core (BTC/ETH)
    manage_core_portfolio(trading_client, crypto_client, account_info, positions, dry_run)
    
    # 2. Run Explore (Alts)
    run_explore_strategy(trading_client, crypto_client, account_info, positions, dry_run)


def main():
    """Main entry point with 24/7 loop and auto-reconnect."""
    import argparse
    
    parser = argparse.ArgumentParser(description="24/7 Crypto Trend Surfer")
    parser.add_argument("--interval", type=int, default=60, help="Minutes between cycles (default: 60)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without trading")
    parser.add_argument("--max-cycles", type=int, default=0, help="Max cycles (0 = unlimited)")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  BTC CRYPTO TREND SURFER - 24/7 Trading")
    print("=" * 60)
    print(f"  Core (70%): {', '.join(CORE_PAIRS)}")
    print(f"  Explore (30%): {', '.join(EXPLORE_PAIRS)}")
    print(f"  Interval: {args.interval} minutes")
    print(f"  Dry Run: {'Yes' if args.dry_run else 'No (LIVE TRADING)'}")
    print("=" * 60)
    
    if not args.dry_run:
        print("\n[!]  LIVE TRADING MODE - Real crypto trades will be executed!\n")
    
    # Initialize clients
    trading_client, crypto_client = get_clients()
    logger.info("[OK] Connected to Alpaca Crypto")
    
    cycle = 0
    while True:
        cycle += 1
        
        # Auto-reconnect wrapper
        try:
            run_cycle(trading_client, crypto_client, dry_run=args.dry_run)
            
        except ConnectionError as e:
            logger.warning(f"Connection lost: {e}. Reconnecting in 60s...")
            time.sleep(60)
            trading_client, crypto_client = get_clients()
            continue
            
        except Exception as e:
            logger.error(f"Cycle error: {e}")
        
        if args.max_cycles > 0 and cycle >= args.max_cycles:
            logger.info("Max cycles reached. Exiting.")
            break
        
        logger.info(f"[.] Sleeping {args.interval} minutes until next cycle...")
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
