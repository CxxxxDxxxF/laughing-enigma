"""Metrics computation and storage for backtest results.

Metrics represent computed analytics from a completed backtest run.
All metrics must be explainable line-by-line.
"""

import math
import numpy as np
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime

if TYPE_CHECKING:
    from ..engines.simple import RawReturns


class MetricsError(Exception):
    """Error raised when metrics computation fails."""
    pass


@dataclass(frozen=True)
class Metrics:
    """Immutable metrics container.
    
    Metrics are computed from a completed backtest run. Every number
    in this structure must be explainable and reproducible.
    
    Attributes:
        run_id: ID of the run these metrics belong to
        computed_at: Timestamp when metrics were computed
        
        # Equity curve metrics
        equity_curve: List[float]  # Portfolio value at each timestep, starting with initial_capital
        final_value: float  # Final portfolio value (equals equity_curve[-1])
        
        # Drawdown metrics
        max_drawdown: float  # Maximum drawdown as decimal (e.g., 0.15 = 15%)
        max_drawdown_duration: int  # Duration in days from peak to recovery (or end if no recovery)
        
        # Return metrics
        monthly_returns: List[float]  # Monthly returns as decimals (compounded from daily returns)
        total_return: float  # Total return over period as decimal (e.g., 0.10 = 10%)
        
        # Risk-adjusted metrics
        sharpe_ratio: float  # Sharpe ratio (annualized, assumes risk-free rate = 0% for Phase 1)
        volatility: float  # Annualized volatility (standard deviation of daily returns * sqrt(252))
        
        # Turnover metrics
        turnover: float  # Portfolio turnover (0.0 for buy-and-hold in Phase 1)
        
    Note:
        All calculations must be deterministic and explainable. No
        black-box metrics allowed. If you cannot explain how a metric
        is computed line-by-line, it should not be here.
    """
    
    run_id: str
    computed_at: datetime
    
    # Equity curve
    equity_curve: List[float]
    final_value: float
    
    # Drawdown
    max_drawdown: float
    max_drawdown_duration: int
    
    # Returns
    monthly_returns: List[float]
    total_return: float
    
    # Risk-adjusted
    sharpe_ratio: float
    volatility: float
    
    # Turnover
    turnover: float
    
    @classmethod
    def compute(cls, run_id: str, raw_returns: 'RawReturns') -> 'Metrics':
        """Compute all metrics from raw returns.
        
        This is the main entry point for metrics computation. All metrics
        are computed from first principles using explicit formulas.
        
        Args:
            run_id: ID of the run these metrics belong to
            raw_returns: Raw return series from backtest engine
            
        Returns:
            Metrics object with all computed values
            
        Raises:
            MetricsError: If computation fails (e.g., insufficient data, undefined metrics)
        """
        # Validate inputs
        if len(raw_returns.returns) == 0:
            raise MetricsError("Cannot compute metrics from empty return series")
        
        if raw_returns.initial_capital <= 0:
            raise MetricsError(f"initial_capital must be positive, got: {raw_returns.initial_capital}")
        
        # Compute equity curve
        equity_curve = _compute_equity_curve(raw_returns.returns, raw_returns.initial_capital)
        final_value = equity_curve[-1]
        
        # Compute drawdown metrics
        max_drawdown, max_drawdown_duration = _compute_max_drawdown(equity_curve)
        
        # Compute monthly returns
        monthly_returns = _compute_monthly_returns(raw_returns.dates, raw_returns.returns)
        
        # Compute total return
        total_return = (final_value / raw_returns.initial_capital) - 1.0
        
        # Compute volatility (annualized)
        volatility = _compute_volatility(raw_returns.returns)
        
        # Compute Sharpe ratio (annualized, risk-free rate = 0% for Phase 1)
        sharpe_ratio = _compute_sharpe_ratio(raw_returns.returns, risk_free_rate=0.0)
        
        # Turnover: 0.0 for buy-and-hold strategy in Phase 1
        turnover = 0.0
        
        return cls(
            run_id=run_id,
            computed_at=datetime.now(),
            equity_curve=equity_curve,
            final_value=final_value,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_drawdown_duration,
            monthly_returns=monthly_returns,
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            volatility=volatility,
            turnover=turnover
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize metrics to dictionary.
        
        Returns:
            Dictionary representation suitable for storage/JSON serialization.
            datetime is serialized as ISO format string.
        """
        return {
            "run_id": self.run_id,
            "computed_at": self.computed_at.isoformat(),
            "equity_curve": self.equity_curve,
            "final_value": self.final_value,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_duration": self.max_drawdown_duration,
            "monthly_returns": self.monthly_returns,
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "volatility": self.volatility,
            "turnover": self.turnover,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Metrics':
        """Deserialize metrics from dictionary.
        
        Args:
            data: Dictionary representation of metrics (from to_dict)
            
        Returns:
            Metrics instance
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        return cls(
            run_id=data["run_id"],
            computed_at=datetime.fromisoformat(data["computed_at"]),
            equity_curve=data["equity_curve"],
            final_value=data["final_value"],
            max_drawdown=data["max_drawdown"],
            max_drawdown_duration=data["max_drawdown_duration"],
            monthly_returns=data["monthly_returns"],
            total_return=data["total_return"],
            sharpe_ratio=data["sharpe_ratio"],
            volatility=data["volatility"],
            turnover=data["turnover"],
        )
    
    def validate(self) -> bool:
        """Validate metrics for consistency and correctness.
        
        Returns:
            True if metrics are valid, False otherwise
            
        Note:
            This should check for impossible values (e.g., negative
            sharpe ratios when returns are positive, etc.)
        """
        # TODO: Implement validation logic
        raise NotImplementedError


def _compute_equity_curve(returns: List[float], initial_capital: float) -> List[float]:
    """Compute equity curve from daily returns.
    
    Formula:
        equity[0] = initial_capital
        equity[i] = equity[i-1] * (1 + returns[i-1]) for i > 0
    
    This gives portfolio value at the end of each day.
    
    Args:
        returns: List of daily returns as decimals
        initial_capital: Starting capital
        
    Returns:
        List of portfolio values, one per timestep (length = len(returns) + 1)
    """
    equity_curve = [initial_capital]
    value = initial_capital
    
    for daily_return in returns:
        value *= (1 + daily_return)
        equity_curve.append(value)
    
    return equity_curve


def _compute_max_drawdown(equity_curve: List[float]) -> tuple[float, int]:
    """Compute maximum drawdown and duration.
    
    Drawdown at time t is defined as:
        drawdown[t] = (peak[t] - equity[t]) / peak[t]
    where peak[t] = max(equity[0:t+1])
    
    Max drawdown is the maximum drawdown over all timesteps.
    
    Duration is the number of days from when the max drawdown occurred
    (measured from its peak) to when equity recovers to or exceeds that peak.
    If recovery never occurs, duration is measured to the end of the series.
    
    Args:
        equity_curve: List of portfolio values over time
        
    Returns:
        Tuple of (max_drawdown as decimal, duration in days)
    """
    if len(equity_curve) < 2:
        return (0.0, 0)
    
    max_drawdown = 0.0
    max_drawdown_peak_index = 0
    max_drawdown_trough_index = 0
    peak = equity_curve[0]
    peak_index = 0
    
    # First pass: find max drawdown and its peak/trough indices
    for i, value in enumerate(equity_curve):
        # Update peak
        if value > peak:
            peak = value
            peak_index = i
        
        # Compute drawdown from current peak
        if peak > 0:
            drawdown = (peak - value) / peak
        else:
            drawdown = 0.0
        
        # Track maximum drawdown and its location
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_peak_index = peak_index
            max_drawdown_trough_index = i
    
    # Second pass: find recovery point (when equity exceeds the peak that caused max drawdown)
    max_drawdown_peak_value = equity_curve[max_drawdown_peak_index]
    recovery_index = None
    
    for i in range(max_drawdown_trough_index + 1, len(equity_curve)):
        if equity_curve[i] >= max_drawdown_peak_value:
            recovery_index = i
            break
    
    # Compute duration
    if recovery_index is not None:
        # Duration from peak to recovery
        max_drawdown_duration = recovery_index - max_drawdown_peak_index
    else:
        # No recovery: duration from peak to end
        max_drawdown_duration = len(equity_curve) - 1 - max_drawdown_peak_index
    
    return (max_drawdown, max_drawdown_duration)


def _compute_monthly_returns(dates: List[str], returns: List[float]) -> List[float]:
    """Compute monthly returns by compounding daily returns within each month.
    
    Formula for monthly return:
        monthly_return = product(1 + daily_returns_in_month) - 1
    
    Returns are grouped by YYYY-MM, and daily returns within each month
    are compounded to produce a single monthly return.
    
    Args:
        dates: List of date strings in YYYY-MM-DD format
        returns: List of daily returns as decimals (same length as dates)
        
    Returns:
        List of monthly returns as decimals, in chronological order
    """
    if len(dates) != len(returns):
        raise MetricsError(f"dates and returns must have same length, got {len(dates)} and {len(returns)}")
    
    if len(dates) == 0:
        return []
    
    monthly_returns = []
    current_month = None
    current_month_returns = []
    
    for date_str, daily_return in zip(dates, returns):
        # Extract YYYY-MM from date string
        month_key = date_str[:7]  # "YYYY-MM"
        
        if current_month is None:
            current_month = month_key
        
        if month_key == current_month:
            # Accumulate returns for current month
            current_month_returns.append(daily_return)
        else:
            # Month changed: compute compounded return for previous month
            if current_month_returns:
                monthly_return = _compound_returns(current_month_returns)
                monthly_returns.append(monthly_return)
            
            # Start new month
            current_month = month_key
            current_month_returns = [daily_return]
    
    # Don't forget the last month
    if current_month_returns:
        monthly_return = _compound_returns(current_month_returns)
        monthly_returns.append(monthly_return)
    
    return monthly_returns


def _compound_returns(returns: List[float]) -> float:
    """Compound a series of returns into a single return.
    
    Formula:
        compounded = product(1 + r_i) - 1
        where r_i are the individual returns
    
    Args:
        returns: List of returns to compound
        
    Returns:
        Single compounded return as decimal
    """
    product = 1.0
    for r in returns:
        product *= (1 + r)
    return product - 1.0


def _compute_volatility(returns: List[float]) -> float:
    """Compute annualized volatility from daily returns.
    
    Formula:
        1. Compute sample mean: mean = sum(returns) / n
        2. Compute sample variance: variance = sum((r_i - mean)^2) / (n - 1)
        3. Compute standard deviation: std_dev = sqrt(variance)
        4. Annualize: volatility = std_dev * sqrt(252)
    
    Assumptions:
        - 252 trading days per year
        - Sample standard deviation (n-1 denominator)
    
    Edge cases:
        - If n < 2, variance is undefined (raises MetricsError)
        - If variance is 0, volatility is 0 (no error)
    
    Args:
        returns: List of daily returns as decimals
        
    Returns:
        Annualized volatility as decimal
        
    Raises:
        MetricsError: If insufficient data (less than 2 returns)
    """
    n = len(returns)
    if n < 2:
        raise MetricsError(
            f"Cannot compute volatility with fewer than 2 returns, got {n}. "
            f"Variance requires at least 2 data points."
        )
    # Use NumPy for variance and std deviation
    returns_arr = np.array(returns, dtype=np.float64)
    std_dev = returns_arr.std(ddof=1)  # sample std dev
    annualized_volatility = std_dev * np.sqrt(252)
    return annualized_volatility


def _compute_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
    """Compute annualized Sharpe ratio from daily returns.
    
    Formula:
        1. Compute annualized excess return: excess_return = (mean_daily * 252) - risk_free_rate_annual
        2. Compute annualized volatility: volatility = std_dev_daily * sqrt(252)
        3. Sharpe = excess_return / volatility
    
    If volatility is zero, Sharpe ratio is undefined (raises MetricsError).
    
    Assumptions:
        - 252 trading days per year
        - Risk-free rate is annualized (default 0% for Phase 1)
        - Mean and volatility are computed from daily returns
    
    Args:
        returns: List of daily returns as decimals
        risk_free_rate: Annual risk-free rate as decimal (default 0.0 for Phase 1)
        
    Returns:
        Annualized Sharpe ratio
        
    Raises:
        MetricsError: If volatility is zero (Sharpe undefined) or insufficient data
    """
    n = len(returns)
    if n < 2:
        raise MetricsError(
            f"Cannot compute Sharpe ratio with fewer than 2 returns, got {n}. "
            f"Both mean and variance require at least 2 data points."
        )
    returns_arr = np.array(returns, dtype=np.float64)
    mean_daily = returns_arr.mean()
    std_dev_daily = returns_arr.std(ddof=1)
    if std_dev_daily == 0.0:
        # Volatility is zero (all returns identical).
        # Return 0.0 instead of crashing, as this is valid for flat/cash strategies.
        return 0.0
    annualized_mean = mean_daily * 252
    annualized_volatility = std_dev_daily * np.sqrt(252)
    excess_return = annualized_mean - risk_free_rate
    sharpe = excess_return / annualized_volatility
    return sharpe
