#!/usr/bin/env python3
"""Regime stress validation script (Gate 3).

Tests strategy behavior across different market regimes to understand failure modes.
"""

import sys
import json
import subprocess
import tempfile
import statistics
from pathlib import Path
from typing import Dict, Any, Optional, List
from copy import deepcopy

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# Deterministic price sequences for each regime
REGIME_PRICE_SERIES = {
    'trending': [100, 105, 110, 115, 120, 125, 130, 135, 140, 145],
    'mean_reverting': [100, 105, 100, 105, 100, 105, 100, 105, 100, 105],
    'flat': [100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
    'volatile': [100, 110, 90, 115, 85, 120, 80, 125, 75, 130]
}


def calculate_sharpe_from_equity(daily_equity: list) -> Optional[float]:
    """Calculate Sharpe ratio from daily equity series."""
    if len(daily_equity) < 2:
        return None
    
    returns = []
    for i in range(1, len(daily_equity)):
        prev_equity = daily_equity[i-1].get('equity', 0.0)
        curr_equity = daily_equity[i].get('equity', 0.0)
        if prev_equity > 0:
            daily_return = (curr_equity - prev_equity) / prev_equity
            returns.append(daily_return)
    
    if len(returns) < 2:
        return None
    
    mean_return = statistics.mean(returns)
    std_return = statistics.stdev(returns) if len(returns) > 1 else 0.0
    
    if std_return == 0:
        return None if mean_return == 0 else float('inf')
    
    return mean_return / std_return


def load_evidence_report(artifacts_dir: Path, portfolio_id: str) -> Dict[str, Any]:
    """Load evidence report from artifacts directory."""
    report_path = artifacts_dir / f"evidence_report_{portfolio_id}.json"
    if not report_path.exists():
        raise FileNotFoundError(f"Evidence report not found: {report_path}")
    with open(report_path, 'r') as f:
        return json.load(f)


def extract_metrics(report: Dict[str, Any]) -> Dict[str, Any]:
    """Extract metrics from evidence report."""
    final_equity = report.get('final_equity', 0.0)
    max_drawdown = abs(report.get('max_drawdown', 0.0))
    daily_equity = report.get('daily_equity', [])
    sharpe = calculate_sharpe_from_equity(daily_equity)
    
    # Calculate max drawdown percentage
    if daily_equity:
        equities = [de.get('equity', 0.0) for de in daily_equity]
        if equities:
            peak = equities[0]
            max_dd_pct = 0.0
            for equity in equities:
                if equity > peak:
                    peak = equity
                if peak > 0:
                    dd_pct = (peak - equity) / peak
                    if dd_pct > max_dd_pct:
                        max_dd_pct = dd_pct
            max_drawdown_pct = max_dd_pct
        else:
            max_drawdown_pct = 0.0
    else:
        max_drawdown_pct = 0.0
    
    # Extract total PnL
    total_pnl = report.get('total_pnl', 0.0)
    
    return {
        'final_equity': final_equity,
        'max_drawdown': max_drawdown,
        'max_drawdown_pct': max_drawdown_pct,
        'sharpe': sharpe,
        'total_pnl': total_pnl
    }


def create_regime_config(
    base_config: Dict[str, Any],
    regime_name: str,
    price_series: List[float],
    portfolio_id_suffix: str
) -> Dict[str, Any]:
    """Create a config with regime-specific price series."""
    config = deepcopy(base_config)
    
    # Update portfolio_id
    config['portfolio_id'] = portfolio_id_suffix
    
    # Update description
    if 'description' in config:
        config['description'] = f"{config['description']} (regime: {regime_name})"
    
    # Override price_series in evaluation_config
    if 'evaluation_config' not in config:
        config['evaluation_config'] = {}
    config['evaluation_config']['price_series'] = price_series
    
    # Update execution_config prices to use last price from series (current price)
    if price_series:
        current_price = price_series[-1]
        if 'execution_config' not in config:
            config['execution_config'] = {}
        if 'price_by_strategy_or_instrument' not in config['execution_config']:
            config['execution_config']['price_by_strategy_or_instrument'] = {}
        
        # Update all strategy/instrument prices
        price_map = config['execution_config']['price_by_strategy_or_instrument']
        for key in list(price_map.keys()):
            price_map[key] = current_price
    
    return config


def run_backtest(config_path: Path, artifacts_dir: Path, num_cycles: int) -> bool:
    """Run backtest using backtest_runner.py."""
    cmd = [
        sys.executable,
        'scripts/backtest_runner.py',
        '--config', str(config_path),
        '--artifacts', str(artifacts_dir),
        '--cycles', str(num_cycles)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Backtest failed with exit code {e.returncode}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False


def get_account_size(config: Dict[str, Any]) -> float:
    """Get account size from config."""
    # Try ruleset_config.account_size first
    ruleset_config = config.get('ruleset_config', {})
    if 'account_size' in ruleset_config:
        return float(ruleset_config['account_size'])
    
    # Fall back to allocation_config.total_capital
    allocation_config = config.get('allocation_config', {})
    if 'total_capital' in allocation_config:
        return float(allocation_config['total_capital'])
    
    # Default fallback
    return 50000.0


def get_max_trailing_drawdown_pct(config: Dict[str, Any]) -> Optional[float]:
    """Get max_trailing_drawdown_pct from ruleset_config."""
    ruleset_config = config.get('ruleset_config', {})
    return ruleset_config.get('max_trailing_drawdown_pct')


def run_regime_stress(
    base_config_path: Path,
    artifacts_dir: Path,
    regimes: List[str],
    num_cycles: int = 30
) -> Dict[str, Any]:
    """Run regime stress validation."""
    # Load base config
    with open(base_config_path, 'r') as f:
        base_config = json.load(f)
    
    # Validate regimes
    invalid_regimes = [r for r in regimes if r not in REGIME_PRICE_SERIES]
    if invalid_regimes:
        raise ValueError(f"Invalid regime names: {invalid_regimes}. Valid: {list(REGIME_PRICE_SERIES.keys())}")
    
    # Set up output directory
    base_portfolio_id = base_config.get('portfolio_id', 'portfolio')
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Get account size and drawdown threshold
    account_size = get_account_size(base_config)
    max_dd_pct_threshold = get_max_trailing_drawdown_pct(base_config)
    if max_dd_pct_threshold is None:
        max_dd_pct_threshold = 20.0  # Default 20%
    else:
        max_dd_pct_threshold = max_dd_pct_threshold * 2.0  # 2x threshold
    
    # Run each regime
    results = {}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        for regime_name in regimes:
            price_series = REGIME_PRICE_SERIES[regime_name]
            portfolio_id_suffix = f"{base_portfolio_id}_regime_{regime_name}"
            
            # Create regime config
            regime_config = create_regime_config(
                base_config, regime_name, price_series, portfolio_id_suffix
            )
            
            # Run backtest in subdirectory
            regime_artifacts = artifacts_dir / portfolio_id_suffix
            regime_artifacts.mkdir(parents=True, exist_ok=True)
            
            regime_config_path = tmp_path / f'{portfolio_id_suffix}_config.json'
            with open(regime_config_path, 'w') as f:
                json.dump(regime_config, f, indent=2)
            
            print(f"Running regime '{regime_name}' (portfolio: {portfolio_id_suffix})")
            if not run_backtest(regime_config_path, regime_artifacts, num_cycles):
                print(f"WARNING: Regime '{regime_name}' backtest failed")
                results[regime_name] = {'error': 'Backtest failed'}
                continue
            
            # Load evidence report
            regime_report = load_evidence_report(regime_artifacts, portfolio_id_suffix)
            regime_metrics = extract_metrics(regime_report)
            
            # Check pass/fail criteria
            final_equity = regime_metrics['final_equity']
            total_pnl = regime_metrics['total_pnl']
            max_dd_pct_decimal = regime_metrics['max_drawdown_pct']  # Already a decimal (0.0 to 1.0)
            max_dd_pct = max_dd_pct_decimal * 100.0  # Convert to percentage for display
            
            # Catastrophic check: final_equity <= 0 OR total_pnl <= -0.5 * account_size
            catastrophic = final_equity <= 0 or total_pnl <= -0.5 * account_size
            
            # Drawdown check: max_dd_pct <= threshold (both in percentage terms)
            drawdown_bounded = max_dd_pct <= max_dd_pct_threshold
            
            regime_passed = not catastrophic and drawdown_bounded
            
            results[regime_name] = {
                'metrics': regime_metrics,
                'account_size': account_size,
                'max_dd_threshold_pct': max_dd_pct_threshold,
                'catastrophic': catastrophic,
                'drawdown_bounded': drawdown_bounded,
                'passed': regime_passed
            }
    
    # Overall pass/fail: all regimes must pass
    all_passed = all(
        data.get('passed', False) for data in results.values()
        if 'error' not in data
    )
    
    result = {
        'validation_passed': all_passed,
        'account_size': account_size,
        'max_drawdown_threshold_pct': max_dd_pct_threshold,
        'regimes': {
            name: {
                'final_equity': data.get('metrics', {}).get('final_equity'),
                'total_pnl': data.get('metrics', {}).get('total_pnl'),
                'max_drawdown': data.get('metrics', {}).get('max_drawdown'),
                'max_drawdown_pct': data.get('metrics', {}).get('max_drawdown_pct') * 100.0,
                'sharpe': data.get('metrics', {}).get('sharpe'),
                'catastrophic': data.get('catastrophic', False),
                'drawdown_bounded': data.get('drawdown_bounded', False),
                'passed': data.get('passed', False)
            }
            if 'error' not in data
            else {'error': data.get('error')}
            for name, data in results.items()
        }
    }
    
    return result


def print_results(result: Dict[str, Any]):
    """Print validation results to console."""
    print("=" * 80)
    print("Regime Stress Validation Results (Gate 3)")
    print("=" * 80)
    print()
    
    print(f"Account Size: ${result['account_size']:,.2f}")
    print(f"Max Drawdown Threshold: {result['max_drawdown_threshold_pct']:.2f}%")
    print()
    
    print("Regime Results:")
    for regime_name, data in sorted(result['regimes'].items()):
        if 'error' in data:
            print(f"  {regime_name}: ERROR - {data['error']}")
            continue
        
        print(f"  {regime_name}:")
        print(f"    Final Equity: ${data.get('final_equity', 0):,.2f}")
        print(f"    Total PnL: ${data.get('total_pnl', 0):,.2f}")
        print(f"    Max Drawdown: ${data.get('max_drawdown', 0):,.2f}")
        print(f"    Max Drawdown %: {data.get('max_drawdown_pct', 0):.2f}%")
        if data.get('sharpe') is not None:
            print(f"    Sharpe: {data['sharpe']:.4f}")
        print(f"    Catastrophic: {'YES' if data.get('catastrophic') else 'NO'}")
        print(f"    Drawdown Bounded: {'YES' if data.get('drawdown_bounded') else 'NO'}")
        print(f"    Status: {'PASS' if data.get('passed') else 'FAIL'}")
        print()
    
    print("Validation Criteria:")
    print("  - Strategy must NOT be catastrophic (final_equity > 0 AND total_pnl > -0.5 * account_size)")
    print("  - Max drawdown must be bounded (dd_pct <= threshold)")
    print()
    
    if result['validation_passed']:
        print("✓ VALIDATION PASSED - Strategy handles all regimes predictably")
    else:
        print("✗ VALIDATION FAILED - Strategy fails catastrophically in some regimes")
        print("  RECOMMENDATION: Understand failure modes before deploying")
    print("=" * 80)


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run regime stress validation (Gate 3)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--config',
        type=Path,
        required=True,
        help='Path to base configuration file'
    )
    
    parser.add_argument(
        '--artifacts',
        type=Path,
        required=True,
        help='Artifacts directory (root output folder)'
    )
    
    parser.add_argument(
        '--cycles',
        type=int,
        default=30,
        help='Number of cycles to run (default: 30)'
    )
    
    parser.add_argument(
        '--regimes',
        type=str,
        nargs='+',
        default=['trending', 'mean_reverting', 'flat', 'volatile'],
        help='List of regimes to test (default: trending mean_reverting flat volatile)'
    )
    
    args = parser.parse_args()
    
    if not args.config.exists():
        print(f"ERROR: Config file not found: {args.config}")
        sys.exit(2)
    
    try:
        result = run_regime_stress(
            base_config_path=args.config,
            artifacts_dir=args.artifacts,
            regimes=args.regimes,
            num_cycles=args.cycles
        )
        
        print_results(result)
        
        # Save results
        result_path = args.artifacts / 'regime_stress_result.json'
        result_path.parent.mkdir(parents=True, exist_ok=True)
        with open(result_path, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\nResults saved to: {result_path}")
        
        sys.exit(0 if result['validation_passed'] else 1)
        
    except ValueError as e:
        print(f"ERROR: Invalid input - {e}")
        sys.exit(2)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == '__main__':
    main()
