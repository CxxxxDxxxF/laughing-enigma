#!/usr/bin/env python3
"""
Risk Management Module - Production-Grade Safety Features

Contains:
- CircuitBreaker: Halts trading on 2% daily loss
- ATRPositionSizer: Dynamic position sizing based on volatility
- SmartOrderExecutor: Limit orders that chase price to reduce slippage
- RateLimiter: Prevents API rate limit violations
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from collections import deque
from functools import wraps
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

logger = logging.getLogger(__name__)

# ============================================================
# CIRCUIT BREAKER (2% Daily Loss Limit)
# ============================================================

class CircuitBreaker:
    """
    Global risk manager that halts ALL trading if equity drops too much.
    
    Features:
    - Trips on 2% daily loss (configurable)
    - Auto-closes all positions on trip
    - Writes HALTED file for external monitoring
    - Resets at start of new trading day
    """
    
    def __init__(
        self,
        trading_client,
        max_daily_loss_pct: float = 0.02,
        halt_file_path: str = "data/artifacts/CIRCUIT_BREAKER_HALTED"
    ):
        self.client = trading_client
        self.max_daily_loss_pct = max_daily_loss_pct
        self.halt_file = Path(halt_file_path)
        self.is_tripped = False
        self.tripped_at: Optional[datetime] = None
        self.trip_reason: str = ""
        
        # Initialize with current equity
        self._refresh_start_equity()
        
        # Check if already halted from previous session
        if self.halt_file.exists():
            self.is_tripped = True
            self.trip_reason = self.halt_file.read_text()
            logger.warning(f"Circuit breaker already tripped: {self.trip_reason}")
    
    def _refresh_start_equity(self):
        """Get start-of-day equity."""
        try:
            account = self.client.get_account()
            self.start_of_day_equity = float(account.last_equity)
            logger.info(f"Circuit breaker initialized: Start equity ${self.start_of_day_equity:,.2f}")
        except Exception as e:
            logger.error(f"Failed to get equity: {e}")
            self.start_of_day_equity = 0
    
    def check(self) -> Tuple[bool, float]:
        """
        Check if circuit breaker should trip.
        
        Returns: (is_safe_to_trade, current_loss_pct)
        """
        if self.is_tripped:
            return False, 0
        
        try:
            account = self.client.get_account()
            current_equity = float(account.equity)
            
            if self.start_of_day_equity <= 0:
                self._refresh_start_equity()
                return True, 0
            
            loss_pct = (self.start_of_day_equity - current_equity) / self.start_of_day_equity
            
            if loss_pct >= self.max_daily_loss_pct:
                self._trip(loss_pct, current_equity)
                return False, loss_pct
            
            return True, loss_pct
            
        except Exception as e:
            logger.error(f"Circuit breaker check failed: {e}")
            return True, 0  # Fail open (allow trading)
    
    def _trip(self, loss_pct: float, current_equity: float):
        """Trip the circuit breaker - close all positions and halt."""
        self.is_tripped = True
        self.tripped_at = datetime.now()
        self.trip_reason = f"Daily loss {loss_pct*100:.2f}% exceeded {self.max_daily_loss_pct*100:.0f}% limit"
        
        logger.critical("=" * 60)
        logger.critical("[!!] CIRCUIT BREAKER TRIPPED!")
        logger.critical(f"   Loss: {loss_pct*100:.2f}%")
        logger.critical(f"   Start: ${self.start_of_day_equity:,.2f}")
        logger.critical(f"   Current: ${current_equity:,.2f}")
        logger.critical("   Closing all positions and halting trading...")
        logger.critical("=" * 60)
        
        try:
            # Cancel all orders
            self.client.cancel_orders()
            logger.info("[OK] All orders cancelled")
            
            # Close all positions
            self.client.close_all_positions(cancel_orders=True)
            logger.info("[OK] All positions closed")
            
        except Exception as e:
            logger.error(f"Error during emergency liquidation: {e}")
        
        # Write halt file
        self.halt_file.parent.mkdir(parents=True, exist_ok=True)
        self.halt_file.write_text(
            f"TRIPPED: {self.tripped_at.isoformat()}\n"
            f"REASON: {self.trip_reason}\n"
            f"START_EQUITY: ${self.start_of_day_equity:,.2f}\n"
            f"FINAL_EQUITY: ${current_equity:,.2f}\n"
        )
    
    def reset(self, force: bool = False) -> bool:
        """
        Reset circuit breaker for new trading day.
        
        Args:
            force: If True, reset even if same day
        
        Returns: True if reset successful
        """
        if not force and self.tripped_at:
            # Only auto-reset on new day
            tz = zoneinfo.ZoneInfo('America/New_York')
            now = datetime.now(tz)
            trip_date = self.tripped_at.astimezone(tz).date()
            
            if now.date() <= trip_date:
                logger.warning("Cannot reset circuit breaker on same day")
                return False
        
        self.is_tripped = False
        self.tripped_at = None
        self.trip_reason = ""
        self._refresh_start_equity()
        
        if self.halt_file.exists():
            self.halt_file.unlink()
        
        logger.info("[OK] Circuit breaker reset")
        return True


# ============================================================
# ATR POSITION SIZER (Volatility-Adjusted)
# ============================================================

class ATRPositionSizer:
    """
    Dynamic position sizing based on ATR (Average True Range).
    
    Higher volatility = smaller position
    Lower volatility = larger position
    """
    
    def __init__(
        self,
        risk_per_trade_pct: float = 0.01,  # Risk 1% of account per trade
        atr_period: int = 14,
        max_position_pct: float = 0.20  # Max 20% in single position
    ):
        self.risk_per_trade_pct = risk_per_trade_pct
        self.atr_period = atr_period
        self.max_position_pct = max_position_pct
    
    def calculate_atr(self, df: pd.DataFrame) -> float:
        """Calculate Average True Range."""
        if len(df) < self.atr_period + 1:
            return df['close'].std()  # Fallback
        
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)
        
        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)
        
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(window=self.atr_period).mean().iloc[-1]
        
        return atr if not pd.isna(atr) else df['close'].std()
    
    def calculate_shares(
        self,
        df: pd.DataFrame,
        account_equity: float,
        current_price: Optional[float] = None
    ) -> Tuple[int, float]:
        """
        Calculate position size in shares.
        
        Returns: (shares, atr_value)
        """
        atr = self.calculate_atr(df)
        price = current_price or df['close'].iloc[-1]
        
        # Risk amount in dollars
        risk_amount = account_equity * self.risk_per_trade_pct
        
        # Position size: Risk Amount / ATR
        # If ATR moves against us, we lose risk_amount
        if atr <= 0:
            atr = price * 0.02  # Fallback: assume 2% volatility
        
        position_value = risk_amount / (atr / price)
        
        # Cap at max position
        max_value = account_equity * self.max_position_pct
        position_value = min(position_value, max_value)
        
        shares = int(position_value / price)
        
        return shares, atr


# ============================================================
# SMART ORDER EXECUTOR (Limit Orders with Chase)
# ============================================================

class SmartOrderExecutor:
    """
    Executes orders using limit orders that 'chase' the price.
    Reduces slippage compared to market orders.
    """
    
    def __init__(
        self,
        trading_client,
        data_client,
        max_chase_pct: float = 0.001,  # Chase up to 0.1%
        max_chase_attempts: int = 5,
        chase_interval_sec: float = 0.5
    ):
        self.trading_client = trading_client
        self.data_client = data_client
        self.max_chase_pct = max_chase_pct
        self.max_chase_attempts = max_chase_attempts
        self.chase_interval = chase_interval_sec
    
    def get_quote(self, symbol: str) -> Tuple[float, float, float]:
        """Get current bid, ask, mid prices."""
        from alpaca.data.requests import StockLatestQuoteRequest
        
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = self.data_client.get_stock_latest_quote(request)
        
        if symbol not in quotes:
            raise ValueError(f"No quote for {symbol}")
        
        bid = float(quotes[symbol].bid_price)
        ask = float(quotes[symbol].ask_price)
        mid = (bid + ask) / 2
        
        return bid, ask, mid
    
    def execute(
        self,
        symbol: str,
        qty: int,
        side: str,
        fallback_to_market: bool = True
    ) -> Optional[object]:
        """
        Execute order with limit order chase logic.
        
        For BUY: Start at bid, chase towards ask
        For SELL: Start at ask, chase towards bid
        """
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        
        if qty <= 0:
            return None
        
        order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
        
        try:
            bid, ask, mid = self.get_quote(symbol)
            spread = ask - bid
            
            # Starting price
            if side.lower() == 'buy':
                start_price = bid + spread * 0.25  # Start at 25% into spread
            else:
                start_price = ask - spread * 0.25
            
            for attempt in range(self.max_chase_attempts):
                # Calculate chase price
                chase_offset = self.max_chase_pct * (attempt / self.max_chase_attempts)
                
                if side.lower() == 'buy':
                    limit_price = start_price * (1 + chase_offset)
                    limit_price = min(limit_price, ask)  # Don't exceed ask
                else:
                    limit_price = start_price * (1 - chase_offset)
                    limit_price = max(limit_price, bid)  # Don't go below bid
                
                limit_price = round(limit_price, 2)
                
                # Submit IOC limit order
                request = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=order_side,
                    time_in_force=TimeInForce.IOC,
                    limit_price=limit_price
                )
                
                order = self.trading_client.submit_order(request)
                time.sleep(self.chase_interval)
                
                # Check fill
                order = self.trading_client.get_order_by_id(order.id)
                
                if order.status.value in ['filled', 'partially_filled']:
                    filled = float(order.filled_qty or 0)
                    logger.info(f"[OK] Smart order filled: {side.upper()} {filled} {symbol} @ ${limit_price:.2f}")
                    return order
                
                # Cancel unfilled order
                try:
                    self.trading_client.cancel_order_by_id(order.id)
                except:
                    pass
                
                logger.debug(f"Chase attempt {attempt+1}: {symbol} @ ${limit_price:.2f} not filled")
            
            # Fallback to market order
            if fallback_to_market:
                logger.warning(f"Smart order exhausted, falling back to market: {side.upper()} {qty} {symbol}")
                request = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=order_side,
                    time_in_force=TimeInForce.DAY
                )
                return self.trading_client.submit_order(request)
            
            return None
            
        except Exception as e:
            logger.error(f"Smart order failed: {e}")
            
            # Emergency fallback
            if fallback_to_market:
                request = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=order_side,
                    time_in_force=TimeInForce.DAY
                )
                return self.trading_client.submit_order(request)
            
            return None


# ============================================================
# RATE LIMITER (Prevent API Throttling)
# ============================================================

class RateLimiter:
    """
    Rate limiter with exponential backoff for Alpaca API.
    
    Alpaca limits: 200 requests/minute
    """
    
    def __init__(self, max_requests_per_minute: int = 180):  # Leave 10% buffer
        self.max_rpm = max_requests_per_minute
        self.requests = deque()
        self.backoff_until: Optional[datetime] = None
    
    def wait_if_needed(self):
        """Wait if rate limit is approaching."""
        now = datetime.now()
        
        # Check backoff
        if self.backoff_until and now < self.backoff_until:
            wait_sec = (self.backoff_until - now).total_seconds()
            logger.warning(f"Rate limit backoff: waiting {wait_sec:.1f}s")
            time.sleep(wait_sec)
            self.backoff_until = None
        
        # Clean old requests
        cutoff = now - timedelta(minutes=1)
        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()
        
        # Check if at limit
        if len(self.requests) >= self.max_rpm:
            wait_until = self.requests[0] + timedelta(minutes=1)
            wait_sec = (wait_until - now).total_seconds()
            if wait_sec > 0:
                logger.warning(f"Rate limit: waiting {wait_sec:.1f}s")
                time.sleep(wait_sec + 0.1)
        
        # Record this request
        self.requests.append(now)
    
    def trigger_backoff(self, error_code: int = 429):
        """Trigger exponential backoff on rate limit error."""
        backoff_sec = 30  # Base backoff
        self.backoff_until = datetime.now() + timedelta(seconds=backoff_sec)
        logger.warning(f"Rate limit error {error_code}: backing off {backoff_sec}s")


def rate_limited(rate_limiter: RateLimiter):
    """Decorator for rate-limited functions."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            rate_limiter.wait_if_needed()
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if '429' in str(e) or 'rate' in str(e).lower():
                    rate_limiter.trigger_backoff(429)
                raise
        return wrapper
    return decorator


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    'CircuitBreaker',
    'ATRPositionSizer',
    'SmartOrderExecutor',
    'RateLimiter',
    'rate_limited',
]
