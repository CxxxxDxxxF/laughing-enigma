"""
Market Regime Detection Module (Hardened).

Classifies market state (Trending vs Chop) using ADX (Average Directional Index).
Includes strict data validation and fail-safe defaults.
Dependency: pandas, numpy, dataclasses
"""

import pandas as pd
import numpy as np
import logging
from typing import Tuple, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class RegimeStatus(str, Enum):
    OK = "ok"
    INSUFFICIENT_HISTORY = "insufficient_history"
    DATA_INVALID = "data_invalid"

@dataclass
class RegimeResult:
    adx: float
    is_chop: bool
    status: str       # RegimeStatus
    reason: str = ""

def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate ADX using pandas ewm (Wilder's approximation).
    
    Args:
        df: DataFrame with 'high', 'low', 'close', validated.
        period: Lookback period.
    Returns:
        pd.Series: ADX values (0-100).
    """
    # Validation should be handled by caller. Pandas will produce NaNs if insufficient.


    high = df['high']
    low = df['low']
    close = df['close']
    
    # TR
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # DM
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)
    
    # Smoothing
    alpha = 1.0 / period
    tr_smooth = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_dm_smooth = plus_dm.ewm(alpha=alpha, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(alpha=alpha, adjust=False).mean()
    
    # DI
    plus_di = 100 * (plus_dm_smooth / tr_smooth.replace(0, np.nan)).fillna(0)
    minus_di = 100 * (minus_dm_smooth / tr_smooth.replace(0, np.nan)).fillna(0)
    
    # DX
    dx_diff = (plus_di - minus_di).abs()
    dx_sum = plus_di + minus_di
    dx = 100 * (dx_diff / dx_sum.replace(0, np.nan)).fillna(0)
    
    # ADX
    adx = dx.ewm(alpha=alpha, adjust=False).mean()
    return adx

def calculate_regime(df: pd.DataFrame, 
                     threshold: float = 30.0, 
                     period: int = 14,
                     confirmation_window: int = 3) -> RegimeResult:
    """
    Determine if market is trending or choppy with strict validation.
    
    Returns:
        RegimeResult
    """
    # 1. Validation: Required Columns
    required = ['high', 'low', 'close']
    if df.empty or not all(col in df.columns for col in required):
        msg = f"Missing required columns: {required} or empty DF"
        return RegimeResult(0.0, True, RegimeStatus.DATA_INVALID, msg)

    # 2. Validation: Finite Check (Last N rows)
    check_window = max(10, period)
    last_rows = df.tail(check_window)
    if not np.isfinite(last_rows[required]).all().all():
         return RegimeResult(0.0, True, RegimeStatus.DATA_INVALID, "NaNs or Infs in OHLC data")

    # 3. Validation: Monotonic Index
    if not df.index.is_monotonic_increasing:
         return RegimeResult(0.0, True, RegimeStatus.DATA_INVALID, "Index not monotonic increasing")

    # 4. Validation: Sufficient History
    warmup = period * 2
    if len(df) < warmup:
        return RegimeResult(0.0, True, RegimeStatus.INSUFFICIENT_HISTORY, f"Len {len(df)} < Warmup {warmup}")

    # 5. Calculate ADX
    adx_series = calculate_adx(df, period)
    
    # 6. Hysteresis / Confirmation
    # Use median of last N confirmed values to avoid flapping.
    if len(adx_series) < confirmation_window:
        # Fallback if somehow history checks passed but adx series short? Unlikely.
        current_adx = adx_series.iloc[-1]
    else:
        recent_adx = adx_series.tail(confirmation_window)
        current_adx = float(recent_adx.median())
    
    # Fail-safe zero check (should be handled by calc but safety first)
    if np.isnan(current_adx):
        return RegimeResult(0.0, True, RegimeStatus.DATA_INVALID, "ADX resulted in NaN")

    is_chop = current_adx < threshold
    
    return RegimeResult(
        adx=float(current_adx),
        is_chop=is_chop,
        status=RegimeStatus.OK
    )
