#!/usr/bin/env python3
"""Layer 2: Statistical Backtest Execution

Runs statistical backtests exactly as defined in BACKTEST_SPEC_V1.md Layer 2.

This determines statistical significance of strategy performance.
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import List, Dict, Any, Optional
import zoneinfo

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lifecycle.runner import (
    run_portfolio_cycle,
    ExecutionMode,
    PortfolioCycleConfig,
)
from src.lifecycle.state_store import LocalPortfolioStateStore
from src.core.artifacts import LocalArtifactStore
from src.engines.simple import SimpleResearchEngine
from src.execution import PaperExecutionEngine
from src.rules.day_boundary import TradingDayBoundary
from src.execution.fill import Fill


# Backtest Spec v1 Constants
INSTRUMENTS = ["ES", "NQ", "CL"]
STRATEGY_TYPE = "buy_hold"
DAILY_TREND = 0.001
START_DATE = "2023-01-01"
END_DATE = "2023-12-31"
INITIAL_CAPITAL = 50000.0

# Execution costs per spec
EXECUTION_COSTS = {
    "ES": {
        "slippage_per_contract": 12.50,  # $12.50 per contract
        "commission_per_side": 4.20,      # $4.20 per contract per side
        "round_trip_cost": 33.40          # $33.40 per contract
    },
    "NQ": {
        "slippage_per_contract": 5.00,   # $5.00 per contract
        "commission_per_side": 4.20,      # $4.20 per contract per side
        "round_trip_cost": 18.40          # $18.40 per contract
    },
    "CL": {
        "slippage_per_contract": 10.00,   # $10.00 per contract
        "commission_per_side": 4.20,      # $4.20 per contract per side
        "round_trip_cost": 28.40          # $28.40 per contract
    }
}

# Contract specs
CONTRACT_SPECS = {
    "ES": {
        "multiplier": 50.0,
        "tick_size": 0.25,
        "margin": 13200.0,
        "base_price": 5000.0
    },
    "NQ": {
        "multiplier": 20.0,
        "tick_size": 0.25,
        "margin": 17600.0,
        "base_price": 15000.0
    },
    "CL": {
        "multiplier": 1000.0,
        "tick_size": 0.01,
        "margin": 6600.0,
        "base_price": 75.0
    }
}


def apply_slippage_to_price(price: float, instrument: str, quantity: float, is_entry: bool) -> float:
    """Apply slippage to execution price."""
    if instrument == "ES":
        slippage_points = 0.25
    elif instrument == "NQ":
        slippage_points = 0.25
    elif instrument == "CL":
        slippage_points = 0.01
    else:
        raise ValueError(f"Unknown instrument: {instrument}")
    
    is_long = quantity > 0
    
    if is_entry:
        if is_long:
            return price + slippage_points
        else:
            return price - slippage_points
    else:
        if is_long:
            return price - slippage_points
        else:
            return price + slippage_points


def calculate_trade_metrics(trades: List[Fill], instrument: str, initial_capital: float) -> Dict[str, Any]:
    """Calculate trade-level metrics from fills."""
    if not trades:
        return {
            "trade_count": 0,
            "expectancy_per_trade": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "net_pnl": 0.0,
            "gross_pnl": 0.0,
            "total_execution_costs": 0.0
        }
    
    # Separate entry and exit fills
    entry_fills = [f for f in trades if f.side == "buy"]
    exit_fills = [f for f in trades if f.side == "sell"]
    
    costs = EXECUTION_COSTS[instrument]
    
    # Calculate round-trip trades
    round_trips = []
    entry_idx = 0
    exit_idx = 0
    
    while entry_idx < len(entry_fills) and exit_idx < len(exit_fills):
        entry = entry_fills[entry_idx]
        exit = exit_fills[exit_idx]
        
        # Match entry and exit
        qty = min(entry.quantity, exit.quantity)
        
        # Apply slippage
        entry_price = apply_slippage_to_price(entry.price, instrument, qty, True)
        exit_price = apply_slippage_to_price(exit.price, instrument, qty, False)
        
        # Calculate PnL
        gross_pnl = (exit_price - entry_price) * qty
        
        # Execution costs
        entry_commission = costs["commission_per_side"] * qty
        exit_commission = costs["commission_per_side"] * qty
        entry_slippage_cost = costs["slippage_per_contract"] * qty
        exit_slippage_cost = costs["slippage_per_contract"] * qty
        
        total_costs = entry_commission + exit_commission + entry_slippage_cost + exit_slippage_cost
        net_pnl = gross_pnl - total_costs
        
        round_trips.append({
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "execution_costs": total_costs,
            "quantity": qty
        })
        
        # Update indices
        if entry.quantity == qty:
            entry_idx += 1
        else:
            entry_fills[entry_idx] = Fill(
                id=entry.id,
                order_id=entry.order_id,
                instrument=entry.instrument,
                side=entry.side,
                quantity=entry.quantity - qty,
                price=entry.price,
                fee=entry.fee,
                filled_at=entry.filled_at,
                execution_id=entry.execution_id
            )
        
        if exit.quantity == qty:
            exit_idx += 1
        else:
            exit_fills[exit_idx] = Fill(
                id=exit.id,
                order_id=exit.order_id,
                instrument=exit.instrument,
                side=exit.side,
                quantity=exit.quantity - qty,
                price=exit.price,
                fee=exit.fee,
                filled_at=exit.filled_at,
                execution_id=exit.execution_id
            )
    
    if not round_trips:
        return {
            "trade_count": 0,
            "expectancy_per_trade": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "net_pnl": 0.0,
            "gross_pnl": 0.0,
            "total_execution_costs": 0.0
        }
    
    # Calculate metrics
    trade_count = len(round_trips)
    net_pnls = [rt["net_pnl"] for rt in round_trips]
    gross_pnls = [rt["gross_pnl"] for rt in round_trips]
    execution_costs = [rt["execution_costs"] for rt in round_trips]
    
    net_pnl = sum(net_pnls)
    gross_pnl = sum(gross_pnls)
    total_execution_costs = sum(execution_costs)
    
    expectancy_per_trade = net_pnl / trade_count if trade_count > 0 else 0.0
    
    winning_trades = [pnl for pnl in net_pnls if pnl > 0]
    losing_trades = [pnl for pnl in net_pnls if pnl < 0]
    
    win_rate = len(winning_trades) / trade_count if trade_count > 0 else 0.0
    avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0.0
    avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else 0.0
    
    total_wins = sum(winning_trades) if winning_trades else 0.0
    total_losses = abs(sum(losing_trades)) if losing_trades else 0.0
    profit_factor = total_wins / total_losses if total_losses > 0 else (float('inf') if total_wins > 0 else 0.0)
    
    return {
        "trade_count": trade_count,
        "expectancy_per_trade": expectancy_per_trade,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "net_pnl": net_pnl,
        "gross_pnl": gross_pnl,
        "total_execution_costs": total_execution_costs,
        "round_trips": round_trips
    }


def run_layer2_backtest_for_instrument(instrument: str, light_artifacts: bool = False, num_days_override: Optional[int] = None) -> Dict[str, Any]:
    """Run Layer 2 backtest for a single instrument."""
    
    print("=" * 80)
    print(f"Layer 2: Statistical Backtest - {instrument}")
    print("=" * 80)
    print(f"Instrument: {instrument}")
    print(f"Strategy: {STRATEGY_TYPE} (daily_trend={DAILY_TREND})")
    print(f"Date Range: {START_DATE} to {END_DATE}")
    print(f"Initial Capital: ${INITIAL_CAPITAL:,.2f}")
    print()
    
    # Create artifacts directory
    artifacts_dir = Path(f"./artifacts_layer2_{instrument.lower()}")
    if artifacts_dir.exists():
        import shutil
        shutil.rmtree(artifacts_dir)
    artifacts_dir.mkdir()
    
    # Initialize components
    artifact_store = LocalArtifactStore(artifacts_dir)
    state_store = LocalPortfolioStateStore(artifact_store)
    research_engine = SimpleResearchEngine(artifact_store)
    
    # Calculate number of trading days
    start = datetime.strptime(START_DATE, "%Y-%m-%d")
    end = datetime.strptime(END_DATE, "%Y-%m-%d")
    num_days = num_days_override if num_days_override is not None else ((end - start).days + 1)
    
    # Generate price series (synthetic, deterministic) - cached once
    base_price = CONTRACT_SPECS[instrument]["base_price"]
    price_series = []
    for i in range(num_days):
        price = base_price * (1 + DAILY_TREND) ** i
        price_series.append(price)
    
    # Create base config once (optimization: avoid to_dict/from_dict in loop)
    config_dict = {
        "portfolio_id": f"layer2_{instrument.lower()}",
        "description": f"Layer 2: Statistical Backtest per BACKTEST_SPEC_V1.md - {instrument}",
        "evaluation_config": {
            "strategies": [
                {
                    "strategy_id": f"buy_hold_{instrument.lower()}",
                    "experiment_name": "momentum",
                    "experiment_version": "v1",
                    "experiment_config": {
                        "daily_trend": DAILY_TREND
                    },
                    "inputs": {
                        "start_date": START_DATE,
                        "end_date": END_DATE,
                        "initial_capital": INITIAL_CAPITAL,
                        "instrument": instrument,
                        "strategy_type": STRATEGY_TYPE
                    },
                    "description": f"Buy-and-hold {instrument} strategy with daily_trend=0.001"
                }
            ],
            "parameter_grid": None,
            "evaluation_criteria": {
                "min_robustness_score": 0.0,
                "max_divergence_pct": 1.0,
                "max_timing_drift_seconds": 999999
            },
            "price_series": price_series
        },
        "allocation_config": {
            "total_capital": INITIAL_CAPITAL,
            "top_n_strategies": 1,
            "min_robustness_score": 0.0,
            "max_allocation_per_strategy": 1.0,
            "min_allocation_per_strategy": 0.0,
            "allocation_method": "equal",
            "max_total_leverage": 1.0,
            "require_all_passed": False
        },
        "rebalance_config": {
            "rebalance_threshold_pct": 0.0,
            "max_turnover_pct": 1.0,
            "min_trade_size": 0.0,
            "allow_partial_rebalance": True
        },
        "execution_config": {
            "price_by_strategy_or_instrument": {
                f"buy_hold_{instrument.lower()}": price_series[0] if price_series else base_price,
                instrument: price_series[0] if price_series else base_price
            },
            "rounding_method": "floor",
            "min_quantity": 1.0
        },
        "cadence_config": {
            "frequency": "daily",
            "min_seconds_between_cycles": 86400,
            "timezone": "America/Chicago"
        },
        "guardrails_config": {
            "max_turnover_pct_per_cycle": 1.0,
            "max_failed_intents": 0,
            "min_execution_success_rate": 0.95,
            "max_single_strategy_allocation_fraction": 1.0,
            "halt_on_any_error": True
        },
        "ruleset_type": "topstep",
        "ruleset_config": {
            "max_turnover_pct": 100.0,
            "max_position_size": None,
            "max_daily_loss": -1000.0,
            "max_trailing_drawdown_pct": 5.0,
            "account_size": INITIAL_CAPITAL
        },
        "day_boundary_config": {
            "timezone": "America/Chicago",
            "session_start_time": "17:00:00"
        },
        "validation_hold_quantity": False,
        "validation_bootstrap_first_cycle": True,
        "cycle_id": None
    }
    
    base_config = PortfolioCycleConfig.from_dict(config_dict)
    
    # Create execution engine with fees
    costs = EXECUTION_COSTS[instrument]
    def create_engine():
        return PaperExecutionEngine(
            instrument=instrument,
            artifact_store=artifact_store,
            fixed_fee=costs["commission_per_side"]  # Per fill
        )
    
    # Setup timezone and day boundary
    ct_tz = zoneinfo.ZoneInfo("America/Chicago")
    boundary = TradingDayBoundary(
        timezone=ct_tz,
        session_start_time=time(17, 0, 0)
    )
    
    # Generate cycle timestamps
    start_dt = datetime.strptime(START_DATE, "%Y-%m-%d").replace(tzinfo=ct_tz)
    current_dt = start_dt.replace(hour=17, minute=0, second=0, microsecond=0)
    
    cycle_results = []
    equity_series = []
    daily_losses = []
    daily_loss_breaches = 0
    
    print(f"Running {num_days} cycles...")
    print()
    
    for i, price in enumerate(price_series):
        # Progress heartbeat every 25 cycles
        if i % 25 == 0 or i == 0:
            print(f"[Layer2] {instrument} cycle {i+1}/{num_days} ({(i+1)/num_days*100:.1f}%)", flush=True)
        cycle_id = f"layer2_{instrument.lower()}_cycle_{i+1:03d}"
        cycle_timestamp = current_dt + timedelta(days=i)
        
        # Optimize config reuse: only update mutable fields (price, cycle_id, allocation threshold)
        # Avoid expensive to_dict/from_dict round-trip
        cycle_config = PortfolioCycleConfig(
            portfolio_id=base_config.portfolio_id,
            evaluation_config=base_config.evaluation_config,
            allocation_config=base_config.allocation_config,
            rebalance_config=base_config.rebalance_config,
            execution_config={
                **base_config.execution_config,
                "price_by_strategy_or_instrument": {
                    f"buy_hold_{instrument.lower()}": price,
                    instrument: price
                }
            },
            cadence_config=base_config.cadence_config,
            guardrails_config=base_config.guardrails_config,
            ruleset_type=base_config.ruleset_type,
            ruleset_config=base_config.ruleset_config,
            day_boundary_config=base_config.day_boundary_config,
            cycle_id=cycle_id,
            validation_hold_quantity=base_config.validation_hold_quantity,
            validation_bootstrap_first_cycle=base_config.validation_bootstrap_first_cycle
        )
        
        # Timeboxed exits are now handled at the portfolio cycle level in allocation logic.
        # No special-case logic needed here - exits are enforced generically for all strategies
        # based on strategy_entry_cycles and hold_days from strategy config.
        
        try:
            result = run_portfolio_cycle(
                config=cycle_config,
                research_engine=research_engine,
                artifact_store=artifact_store,
                execution_engine_factory=create_engine,
                state_store=state_store,
                cycle_id=cycle_id,
                execution_mode=ExecutionMode.SIMULATION,
                cycle_timestamp=cycle_timestamp,
                light_artifacts=light_artifacts
            )
            
            cycle_results.append(result)
            
            # Extract equity from result
            if result.summary:
                equity = result.summary.get("equity", INITIAL_CAPITAL)
                equity_series.append({
                    "date": cycle_timestamp.date().isoformat(),
                    "equity": equity,
                    "cycle_id": cycle_id
                })
                
                # Check for daily loss breach
                daily_loss = equity - INITIAL_CAPITAL
                daily_losses.append(daily_loss)
                if daily_loss <= -1000.0:
                    daily_loss_breaches += 1
            
            if result.status == "halted":
                print(f"🛑 HALTED at cycle {i+1}: {result.skip_reason}")
                break
                
        except Exception as e:
            print(f"❌ ERROR at cycle {i+1}: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    print()
    print("=" * 80)
    print(f"Backtest Complete for {instrument}")
    print("=" * 80)
    
    # Get trades from execution results
    # Note: Execution artifacts are always written (even in light_artifacts mode) because they're
    # required for final trade collection and metrics calculation.
    trades = []
    fill_ids_seen = set()
    
    # Extract fills from cycle results (preferred: in-memory execution_result)
    # This ensures determinism in --light-artifacts mode where artifacts may not be written
    for cycle_result in cycle_results:
        if cycle_result.execution_result is not None:
            # Extract fills from in-memory execution result
            for intent_result in cycle_result.execution_result.intent_results:
                if intent_result.fills:
                    for fill in intent_result.fills:
                        fill_id = fill.id
                        if fill_id and fill_id not in fill_ids_seen:
                            fill_ids_seen.add(fill_id)
                            trades.append(fill)
    
    # Fallback: If no in-memory execution results, try reading from artifacts (backward compatibility)
    # Note: In light_artifacts mode, we MUST use in-memory execution_result (artifacts not written)
    # Sorting ensures deterministic order if fallback is needed
    if not trades and not light_artifacts:
        exec_files = sorted(artifacts_dir.glob("runs/*_exec/rebalance_execution.json"))  # Sort for determinism
        for exec_file in exec_files:
            try:
                with open(exec_file) as f:
                    exec_dict = json.load(f)
                    if 'intent_results' in exec_dict:
                        for ir_dict in exec_dict['intent_results']:
                            if 'fills' in ir_dict and ir_dict['fills']:
                                for fill_dict in ir_dict['fills']:
                                    fill_id = fill_dict.get('id')
                                    if fill_id and fill_id not in fill_ids_seen:
                                        fill_ids_seen.add(fill_id)
                                        filled_at_str = fill_dict.get('filled_at')
                                        if isinstance(filled_at_str, str):
                                            filled_at = datetime.fromisoformat(filled_at_str.replace('Z', '+00:00'))
                                        else:
                                            filled_at = filled_at_str
                                        
                                        fill = Fill(
                                            id=fill_dict['id'],
                                            order_id=fill_dict['order_id'],
                                            instrument=fill_dict['instrument'],
                                            side=fill_dict['side'],
                                            quantity=fill_dict['quantity'],
                                            price=fill_dict['price'],
                                            fee=fill_dict.get('fee', 0.0),
                                            filled_at=filled_at,
                                            execution_id=fill_dict.get('execution_id')
                                        )
                                        trades.append(fill)
            except Exception as e:
                pass
    
    # Calculate trade metrics
    trade_metrics = calculate_trade_metrics(trades, instrument, INITIAL_CAPITAL)
    
    # Calculate max drawdown
    max_drawdown = 0.0
    peak_equity = INITIAL_CAPITAL
    for eq_data in equity_series:
        equity = eq_data["equity"]
        if equity > peak_equity:
            peak_equity = equity
        drawdown = peak_equity - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    max_drawdown_pct = (max_drawdown / INITIAL_CAPITAL) * 100.0
    
    # Check for single trade dominance
    round_trips = trade_metrics.get("round_trips", [])
    if round_trips:
        net_pnls = [rt["net_pnl"] for rt in round_trips]
        total_profit = sum(pnl for pnl in net_pnls if pnl > 0)
        if total_profit > 0:
            max_trade_profit = max(pnl for pnl in net_pnls if pnl > 0)
            single_trade_dominance = (max_trade_profit / total_profit) > 0.5
            dominant_trade_idx = next(i for i, pnl in enumerate(net_pnls) if pnl == max_trade_profit) if single_trade_dominance else None
        else:
            single_trade_dominance = False
            dominant_trade_idx = None
    else:
        single_trade_dominance = False
        dominant_trade_idx = None
    
    # Check execution cost impact
    gross_pnl = trade_metrics.get("gross_pnl", 0.0)
    net_pnl = trade_metrics.get("net_pnl", 0.0)
    execution_costs = trade_metrics.get("total_execution_costs", 0.0)
    execution_cost_impact = (execution_costs / abs(gross_pnl)) * 100.0 if gross_pnl != 0 else 0.0
    costs_materially_reduced = execution_costs > 0 and abs(execution_cost_impact) > 1.0
    
    results = {
        "instrument": instrument,
        "date_range": f"{START_DATE} to {END_DATE}",
        "trade_count": trade_metrics["trade_count"],
        "expectancy_per_trade": trade_metrics["expectancy_per_trade"],
        "win_rate": trade_metrics["win_rate"],
        "avg_win": trade_metrics["avg_win"],
        "avg_loss": trade_metrics["avg_loss"],
        "profit_factor": trade_metrics["profit_factor"],
        "net_pnl": net_pnl,
        "gross_pnl": gross_pnl,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
        "daily_loss_breaches": daily_loss_breaches,
        "daily_loss_breach_frequency_pct": (daily_loss_breaches / num_days) * 100.0 if num_days > 0 else 0.0,
        "total_execution_costs": execution_costs,
        "execution_cost_impact_pct": execution_cost_impact,
        "single_trade_dominance": single_trade_dominance,
        "dominant_trade_idx": dominant_trade_idx,
        "costs_materially_reduced": costs_materially_reduced,
        "anomalies": []
    }
    
    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run Layer 2 statistical backtest",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--light-artifacts",
        action="store_true",
        help="Skip per-cycle artifact writes for faster execution (keeps final summary only)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Override number of days to run (default: full date range)"
    )
    parser.add_argument(
        "--instruments",
        type=str,
        default=None,
        help="Comma-separated instruments to run (default: all)"
    )
    args = parser.parse_args()
    
    # Override instruments if specified
    instruments_to_run = INSTRUMENTS
    if args.instruments:
        instruments_to_run = [i.strip() for i in args.instruments.split(",")]
    
    all_results = {}
    
    for instrument in instruments_to_run:
        try:
            results = run_layer2_backtest_for_instrument(instrument, light_artifacts=args.light_artifacts, num_days_override=args.days)
            all_results[instrument] = results
            
            print(f"\n{instrument} Results:")
            print(f"  Trade Count: {results['trade_count']}")
            print(f"  Expectancy Per Trade: ${results['expectancy_per_trade']:,.2f}")
            print(f"  Win Rate: {results['win_rate']:.2%}")
            print(f"  Profit Factor: {results['profit_factor']:.2f}")
            print(f"  Net PnL: ${results['net_pnl']:,.2f}")
            print(f"  Max Drawdown: ${results['max_drawdown']:,.2f} ({results['max_drawdown_pct']:.2f}%)")
            print()
            
        except Exception as e:
            print(f"\n❌ FATAL ERROR for {instrument}: {e}")
            import traceback
            traceback.print_exc()
            all_results[instrument] = {"error": str(e)}
    
    # Save results
    results_path = Path("./LAYER2_BACKTEST_RESULTS.json")
    results_path.write_text(json.dumps(all_results, indent=2, default=str))
    
    # Print summary
    print("=" * 80)
    print("LAYER 2 RESULTS SUMMARY")
    print("=" * 80)
    
    for instrument in INSTRUMENTS:
        if instrument in all_results and "error" not in all_results[instrument]:
            r = all_results[instrument]
            print(f"\n{instrument}:")
            print(f"  Trade Count: {r['trade_count']}")
            print(f"  Expectancy: ${r['expectancy_per_trade']:,.2f}")
            print(f"  Profit Factor: {r['profit_factor']:.2f}")
            print(f"  Max Drawdown: {r['max_drawdown_pct']:.2f}%")
            print(f"  Daily Loss Breaches: {r['daily_loss_breaches']} ({r['daily_loss_breach_frequency_pct']:.2f}%)")
        else:
            print(f"\n{instrument}: ERROR")
    
    print(f"\nResults saved to: {results_path}")
    
    sys.exit(0)


if __name__ == "__main__":
    main()

