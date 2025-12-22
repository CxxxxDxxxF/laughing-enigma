"""Evidence report generator for funded firm evaluation.

This module aggregates data from artifacts to generate reports that demonstrate
system behavior over time. Funded firms don't read code - they look at behavior.

Reports include:
- Daily equity curve
- Drawdown over time
- Halts (if any)
- Order count
- Win/loss stats
- Max adverse excursion
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime, date
from dataclasses import dataclass, asdict
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ..core.artifacts import ArtifactStore, LocalArtifactStore

if TYPE_CHECKING:
    from ..lifecycle.runner import CycleResult


@dataclass
class DailyEquity:
    """Daily equity snapshot."""
    date: date
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    drawdown: float
    drawdown_pct: float
    high_water_mark: float


@dataclass
class TradeStatistics:
    """Trade-level statistics."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    max_win: float
    max_loss: float
    max_adverse_excursion: float
    max_favorable_excursion: float


@dataclass
class EvidenceReport:
    """Complete evidence report for funded firm evaluation."""
    portfolio_id: str
    start_date: date
    end_date: date
    total_days: int
    daily_equity: List[DailyEquity]
    trade_stats: TradeStatistics
    order_count: int
    fill_count: int
    halts: List[Dict[str, Any]]
    max_drawdown: float
    max_drawdown_pct: float
    final_equity: float
    total_return_pct: float


def load_cycle_results(
    artifact_store: ArtifactStore,
    portfolio_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """Load cycle results for a portfolio.
    
    Args:
        artifact_store: Artifact store instance
        portfolio_id: Portfolio identifier
        start_date: Optional start date filter
        end_date: Optional end date filter
        
    Returns:
        List of cycle result dicts, sorted by cycle_timestamp
    """
    from pathlib import Path
    
    cycle_results = []
    
    # Access artifact store base path
    if not hasattr(artifact_store, 'base_path'):
        # Cannot scan if we don't have base_path
        return []
    
    base_path = Path(artifact_store.base_path)
    runs_dir = base_path / "runs"
    
    if not runs_dir.exists():
        return []
    
    # Scan all run directories for cycle_result.json
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        
        cycle_id = run_dir.name
        
        # Try to load cycle_result.json
        try:
            result_data = artifact_store.retrieve(cycle_id, "cycle_result.json")
            if result_data is None:
                continue
            
            result_dict = json.loads(result_data.decode('utf-8'))
            
            # Filter by portfolio_id
            if result_dict.get('portfolio_id') != portfolio_id:
                continue
            
            # Filter by date range
            cycle_timestamp_str = result_dict.get('cycle_timestamp')
            if cycle_timestamp_str:
                cycle_timestamp = datetime.fromisoformat(cycle_timestamp_str)
                cycle_date = cycle_timestamp.date()
                
                if start_date and cycle_date < start_date:
                    continue
                if end_date and cycle_date > end_date:
                    continue
            
            cycle_results.append(result_dict)
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Skip invalid cycle results
            continue
    
    # Sort by cycle_timestamp
    cycle_results.sort(key=lambda x: x.get('cycle_timestamp', ''))
    
    return cycle_results


def calculate_daily_equity(
    cycle_results: List[Dict[str, Any]]
) -> List[DailyEquity]:
    """Calculate daily equity from cycle results.
    
    Args:
        cycle_results: List of cycle result dicts
        
    Returns:
        List of DailyEquity snapshots
    """
    daily_equity_map: Dict[date, DailyEquity] = {}
    
    for cycle_result in cycle_results:
        cycle_timestamp = datetime.fromisoformat(cycle_result.get('cycle_timestamp', ''))
        cycle_date = cycle_timestamp.date()
        
        # Extract equity from summary or state
        summary = cycle_result.get('summary', {})
        equity = summary.get('equity', 0.0)
        realized_pnl = summary.get('realized_pnl', 0.0)
        unrealized_pnl = summary.get('unrealized_pnl', 0.0)
        drawdown = summary.get('drawdown', 0.0)
        drawdown_pct = summary.get('drawdown_pct', 0.0)
        high_water_mark = summary.get('high_water_mark', equity)
        
        # Use latest snapshot for each day
        if cycle_date not in daily_equity_map:
            daily_equity_map[cycle_date] = DailyEquity(
                date=cycle_date,
                equity=equity,
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized_pnl,
                drawdown=drawdown,
                drawdown_pct=drawdown_pct,
                high_water_mark=high_water_mark
            )
        else:
            # Update if this cycle is later in the day
            existing = daily_equity_map[cycle_date]
            if cycle_timestamp > datetime.combine(cycle_date, datetime.min.time()):
                daily_equity_map[cycle_date] = DailyEquity(
                    date=cycle_date,
                    equity=equity,
                    realized_pnl=realized_pnl,
                    unrealized_pnl=unrealized_pnl,
                    drawdown=drawdown,
                    drawdown_pct=drawdown_pct,
                    high_water_mark=max(existing.high_water_mark, high_water_mark)
                )
    
    # Sort by date
    return sorted(daily_equity_map.values(), key=lambda x: x.date)


def load_execution_results(
    artifact_store: ArtifactStore,
    execution_ids: List[str]
) -> List[Dict[str, Any]]:
    """Load execution results by execution IDs.
    
    Args:
        artifact_store: Artifact store instance
        execution_ids: List of execution IDs
        
    Returns:
        List of execution result dicts
    """
    execution_results = []
    
    for execution_id in execution_ids:
        if not execution_id:
            continue
        
        try:
            # Try loading rebalance_execution.json
            exec_data = artifact_store.retrieve(execution_id, "rebalance_execution.json")
            if exec_data:
                exec_dict = json.loads(exec_data.decode('utf-8'))
                execution_results.append(exec_dict)
        except (json.JSONDecodeError, KeyError, ValueError):
            # Skip invalid execution results
            continue
    
    return execution_results


def extract_fills_and_orders(
    execution_results: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Extract fills and orders from execution results.
    
    Args:
        execution_results: List of execution result dicts
        
    Returns:
        Tuple of (fills list, orders list)
    """
    fills = []
    orders = []
    
    for exec_result in execution_results:
        intent_results = exec_result.get('intent_results', [])
        for intent_result in intent_results:
            # Extract fills
            fills_list = intent_result.get('fills', [])
            fills.extend(fills_list)
            
            # Extract order
            order = intent_result.get('order')
            if order:
                orders.append(order)
    
    return fills, orders


def calculate_trade_statistics(
    fills: List[Dict[str, Any]],
    orders: List[Dict[str, Any]]
) -> TradeStatistics:
    """Calculate trade statistics from fills and orders.
    
    Args:
        fills: List of fill dicts
        orders: List of order dicts
        
    Returns:
        TradeStatistics
    """
    # Group fills by order to identify complete trades
    order_fills: Dict[str, List[Dict[str, Any]]] = {}
    for fill in fills:
        order_id = fill.get('order_id')
        if order_id:
            if order_id not in order_fills:
                order_fills[order_id] = []
            order_fills[order_id].append(fill)
    
    # Calculate trade PnL (simplified - assumes each order is one trade)
    trade_pnls: List[float] = []
    max_adverse_excursion = 0.0
    max_favorable_excursion = 0.0
    
    for order_id, fills_for_order in order_fills.items():
        # Calculate trade PnL from fills
        trade_pnl = 0.0
        for fill in fills_for_order:
            # PnL calculation depends on position context
            # For simplicity, use net_value difference
            side = fill.get('side', 'buy')
            quantity = fill.get('quantity', 0.0)
            price = fill.get('price', 0.0)
            fee = fill.get('fee', 0.0)
            
            if side == 'buy':
                trade_pnl -= (quantity * price + fee)
            else:  # sell
                trade_pnl += (quantity * price - fee)
        
        trade_pnls.append(trade_pnl)
        
        # Track MAE/MFE (would need price history for accurate calculation)
        # For now, use PnL as proxy
        if trade_pnl < 0:
            max_adverse_excursion = min(max_adverse_excursion, trade_pnl)
        if trade_pnl > 0:
            max_favorable_excursion = max(max_favorable_excursion, trade_pnl)
    
    # Calculate statistics
    total_trades = len(trade_pnls)
    winning_trades = sum(1 for pnl in trade_pnls if pnl > 0)
    losing_trades = sum(1 for pnl in trade_pnls if pnl < 0)
    win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
    
    total_pnl = sum(trade_pnls)
    wins = [pnl for pnl in trade_pnls if pnl > 0]
    losses = [pnl for pnl in trade_pnls if pnl < 0]
    
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    max_win = max(wins) if wins else 0.0
    max_loss = min(losses) if losses else 0.0
    
    return TradeStatistics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        total_pnl=total_pnl,
        avg_win=avg_win,
        avg_loss=avg_loss,
        max_win=max_win,
        max_loss=max_loss,
        max_adverse_excursion=max_adverse_excursion,
        max_favorable_excursion=max_favorable_excursion
    )


def load_halts(
    artifact_store: ArtifactStore,
    portfolio_id: str
) -> List[Dict[str, Any]]:
    """Load halt flags for a portfolio.
    
    Args:
        artifact_store: Artifact store instance
        portfolio_id: Portfolio identifier
        
    Returns:
        List of halt dicts
    """
    from ..lifecycle.runner import HaltFlagStore
    
    halt_store = HaltFlagStore(artifact_store)
    
    if not halt_store.halt_flag_exists(portfolio_id):
        return []
    
    halt_data = halt_store.read_halt_flag(portfolio_id)
    if halt_data:
        return [halt_data]
    return []


def generate_evidence_report(
    artifact_store: ArtifactStore,
    portfolio_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> EvidenceReport:
    """Generate evidence report for a portfolio.
    
    Args:
        artifact_store: Artifact store instance
        portfolio_id: Portfolio identifier
        start_date: Optional start date filter
        end_date: Optional end date filter
        
    Returns:
        EvidenceReport
    """
    # Load cycle results
    cycle_results = load_cycle_results(artifact_store, portfolio_id, start_date, end_date)
    
    if not cycle_results:
        raise ValueError(f"No cycle results found for portfolio {portfolio_id}")
    
    # Calculate daily equity
    daily_equity = calculate_daily_equity(cycle_results)
    
    if not daily_equity:
        raise ValueError(f"No daily equity data found for portfolio {portfolio_id}")
    
    # Extract fills and orders from cycle results
    fills = []
    orders = []
    for cycle_result in cycle_results:
        # Extract from execution result
        execution_id = cycle_result.get('rebalance_execution_id')
        if execution_id:
            # Load execution result
            execution_data = artifact_store.retrieve(execution_id, "rebalance_execution.json")
            if execution_data:
                execution_dict = json.loads(execution_data.decode('utf-8'))
                intent_results = execution_dict.get('intent_results', [])
                for intent_result in intent_results:
                    fills.extend(intent_result.get('fills', []))
                    if intent_result.get('order'):
                        orders.append(intent_result['order'])
    
    # Calculate trade statistics
    trade_stats = calculate_trade_statistics(fills, orders)
    
    # Load halts
    halts = load_halts(artifact_store, portfolio_id)
    
    # Validation: If halt occurred, verify it's reflected in cycle results
    if halts:
        # Check if any cycle result has status "halted"
        halted_cycles = [cr for cr in cycle_results if cr.get('status') == 'halted']
        if not halted_cycles:
            raise ValueError(
                f"Halt flag exists for portfolio {portfolio_id}, but no halted cycles found in results. "
                "This indicates a mismatch between halt flag and cycle results."
            )
    
    # Calculate summary metrics
    max_drawdown = max((de.drawdown for de in daily_equity), default=0.0)
    max_drawdown_pct = max((de.drawdown_pct for de in daily_equity), default=0.0)
    final_equity = daily_equity[-1].equity if daily_equity else 0.0
    initial_equity = daily_equity[0].equity if daily_equity else 0.0
    total_return_pct = ((final_equity - initial_equity) / initial_equity * 100.0) if initial_equity > 0 else 0.0
    
    return EvidenceReport(
        portfolio_id=portfolio_id,
        start_date=daily_equity[0].date if daily_equity else date.today(),
        end_date=daily_equity[-1].date if daily_equity else date.today(),
        total_days=len(set(de.date for de in daily_equity)),
        daily_equity=daily_equity,
        trade_stats=trade_stats,
        order_count=len(orders),
        fill_count=len(fills),
        halts=halts,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
        final_equity=final_equity,
        total_return_pct=total_return_pct
    )


def report_to_dict(report: EvidenceReport) -> Dict[str, Any]:
    """Convert report to dictionary for JSON serialization.
    
    Args:
        report: EvidenceReport instance
        
    Returns:
        Dictionary representation
    """
    return {
        "portfolio_id": report.portfolio_id,
        "start_date": report.start_date.isoformat(),
        "end_date": report.end_date.isoformat(),
        "total_days": report.total_days,
        "daily_equity": [
            {
                "date": de.date.isoformat(),
                "equity": de.equity,
                "realized_pnl": de.realized_pnl,
                "unrealized_pnl": de.unrealized_pnl,
                "drawdown": de.drawdown,
                "drawdown_pct": de.drawdown_pct,
                "high_water_mark": de.high_water_mark
            }
            for de in report.daily_equity
        ],
        "trade_stats": asdict(report.trade_stats),
        "order_count": report.order_count,
        "fill_count": report.fill_count,
        "halts": report.halts,
        "max_drawdown": report.max_drawdown,
        "max_drawdown_pct": report.max_drawdown_pct,
        "final_equity": report.final_equity,
        "total_return_pct": report.total_return_pct
    }


def print_evidence_report(report: EvidenceReport) -> None:
    """Print human-readable evidence report.
    
    Args:
        report: EvidenceReport instance
    """
    print("=" * 80)
    print(f"Evidence Report: {report.portfolio_id}")
    print("=" * 80)
    print(f"Period: {report.start_date} to {report.end_date} ({report.total_days} days)")
    print()
    
    print("Equity Summary:")
    print(f"  Initial Equity: ${report.daily_equity[0].equity:,.2f}" if report.daily_equity else "  Initial Equity: N/A")
    print(f"  Final Equity: ${report.final_equity:,.2f}")
    print(f"  Total Return: {report.total_return_pct:.2f}%")
    print(f"  Max Drawdown: ${report.max_drawdown:,.2f} ({report.max_drawdown_pct:.2f}%)")
    print()
    
    print("Trade Statistics:")
    print(f"  Total Trades: {report.trade_stats.total_trades}")
    print(f"  Winning Trades: {report.trade_stats.winning_trades}")
    print(f"  Losing Trades: {report.trade_stats.losing_trades}")
    print(f"  Win Rate: {report.trade_stats.win_rate:.2%}")
    print(f"  Total PnL: ${report.trade_stats.total_pnl:,.2f}")
    print(f"  Avg Win: ${report.trade_stats.avg_win:,.2f}")
    print(f"  Avg Loss: ${report.trade_stats.avg_loss:,.2f}")
    print(f"  Max Win: ${report.trade_stats.max_win:,.2f}")
    print(f"  Max Loss: ${report.trade_stats.max_loss:,.2f}")
    print(f"  Max Adverse Excursion: ${report.trade_stats.max_adverse_excursion:,.2f}")
    print()
    
    print("Order Statistics:")
    print(f"  Total Orders: {report.order_count}")
    print(f"  Total Fills: {report.fill_count}")
    print()
    
    if report.halts:
        print("Halts:")
        for i, halt in enumerate(report.halts, 1):
            print(f"  {i}. {halt.get('halted_at', 'Unknown')}: {halt.get('reason', 'Unknown')}")
        print()
    
    print("Daily Equity (last 10 days):")
    for de in report.daily_equity[-10:]:
        print(f"  {de.date}: ${de.equity:,.2f} (Drawdown: {de.drawdown_pct:.2f}%)")
    print()
    
    print("=" * 80)

