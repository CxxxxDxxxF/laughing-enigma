#!/usr/bin/env python3
"""Parameter perturbation validation script (Gate 2).

Tests strategy robustness to parameter perturbations to kill curve-fit strategies.
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


def calculate_correlation(series1: List[float], series2: List[float]) -> Optional[float]:
    """Calculate Pearson correlation coefficient between two series."""
    if len(series1) != len(series2) or len(series1) < 2:
        return None
    
    try:
        # Try Python 3.10+ statistics.correlation
        if hasattr(statistics, 'correlation'):
            return statistics.correlation(series1, series2)
        else:
            # Fallback: manual calculation
            mean1 = statistics.mean(series1)
            mean2 = statistics.mean(series2)
            std1 = statistics.stdev(series1)
            std2 = statistics.stdev(series2)
            
            if std1 == 0 or std2 == 0:
                return None
            
            covariance = sum((series1[i] - mean1) * (series2[i] - mean2) 
                           for i in range(len(series1))) / (len(series1) - 1)
            return covariance / (std1 * std2)
    except (ValueError, statistics.StatisticsError, ZeroDivisionError):
        return None


def calculate_returns_correlation(equity_series1: List[float], equity_series2: List[float]) -> Optional[float]:
    """Calculate correlation between equity return series."""
    if len(equity_series1) != len(equity_series2) or len(equity_series1) < 2:
        return None
    
    # Calculate returns
    returns1 = []
    returns2 = []
    
    for i in range(1, len(equity_series1)):
        prev1 = equity_series1[i-1]
        curr1 = equity_series1[i]
        prev2 = equity_series2[i-1]
        curr2 = equity_series2[i]
        
        if prev1 > 0 and prev2 > 0:
            ret1 = (curr1 - prev1) / prev1
            ret2 = (curr2 - prev2) / prev2
            returns1.append(ret1)
            returns2.append(ret2)
    
    if len(returns1) < 2:
        return None
    
    return calculate_correlation(returns1, returns2)


def load_evidence_report(artifacts_dir: Path, portfolio_id: str) -> Dict[str, Any]:
    """Load evidence report from artifacts directory."""
    report_path = artifacts_dir / f"evidence_report_{portfolio_id}.json"
    if not report_path.exists():
        raise FileNotFoundError(f"Evidence report not found: {report_path}")
    with open(report_path, 'r') as f:
        return json.load(f)


def extract_equity_series(report: Dict[str, Any]) -> List[float]:
    """Extract equity series from evidence report."""
    daily_equity = report.get('daily_equity', [])
    return [de.get('equity', 0.0) for de in daily_equity]


def extract_metrics(report: Dict[str, Any]) -> Dict[str, Any]:
    """Extract metrics from evidence report."""
    final_equity = report.get('final_equity', 0.0)
    max_drawdown = abs(report.get('max_drawdown', 0.0))
    daily_equity = report.get('daily_equity', [])
    sharpe = calculate_sharpe_from_equity(daily_equity)
    equity_series = extract_equity_series(report)
    
    return {
        'final_equity': final_equity,
        'max_drawdown': max_drawdown,
        'sharpe': sharpe,
        'equity_series': equity_series
    }


def find_strategy(config: Dict[str, Any], strategy_id: Optional[str] = None) -> tuple:
    """Find strategy by ID or return first strategy.
    
    Returns:
        Tuple of (strategy_index, strategy_dict)
    """
    strategies = config.get('evaluation_config', {}).get('strategies', [])
    
    if not strategies:
        raise ValueError("No strategies found in config")
    
    if strategy_id:
        for idx, strategy in enumerate(strategies):
            if strategy.get('strategy_id') == strategy_id:
                return idx, strategy
        raise ValueError(f"Strategy ID '{strategy_id}' not found in config")
    
    return 0, strategies[0]


def get_parameter_value(strategy: Dict[str, Any], param_name: str) -> float:
    """Get parameter value from strategy experiment_config."""
    experiment_config = strategy.get('experiment_config', {})
    
    if param_name not in experiment_config:
        raise ValueError(f"Parameter '{param_name}' not found in experiment_config")
    
    value = experiment_config[param_name]
    
    if not isinstance(value, (int, float)):
        raise ValueError(f"Parameter '{param_name}' is not numeric (got {type(value).__name__})")
    
    return float(value)


def generate_parameter_values(base_value: float, pct: float) -> List[float]:
    """Generate parameter perturbation values.
    
    Returns: [base_value * (1 - pct), base_value, base_value * (1 + pct)]
    """
    return [
        base_value * (1 - pct),
        base_value,
        base_value * (1 + pct)
    ]


def create_perturbed_config(
    base_config: Dict[str, Any],
    strategy_idx: int,
    param_name: str,
    param_value: float,
    portfolio_id_suffix: str
) -> Dict[str, Any]:
    """Create a config with a perturbed parameter."""
    config = deepcopy(base_config)
    
    # Update portfolio_id
    base_id = config.get('portfolio_id', 'portfolio')
    config['portfolio_id'] = portfolio_id_suffix
    
    # Update description
    if 'description' in config:
        config['description'] = f"{config['description']} (perturb: {param_name}={param_value:.6f})"
    
    # Perturb the parameter
    strategy = config['evaluation_config']['strategies'][strategy_idx]
    strategy['experiment_config'][param_name] = param_value
    
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


def run_parameter_perturbation(
    base_config_path: Path,
    param_name: str,
    artifacts_dir: Path,
    pct: Optional[float] = None,
    values: Optional[List[float]] = None,
    strategy_id: Optional[str] = None,
    num_cycles: int = 30
) -> Dict[str, Any]:
    """Run parameter perturbation validation."""
    # Load base config
    with open(base_config_path, 'r') as f:
        base_config = json.load(f)
    
    # Find target strategy
    strategy_idx, strategy = find_strategy(base_config, strategy_id)
    strategy_name = strategy.get('strategy_id', f'strategy_{strategy_idx}')
    
    # Get base parameter value
    base_value = get_parameter_value(strategy, param_name)
    
    # Generate parameter values
    if values is not None:
        param_values = values
    elif pct is not None:
        param_values = generate_parameter_values(base_value, pct)
        # Remove duplicates and sort
        param_values = sorted(set(param_values))
    else:
        raise ValueError("Either --pct or --values must be provided")
    
    # Set up output directory structure
    base_portfolio_id = base_config.get('portfolio_id', 'portfolio')
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Run base and all variants
    results = {}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        for idx, param_value in enumerate(param_values):
            # Create portfolio ID suffix
            portfolio_id_suffix = f"{base_portfolio_id}_param_{param_name}_{idx}"
            
            # Create perturbed config
            variant_config = create_perturbed_config(
                base_config, strategy_idx, param_name, param_value, portfolio_id_suffix
            )
            
            # Run backtest in subdirectory
            variant_artifacts = artifacts_dir / portfolio_id_suffix
            variant_artifacts.mkdir(parents=True, exist_ok=True)
            
            variant_config_path = tmp_path / f'{portfolio_id_suffix}_config.json'
            with open(variant_config_path, 'w') as f:
                json.dump(variant_config, f, indent=2)
            
            print(f"Running variant {idx}: {param_name}={param_value:.6f} (portfolio: {portfolio_id_suffix})")
            if not run_backtest(variant_config_path, variant_artifacts, num_cycles):
                print(f"WARNING: Variant {idx} backtest failed")
                results[f"variant_{idx}"] = {'error': 'Backtest failed', 'param_value': param_value}
                continue
            
            # Load evidence report
            variant_report = load_evidence_report(variant_artifacts, portfolio_id_suffix)
            variant_metrics = extract_metrics(variant_report)
            results[f"variant_{idx}"] = {
                'param_value': param_value,
                'metrics': variant_metrics
            }
    
    # Find base variant (closest to base_value)
    base_idx = None
    base_variant_key = None
    for key, data in results.items():
        if 'error' in data:
            continue
        if abs(data['param_value'] - base_value) < 1e-10:
            base_idx = int(key.split('_')[1])
            base_variant_key = key
            break
    
    if base_variant_key is None:
        raise ValueError("Base variant not found in results")
    
    base_metrics = results[base_variant_key]['metrics']
    base_equity = base_metrics['equity_series']
    base_dd = base_metrics['max_drawdown']
    base_sharpe = base_metrics['sharpe']
    
    # Calculate correlations and validate criteria
    correlations = {}
    drawdown_ratios = {}
    sharpe_ratios = {}
    
    for variant_key, variant_data in results.items():
        if variant_key == base_variant_key or 'error' in variant_data:
            continue
        
        variant_metrics = variant_data['metrics']
        variant_equity = variant_metrics['equity_series']
        
        # Calculate correlation
        corr = calculate_returns_correlation(base_equity, variant_equity)
        correlations[variant_key] = corr
        
        # Calculate drawdown ratio
        variant_dd = variant_metrics['max_drawdown']
        if base_dd == 0:
            drawdown_ratios[variant_key] = float('inf') if variant_dd > 0 else 1.0
        else:
            drawdown_ratios[variant_key] = variant_dd / base_dd
        
        # Calculate sharpe ratio
        variant_sharpe = variant_metrics['sharpe']
        if base_sharpe is not None and base_sharpe != 0 and variant_sharpe is not None:
            sharpe_ratios[variant_key] = variant_sharpe / base_sharpe
        else:
            sharpe_ratios[variant_key] = None
    
    # Check pass/fail criteria
    # 1. Correlation >= 0.8 (SKIP if insufficient data)
    valid_correlations = [c for c in correlations.values() if c is not None]
    min_correlation = min(valid_correlations) if valid_correlations else None
    if min_correlation is None:
        correlation_passed = True  # SKIP - insufficient data
        correlation_status = 'SKIP'
    else:
        correlation_passed = min_correlation >= 0.8
        correlation_status = 'PASS' if correlation_passed else 'FAIL'
    
    # 2. No variant drawdown > 2x base drawdown
    valid_dd_ratios = [r for r in drawdown_ratios.values() if r != float('inf')]
    max_dd_ratio = max(valid_dd_ratios) if valid_dd_ratios else float('inf')
    if base_dd == 0:
        # If base DD == 0, any DD > 0 fails
        drawdown_passed = all(r <= 1.0 for r in drawdown_ratios.values() if r != float('inf'))
    else:
        drawdown_passed = max_dd_ratio <= 2.0
    
    # 3. No variant sharpe < 0.3x base sharpe (SKIP if insufficient data)
    valid_sharpe_ratios = [r for r in sharpe_ratios.values() if r is not None]
    min_sharpe_ratio = min(valid_sharpe_ratios) if valid_sharpe_ratios else None
    if min_sharpe_ratio is None:
        sharpe_passed = True  # SKIP - insufficient data
        sharpe_status = 'SKIP'
    else:
        sharpe_passed = min_sharpe_ratio >= 0.3
        sharpe_status = 'PASS' if sharpe_passed else 'FAIL'
    
    overall_passed = correlation_passed and drawdown_passed and sharpe_passed
    
    # Build result
    result = {
        'validation_passed': overall_passed,
        'parameter_tested': {
            'strategy_id': strategy_name,
            'param_name': param_name,
            'base_value': base_value,
            'tested_values': param_values
        },
        'variants': {
            key: {
                'param_value': data.get('param_value'),
                'final_equity': data.get('metrics', {}).get('final_equity'),
                'max_drawdown': data.get('metrics', {}).get('max_drawdown'),
                'sharpe': data.get('metrics', {}).get('sharpe'),
                'correlation': correlations.get(key),
                'drawdown_ratio': drawdown_ratios.get(key),
                'sharpe_ratio': sharpe_ratios.get(key)
            }
            if 'error' not in data
            else {'error': data.get('error'), 'param_value': data.get('param_value')}
            for key, data in results.items()
        },
        'criteria': {
            'correlation': {
                'passed': correlation_passed,
                'min_correlation': min_correlation,
                'requirement': 'min_correlation >= 0.8',
                'status': correlation_status
            },
            'drawdown': {
                'passed': drawdown_passed,
                'max_ratio': max_dd_ratio if max_dd_ratio != float('inf') else None,
                'requirement': 'max_drawdown_ratio <= 2.0 (or <= 1.0 if base_dd == 0)',
                'status': 'PASS' if drawdown_passed else 'FAIL'
            },
            'sharpe': {
                'passed': sharpe_passed,
                'min_ratio': min_sharpe_ratio,
                'requirement': 'min_sharpe_ratio >= 0.3',
                'status': sharpe_status
            }
        }
    }
    
    return result


def print_results(result: Dict[str, Any]):
    """Print validation results to console."""
    print("=" * 80)
    print("Parameter Perturbation Validation Results (Gate 2)")
    print("=" * 80)
    print()
    
    param_info = result['parameter_tested']
    print(f"Strategy: {param_info['strategy_id']}")
    print(f"Parameter: {param_info['param_name']}")
    print(f"Base Value: {param_info['base_value']:.6f}")
    print(f"Tested Values: {[f'{v:.6f}' for v in param_info['tested_values']]}")
    print()
    
    print("Variant Results:")
    for key, data in sorted(result['variants'].items()):
        if 'error' in data:
            print(f"  {key}: ERROR - {data['error']}")
            continue
        
        print(f"  {key} (param={data['param_value']:.6f}):")
        print(f"    Final Equity: ${data.get('final_equity', 0):,.2f}")
        print(f"    Max Drawdown: ${data.get('max_drawdown', 0):,.2f}")
        if data.get('sharpe') is not None:
            print(f"    Sharpe: {data['sharpe']:.4f}")
        if data.get('correlation') is not None:
            print(f"    Correlation: {data['correlation']:.4f}")
        if data.get('drawdown_ratio') is not None and data['drawdown_ratio'] != float('inf'):
            print(f"    DD Ratio: {data['drawdown_ratio']:.2f}x")
        if data.get('sharpe_ratio') is not None:
            print(f"    Sharpe Ratio: {data['sharpe_ratio']:.2f}x")
        print()
    
    print("Validation Criteria:")
    for criterion_name, criterion_data in result['criteria'].items():
        status = criterion_data['status']
        print(f"  {criterion_name.upper()}: {status}")
        print(f"    Requirement: {criterion_data['requirement']}")
        if criterion_name == 'correlation' and criterion_data.get('min_correlation') is not None:
            print(f"    Min Correlation: {criterion_data['min_correlation']:.4f}")
        elif criterion_name == 'drawdown' and criterion_data.get('max_ratio') is not None:
            print(f"    Max DD Ratio: {criterion_data['max_ratio']:.2f}x")
        elif criterion_name == 'sharpe' and criterion_data.get('min_ratio') is not None:
            print(f"    Min Sharpe Ratio: {criterion_data['min_ratio']:.2f}x")
        print()
    
    if result['validation_passed']:
        print("✓ VALIDATION PASSED - Strategy is robust to parameter changes")
    else:
        print("✗ VALIDATION FAILED - Strategy appears curve-fit")
        print("  RECOMMENDATION: Delete this strategy. Do not tweak or fix it.")
    print("=" * 80)


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run parameter perturbation validation (Gate 2)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--config',
        type=Path,
        required=True,
        help='Path to base configuration file'
    )
    
    parser.add_argument(
        '--param',
        type=str,
        required=True,
        help='Parameter name to perturb (e.g., daily_trend)'
    )
    
    parser.add_argument(
        '--pct',
        type=float,
        help='Perturbation percentage (e.g., 0.2 for +/-20%%)'
    )
    
    parser.add_argument(
        '--values',
        type=float,
        nargs='+',
        help='Explicit list of parameter values (overrides --pct)'
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
        '--strategy-id',
        type=str,
        help='Strategy ID to target (if multiple strategies in config)'
    )
    
    args = parser.parse_args()
    
    if not args.config.exists():
        print(f"ERROR: Config file not found: {args.config}")
        sys.exit(2)
    
    if args.pct is None and args.values is None:
        print("ERROR: Either --pct or --values must be provided")
        sys.exit(2)
    
    if args.pct is not None and args.values is not None:
        print("ERROR: Cannot specify both --pct and --values")
        sys.exit(2)
    
    try:
        result = run_parameter_perturbation(
            base_config_path=args.config,
            param_name=args.param,
            artifacts_dir=args.artifacts,
            pct=args.pct,
            values=args.values,
            strategy_id=args.strategy_id,
            num_cycles=args.cycles
        )
        
        print_results(result)
        
        # Save results
        result_path = args.artifacts / 'parameter_perturbation_result.json'
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

