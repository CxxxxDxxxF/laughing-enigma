"""Divergence analysis between backtest and paper execution.

This module provides deterministic analysis to compare backtest predictions
with actual paper trading execution results.

Key concepts:
- Alignment: Match backtest signals/returns with paper fills by timestamp
- Divergence: Differences between intended (backtest) and actual (paper) outcomes
- Attribution: Identify causes of divergence (timing, sizing, price)
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

from ..engines.simple import RawReturns
from ..core.metrics import Metrics
from ..execution import Fill, Position, Order
from ..core.artifacts import ArtifactStore


class DivergenceAnalysisError(Exception):
    """Error raised when divergence analysis fails."""
    pass


class DivergenceCause(str, Enum):
    """Causes of divergence between backtest and paper execution."""
    TIMING_DRIFT = "timing_drift"  # Signal time vs execution time mismatch
    POSITION_SIZING = "position_sizing"  # Intended vs actual position size
    EXECUTION_PRICE = "execution_price"  # Backtest price vs fill price
    SIGNAL_DELAY = "signal_delay"  # Delay between signal and execution
    MISSING_EXECUTION = "missing_execution"  # Signal had no corresponding execution
    EXTRA_EXECUTION = "extra_execution"  # Execution without corresponding signal


@dataclass
class DivergencePoint:
    """A single point of divergence at a specific timestamp.
    
    Represents the difference between backtest intent and paper execution
    at a specific point in time.
    
    Attributes:
        timestamp: Timestamp of this divergence point
        backtest_equity: Equity value from backtest at this time
        paper_equity: Equity value from paper trading at this time
        equity_difference: Difference (paper - backtest)
        backtest_position: Intended position size from backtest
        paper_position: Actual position size from paper trading
        position_difference: Difference (paper - backtest)
        backtest_price: Price used in backtest
        paper_price: Price used in paper execution (fill price)
        price_difference: Difference (paper - backtest)
        signal_timestamp: When signal was generated
        execution_timestamp: When order was executed
        timing_drift_seconds: Difference in seconds (execution - signal)
        causes: List of divergence causes identified
    """
    
    timestamp: datetime
    backtest_equity: float
    paper_equity: float
    equity_difference: float
    backtest_position: float
    paper_position: float
    position_difference: float
    backtest_price: Optional[float] = None
    paper_price: Optional[float] = None
    price_difference: Optional[float] = None
    signal_timestamp: Optional[datetime] = None
    execution_timestamp: Optional[datetime] = None
    timing_drift_seconds: Optional[float] = None
    causes: List[str] = None
    
    def __post_init__(self):
        """Initialize causes list if None."""
        if self.causes is None:
            self.causes = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        data['timestamp'] = self.timestamp.isoformat()
        if self.signal_timestamp:
            data['signal_timestamp'] = self.signal_timestamp.isoformat()
        if self.execution_timestamp:
            data['execution_timestamp'] = self.execution_timestamp.isoformat()
        return data


@dataclass
class DivergenceMetrics:
    """Aggregate divergence metrics between backtest and paper execution.
    
    Attributes:
        total_equity_divergence: Cumulative difference in equity (paper - backtest)
        max_equity_divergence: Maximum absolute equity difference
        final_equity_divergence: Equity difference at end of period
        average_timing_drift_seconds: Average delay between signal and execution
        max_timing_drift_seconds: Maximum delay between signal and execution
        average_exposure_drift: Average difference in position size
        max_exposure_drift: Maximum absolute position size difference
        average_price_impact: Average difference between backtest and fill prices
        max_price_impact: Maximum absolute price difference
        total_divergence_points: Number of divergence points analyzed
        attribution: Dictionary mapping divergence causes to counts
    """
    
    total_equity_divergence: float
    max_equity_divergence: float
    final_equity_divergence: float
    average_timing_drift_seconds: float
    max_timing_drift_seconds: float
    average_exposure_drift: float
    max_exposure_drift: float
    average_price_impact: Optional[float]
    max_price_impact: Optional[float]
    total_divergence_points: int
    attribution: Dict[str, int]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return asdict(self)


@dataclass
class DivergenceAnalysis:
    """Complete divergence analysis result.
    
    Attributes:
        backtest_run_id: Identifier for the backtest run
        paper_session_id: Identifier for the paper trading session
        analysis_timestamp: When analysis was performed
        divergence_points: List of divergence points over time
        metrics: Aggregate divergence metrics
        alignment_summary: Summary of timestamp alignment (matched/unmatched signals/fills)
    """
    
    backtest_run_id: str
    paper_session_id: str
    analysis_timestamp: datetime
    divergence_points: List[DivergencePoint]
    metrics: DivergenceMetrics
    alignment_summary: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "backtest_run_id": self.backtest_run_id,
            "paper_session_id": self.paper_session_id,
            "analysis_timestamp": self.analysis_timestamp.isoformat(),
            "divergence_points": [dp.to_dict() for dp in self.divergence_points],
            "metrics": self.metrics.to_dict(),
            "alignment_summary": self.alignment_summary,
        }


def _align_by_timestamp(
    backtest_returns: RawReturns,
    fills: List[Fill],
    tolerance_seconds: float = 86400.0  # 1 day default
) -> List[Tuple[Optional[int], Optional[Fill]]]:
    """Align backtest returns with paper fills by timestamp.
    
    For each fill, find the corresponding backtest return (by date).
    For each backtest return that should have a signal, find corresponding fills.
    
    Args:
        backtest_returns: Raw returns from backtest
        fills: List of fills from paper execution
        tolerance_seconds: Maximum time difference for alignment (default: 1 day)
        
    Returns:
        List of tuples (backtest_index, fill) where:
        - backtest_index is the index into backtest_returns.dates/returns
        - fill is the corresponding Fill object (or None)
        - Either can be None if no match found
    """
    alignments = []
    
    # Parse backtest dates
    backtest_dates = [
        datetime.strptime(date_str, "%Y-%m-%d") for date_str in backtest_returns.dates
    ]
    
    # Create fill lookup by date (rounded to day)
    fill_by_date: Dict[datetime.date, List[Fill]] = {}
    for fill in fills:
        fill_date = fill.timestamp.date() if fill.timestamp else None
        if fill_date:
            if fill_date not in fill_by_date:
                fill_by_date[fill_date] = []
            fill_by_date[fill_date].append(fill)
    
    # Match each backtest date with fills
    for i, backtest_date in enumerate(backtest_dates):
        backtest_day = backtest_date.date()
        matched_fills = fill_by_date.get(backtest_day, [])
        
        # For simplicity, take first fill on that day
        # In production, you might match by order_id or more sophisticated logic
        matched_fill = matched_fills[0] if matched_fills else None
        alignments.append((i, matched_fill))
    
    # Also check for fills without corresponding backtest dates
    for fill in fills:
        fill_date = fill.timestamp.date() if fill.timestamp else None
        if fill_date:
            # Check if this fill was already matched
            already_matched = any(
                f is not None and f.id == fill.id
                for _, f in alignments
            )
            if not already_matched:
                # Find closest backtest date
                fill_datetime = fill.timestamp if fill.timestamp else None
                if fill_datetime:
                    closest_idx = None
                    min_diff = float('inf')
                    for i, bt_date in enumerate(backtest_dates):
                        diff = abs((fill_datetime - bt_date).total_seconds())
                        if diff < min_diff and diff <= tolerance_seconds:
                            min_diff = diff
                            closest_idx = i
                    
                    if closest_idx is not None:
                        # Add alignment if this backtest date doesn't have a fill yet
                        if alignments[closest_idx][1] is None:
                            alignments[closest_idx] = (closest_idx, fill)
    
    return alignments


def _calculate_backtest_equity_series(
    raw_returns: RawReturns
) -> List[float]:
    """Calculate equity curve from raw returns.
    
    Args:
        raw_returns: Raw returns from backtest
        
    Returns:
        List of equity values, one per return date
    """
    equity = raw_returns.initial_capital
    equity_series = [equity]
    
    for ret in raw_returns.returns:
        equity *= (1 + ret)
        equity_series.append(equity)
    
    return equity_series


def _calculate_paper_equity_series(
    fills: List[Fill],
    initial_capital: float,
    backtest_dates: List[datetime],
    positions_by_date: Dict[datetime.date, Position],
    prices_by_date: Optional[Dict[datetime.date, float]] = None
) -> List[float]:
    """Calculate paper equity curve from fills and positions.
    
    Equity = Cash + Position Value (market value) + Realized PnL
    
    Args:
        fills: List of fills from paper execution
        initial_capital: Starting capital
        backtest_dates: Dates from backtest (for alignment)
        positions_by_date: Positions keyed by date
        prices_by_date: Optional prices by date for market value calculation
        
    Returns:
        List of equity values aligned with backtest dates
    """
    equity_series = []
    
    # Create position lookup by date
    positions_by_date_lookup = {
        date.date(): pos for date, pos in positions_by_date.items()
    }
    
    # Build fill timeline: map date -> list of fills on that date
    fills_by_date: Dict[datetime.date, List[Fill]] = {}
    for fill in fills:
        if fill.timestamp:
            fill_date = fill.timestamp.date()
            if fill_date not in fills_by_date:
                fills_by_date[fill_date] = []
            fills_by_date[fill_date].append(fill)
    
    # Track cash and realized PnL over time
    current_cash = initial_capital
    current_realized_pnl = 0.0
    
    # Calculate equity for each date
    for date in backtest_dates:
        date_key = date.date()
        
        # Process fills on this date (updating cash)
        if date_key in fills_by_date:
            for fill in fills_by_date[date_key]:
                if fill.side == "buy":
                    current_cash -= (fill.quantity * fill.price + fill.fee)
                else:  # sell
                    current_cash += (fill.quantity * fill.price - fill.fee)
        
        # Get position at this date
        position = positions_by_date_lookup.get(date_key)
        if position:
            current_realized_pnl = position.realized_pnl or 0.0
        
        # Base equity = cash + realized PnL
        equity = current_cash + current_realized_pnl
        
        # Add unrealized PnL if we have position and prices
        if position and prices_by_date:
            current_price = prices_by_date.get(date_key)
            if current_price is not None and position.quantity != 0:
                # Unrealized PnL = (current_price - cost_basis) * quantity
                unrealized_pnl = (current_price - position.cost_basis) * position.quantity
                equity += unrealized_pnl
        
        equity_series.append(equity)
    
    return equity_series


def _compute_divergence_points(
    raw_returns: RawReturns,
    fills: List[Fill],
    orders: List[Order],
    positions_by_date: Dict[datetime.date, Position],
    alignments: List[Tuple[Optional[int], Optional[Fill]]],
    prices_by_date: Optional[Dict[datetime.date, float]] = None
) -> List[DivergencePoint]:
    """Compute divergence points from aligned data.
    
    Args:
        raw_returns: Raw returns from backtest
        fills: List of fills from paper execution
        orders: List of orders from paper execution
        positions_by_date: Positions keyed by date
        alignments: Aligned backtest indices and fills
        prices_by_date: Optional prices by date for equity calculation
        
    Returns:
        List of divergence points
    """
    divergence_points = []
    
    backtest_dates = [
        datetime.strptime(date_str, "%Y-%m-%d") for date_str in raw_returns.dates
    ]
    backtest_equity_series = _calculate_backtest_equity_series(raw_returns)
    
    # Calculate backtest position (simplified: based on return direction)
    # In a real system, this would come from actual strategy signals
    backtest_positions = []
    for ret in raw_returns.returns:
        if ret > 0.0001:  # Small threshold to avoid noise
            backtest_positions.append(1.0)  # Long
        elif ret < -0.0001:
            backtest_positions.append(-1.0)  # Short
        else:
            backtest_positions.append(0.0)  # Flat
    
    # Calculate paper equity series
    paper_equity_series = _calculate_paper_equity_series(
        fills, raw_returns.initial_capital, backtest_dates, positions_by_date, prices_by_date
    )
    
    # Create order lookup by fill
    order_by_id = {order.id: order for order in orders}
    
    # Process each alignment point
    for backtest_idx, fill in alignments:
        if backtest_idx is None:
            continue
        
        timestamp = backtest_dates[backtest_idx]
        backtest_equity = backtest_equity_series[backtest_idx + 1] if backtest_idx + 1 < len(backtest_equity_series) else backtest_equity_series[-1]
        paper_equity = paper_equity_series[backtest_idx] if backtest_idx < len(paper_equity_series) else paper_equity_series[-1]
        
        backtest_position = backtest_positions[backtest_idx] if backtest_idx < len(backtest_positions) else 0.0
        paper_position_obj = positions_by_date.get(timestamp.date())
        paper_position = paper_position_obj.quantity if paper_position_obj else 0.0
        
        # Identify causes
        causes = []
        
        # Timing drift
        signal_timestamp = None
        execution_timestamp = None
        timing_drift = None
        
        if fill:
            execution_timestamp = fill.timestamp
            order = order_by_id.get(fill.order_id)
            if order and order.accepted_at:
                signal_timestamp = order.accepted_at  # Approximate signal time as order acceptance
                timing_drift = (execution_timestamp - signal_timestamp).total_seconds()
                if abs(timing_drift) > 1.0:  # More than 1 second
                    causes.append(DivergenceCause.TIMING_DRIFT.value)
        
        # Position sizing difference
        if abs(backtest_position - paper_position) > 0.01:
            causes.append(DivergenceCause.POSITION_SIZING.value)
        
        # Price impact (simplified - would need backtest prices)
        backtest_price = None  # Would need to extract from backtest
        paper_price = fill.price if fill else None
        price_diff = None
        if backtest_price is not None and paper_price is not None:
            price_diff = paper_price - backtest_price
            if abs(price_diff) > 0.01:
                causes.append(DivergenceCause.EXECUTION_PRICE.value)
        
        if not causes:
            causes.append("none")  # No significant divergence
        
        divergence_point = DivergencePoint(
            timestamp=timestamp,
            backtest_equity=backtest_equity,
            paper_equity=paper_equity,
            equity_difference=paper_equity - backtest_equity,
            backtest_position=backtest_position,
            paper_position=paper_position,
            position_difference=paper_position - backtest_position,
            backtest_price=backtest_price,
            paper_price=paper_price,
            price_difference=price_diff,
            signal_timestamp=signal_timestamp,
            execution_timestamp=execution_timestamp,
            timing_drift_seconds=timing_drift,
            causes=causes
        )
        
        divergence_points.append(divergence_point)
    
    return divergence_points


def _compute_aggregate_metrics(
    divergence_points: List[DivergencePoint]
) -> DivergenceMetrics:
    """Compute aggregate divergence metrics.
    
    Args:
        divergence_points: List of divergence points
        
    Returns:
        DivergenceMetrics object
    """
    if not divergence_points:
        return DivergenceMetrics(
            total_equity_divergence=0.0,
            max_equity_divergence=0.0,
            final_equity_divergence=0.0,
            average_timing_drift_seconds=0.0,
            max_timing_drift_seconds=0.0,
            average_exposure_drift=0.0,
            max_exposure_drift=0.0,
            average_price_impact=None,
            max_price_impact=None,
            total_divergence_points=0,
            attribution={}
        )
    
    equity_diffs = [dp.equity_difference for dp in divergence_points]
    position_diffs = [dp.position_difference for dp in divergence_points]
    
    timing_drifts = [
        dp.timing_drift_seconds for dp in divergence_points
        if dp.timing_drift_seconds is not None
    ]
    
    price_diffs = [
        dp.price_difference for dp in divergence_points
        if dp.price_difference is not None
    ]
    
    # Attribution counts
    attribution = {}
    for dp in divergence_points:
        for cause in dp.causes:
            attribution[cause] = attribution.get(cause, 0) + 1
    
    return DivergenceMetrics(
        total_equity_divergence=sum(equity_diffs),
        max_equity_divergence=max(abs(d) for d in equity_diffs),
        final_equity_divergence=equity_diffs[-1] if equity_diffs else 0.0,
        average_timing_drift_seconds=sum(timing_drifts) / len(timing_drifts) if timing_drifts else 0.0,
        max_timing_drift_seconds=max(abs(t) for t in timing_drifts) if timing_drifts else 0.0,
        average_exposure_drift=sum(abs(d) for d in position_diffs) / len(position_diffs) if position_diffs else 0.0,
        max_exposure_drift=max(abs(d) for d in position_diffs) if position_diffs else 0.0,
        average_price_impact=sum(price_diffs) / len(price_diffs) if price_diffs else None,
        max_price_impact=max(abs(d) for d in price_diffs) if price_diffs else None,
        total_divergence_points=len(divergence_points),
        attribution=attribution
    )


def analyze_backtest_vs_paper(
    backtest_run_id: str,
    raw_returns: RawReturns,
    paper_session_id: str,
    fills: List[Fill],
    orders: List[Order],
    positions_by_date: Dict[datetime.date, Position],
    tolerance_seconds: float = 86400.0,
    prices_by_date: Optional[Dict[datetime.date, float]] = None
) -> DivergenceAnalysis:
    """Perform deterministic divergence analysis between backtest and paper execution.
    
    This function compares what the backtest predicted vs what actually happened
    in paper trading execution. It aligns data by timestamp and computes divergence
    metrics and attribution.
    
    Process:
    1. Align backtest returns with paper fills by timestamp
    2. Calculate equity series for both backtest and paper
    3. Compute divergence points (equity, position, price differences)
    4. Identify divergence causes (timing, sizing, price)
    5. Compute aggregate metrics
    
    Args:
        backtest_run_id: Identifier for the backtest run
        raw_returns: Raw returns from backtest
        paper_session_id: Identifier for the paper trading session
        fills: List of fills from paper execution
        orders: List of orders from paper execution
        positions_by_date: Positions keyed by date (datetime.date -> Position)
        tolerance_seconds: Maximum time difference for alignment (default: 1 day)
        prices_by_date: Optional prices by date for market value calculation
        
    Returns:
        DivergenceAnalysis object with divergence points and metrics
        
    Raises:
        DivergenceAnalysisError: If analysis fails
        
    Example:
        >>> analysis = analyze_backtest_vs_paper(
        ...     backtest_run_id="run_123",
        ...     raw_returns=raw_returns,
        ...     paper_session_id="session_456",
        ...     fills=fills,
        ...     orders=orders,
        ...     positions_by_date=positions_by_date
        ... )
        >>> print(f"Final equity divergence: {analysis.metrics.final_equity_divergence}")
    """
    try:
        # Align by timestamp
        alignments = _align_by_timestamp(raw_returns, fills, tolerance_seconds)
        
        # Compute divergence points
        divergence_points = _compute_divergence_points(
            raw_returns, fills, orders, positions_by_date, alignments, prices_by_date
        )
        
        # Compute aggregate metrics
        metrics = _compute_aggregate_metrics(divergence_points)
        
        # Alignment summary
        matched_count = sum(1 for _, fill in alignments if fill is not None)
        alignment_summary = {
            "total_backtest_points": len(raw_returns.dates),
            "matched_fills": matched_count,
            "unmatched_backtest_points": len(raw_returns.dates) - matched_count,
            "total_fills": len(fills),
            "unmatched_fills": len(fills) - matched_count,
        }
        
        return DivergenceAnalysis(
            backtest_run_id=backtest_run_id,
            paper_session_id=paper_session_id,
            analysis_timestamp=datetime.now(),
            divergence_points=divergence_points,
            metrics=metrics,
            alignment_summary=alignment_summary
        )
        
    except Exception as e:
        raise DivergenceAnalysisError(f"Failed to analyze divergence: {e}") from e


def persist_divergence_analysis(
    analysis: DivergenceAnalysis,
    artifact_store: ArtifactStore,
    analysis_id: Optional[str] = None
) -> str:
    """Persist divergence analysis to artifact store.
    
    Args:
        analysis: DivergenceAnalysis to persist
        artifact_store: ArtifactStore instance
        analysis_id: Optional analysis identifier (defaults to generated ID)
        
    Returns:
        Analysis identifier (for retrieval)
        
    Raises:
        DivergenceAnalysisError: If persistence fails
    """
    if analysis_id is None:
        analysis_id = f"{analysis.backtest_run_id}_{analysis.paper_session_id}"
    
    try:
        analysis_json = json.dumps(analysis.to_dict(), indent=2).encode('utf-8')
        artifact_store.store(analysis_id, "divergence_analysis.json", analysis_json)
        return analysis_id
    except Exception as e:
        raise DivergenceAnalysisError(f"Failed to persist divergence analysis: {e}") from e

