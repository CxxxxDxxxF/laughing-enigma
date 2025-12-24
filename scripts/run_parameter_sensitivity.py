#!/usr/bin/env python3
"""Parameter sensitivity validation script (Gate 2).

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
    
    return {
        'final_equity': final_equity,
        'max_drawdown': max_drawdown,
        'sharpe': sharpe,
        'equity_series': extract_equity_series(report)
    }


def identify_numeric_parameters(config: Dict[str, Any]) -> List[tuple]:
    """Identify numeric parameters in experiment_config for all strategies.
    
    Returns:
        List of tuples: (strategy_index, param_name, param_value)
    """
    parameters = []
    strategies = config.get('evaluation_config', {}).get('strategies', [])
    
    for idx, strategy in enumerate(strategies):
        experiment_config = strategy.get('experiment_config', {})
        for param_name, param_value in experiment_config.items():
            if isinstance(param_value, (int, float)) and param_value != 0:
                parameters.append((idx, param_name, param_value))
    
    return parameters


def generate_perturbations(base_value: float, perturbation_pct: float = 0.15) -> List[float]:
    """Generate parameter perturbations.
    
    Creates: [-20%, -10%, base, +10%, +20%] if base != 0
    Or: [-perturbation_pct, base, +perturbation_pct] scaled appropriately
    """
    if base_value == 0:
        return [base_value]  # Cannot perturb zero
    
    # Generate ±10% and ±20% perturbations
    perturbations = [
        base_value * 0.8,   # -20%
        base_value * 0.9,   # -10%
        base_value,         # base
        base_value * 1.1,   # +10%
        base_value * 1.2,   # +20%
    ]
    
    # Remove duplicates and sort
    unique = sorted(set(perturbations))
    return unique


def create_perturbed_config(
    base_config: Dict[str, Any],
    strategy_idx: int,
    param_name: str,
    param_value: float,
    variant_name: str
) -> Dict[str, Any]:
    """Create a config with a perturbed parameter."""
    config = deepcopy(base_config)
    
    # Update portfolio_id
    base_id = config.get('portfolio_id', 'portfolio')
    config['portfolio_id'] = f"{base_id}_perturb_{variant_name}"
    
    # Update description
    if 'description' in config:
        config['description'] = f"{config['description']} (perturb: {param_name}={param_value:.6f})"
    
    # Perturb the parameter
    strategy = config['evaluation_config']['strategies'][strategy_idx]
    strategy['experiment_config'][param_name] = param_value
    
    return config


def run_backtest(config_path: Path, artifacts_dir: Path, num_cycles: int = 30) -> bool:
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
        return False


def run_parameter_sensitivity(
    base_config_path: Path,
    output_dir: Optional[Path] = None,
    perturbation_pct: float = 0.15,
    num_cycles: int = 30
) -> Dict[str, Any]:
    """Run parameter sensitivity validation."""
    # Load base config
    with open(base_config_path, 'r') as f:
        base_config = json.load(f)
    
    # Identify parameters to perturb
    parameters = identify_numeric_parameters(base_config)
    
    if not parameters:
        raise ValueError("No numeric parameters found in experiment_config to perturb")
    
    # Use first strategy's first parameter (can be extended later)
    strategy_idx, param_name, base_value = parameters[0]
    
    # Generate perturbations
    perturbations = generate_perturbations(base_value, perturbation_pct)
    
    # Set output directory
    if output_dir is None:
        output_dir = Path('./artifacts_parameter_sensitivity')
    
    # Run base and all variants
    results = {}
    base_portfolio_id = base_config.get('portfolio_id', 'portfolio')
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Run base variant
        base_artifacts = output_dir / 'base'
        base_artifacts.mkdir(parents=True, exist_ok=True)
        
        base_config_path_tmp = tmp_path / 'base_config.json'
        with open(base_config_path_tmp, 'w') as f:
            json.dump(base_config, f, indent=2)
        
        print(f"Running base variant: {param_name}={base_value:.6f}")
        if not run_backtest(base_config_path_tmp, base_artifacts, num_cycles):
            raise RuntimeError("Base backtest failed")
        
        base_report = load_evidence_report(base_artifacts, base_portfolio_id)
        base_metrics = extract_metrics(base_report)
        results['base'] = {
            'param_value': base_value,
            'metrics': base_metrics
        }
        
        # Run perturbed variants
        for i, perturbed_value in enumerate(perturbations):
            if perturbed_value == base_value:
                continue  # Skip base (already run)
            
            variant_name = f"{param_name}_{i}"
            variant_config = create_perturbed_config(
                base_config, strategy_idx, param_name, perturbed_value, variant_name
            )
            
            variant_portfolio_id = variant_config['portfolio_id']
            variant_artifacts = output_dir / variant_name
            variant_artifacts.mkdir(parents=True, exist_ok=True)
            
            variant_config_path = tmp_path / f'{variant_name}_config.json'
            with open(variant_config_path, 'w') as f:
                json.dump(variant_config, f, indent=2)
            
            print(f"Running variant {variant_name}: {param_name}={perturbed_value:.6f}")
            if not run_backtest(variant_config_path, variant_artifacts, num_cycles):
                print(f"WARNING: Variant {variant_name} backtest failed")
                continue
            
            variant_report = load_evidence_report(variant_artifacts, variant_portfolio_id)
            variant_metrics = extract_metrics(variant_report)
            results[variant_name] = {
                'param_value': perturbed_value,
                'metrics': variant_metrics
            }
    
    # Calculate correlations and validate criteria
    base_equity = results['base']['metrics']['equity_series']
    correlations = {}
    drawdown_ratios = {}
    
    for variant_name, variant_data in results.items():
        if variant_name == 'base':
            continue
        
        variant_equity = variant_data['metrics']['equity_series']
        corr = calculate_correlation(base_equity, variant_equity)
        correlations[variant_name] = corr
        
        base_dd = results['base']['metrics']['max_drawdown']
        variant_dd = variant_data['metrics']['max_drawdown']
        if base_dd > 0:
            drawdown_ratios[variant_name] = variant_dd / base_dd
        else:
            drawdown_ratios[variant_name] = float('inf') if variant_dd > 0 else 1.0
    
    # Check pass/fail criteria
    min_correlation = min(c for c in correlations.values() if c is not None)
    max_dd_ratio = max(dd for dd in drawdown_ratios.values() if dd != float('inf'))
    
    correlation_passed = min_correlation is not None and min_correlation > 0.8
    drawdown_passed = max_dd_ratio <= 2.0  # No variant should have >2x base drawdown
    
    overall_passed = correlation_passed and drawdown_passed
    
    # Build result
    result = {
        'validation_passed': overall_passed,
        'parameter_tested': {
            'strategy_index': strategy_idx,
            'param_name': param_name,
            'base_value': base_value,
            'perturbations': perturbations
        },
        'variants': {
            name: {
                'param_value': data['param_value'],
                'final_equity': data['metrics']['final_equity'],
                'max_drawdown': data['metrics']['max_drawdown'],
                'sharpe': data['metrics']['sharpe'],
                'correlation': correlations.get(name),
                'drawdown_ratio': drawdown_ratios.get(name)
            }
            for name, data in results.items()
        },
        'criteria': {
            'correlation': {
                'passed': correlation_passed,
                'min_correlation': min_correlation,
                'requirement': 'min_correlation > 0.8'
            },
            'drawdown': {
                'passed': drawdown_passed,
                'max_ratio': max_dd_ratio,
                'requirement': 'max_drawdown_ratio <= 2.0'
            }
        }
    }
    
    return result


def print_results(result: Dict[str, Any]):
    """Print validation results to console."""
    print("=" * 80)
    print("Parameter Sensitivity Validation Results (Gate 2)")
    print("=" * 80)
    print()
    
    param_info = result['parameter_tested']
    print(f"Parameter Tested: {param_info['param_name']}")
    print(f"Base Value: {param_info['base_value']:.6f}")
    print(f"Perturbations: {[f'{v:.6f}' for v in param_info['perturbations']]}")
    print()
    
    print("Variant Results:")
    for name, data in result['variants'].items():
        print(f"  {name}:")
        print(f"    Parameter Value: {data['param_value']:.6f}")
        print(f"    Final Equity: ${data['final_equity']:,.2f}")
        print(f"    Max Drawdown: ${data['max_drawdown']:,.2f}")
        if data.get('sharpe') is not None:
            print(f"    Sharpe: {data['sharpe']:.4f}")
        if data.get('correlation') is not None:
            print(f"    Correlation: {data['correlation']:.4f}")
        if data.get('drawdown_ratio') is not None:
            print(f"    DD Ratio: {data['drawdown_ratio']:.2f}x")
        print()
    
    print("Validation Criteria:")
    corr_criteria = result['criteria']['correlation']
    print(f"  Correlation: {corr_criteria['min_correlation']:.4f}")
    print(f"    Requirement: {corr_criteria['requirement']}")
    print(f"    Status: {'PASS' if corr_criteria['passed'] else 'FAIL'}")
    
    dd_criteria = result['criteria']['drawdown']
    print(f"  Drawdown: {dd_criteria['max_ratio']:.2f}x")
    print(f"    Requirement: {dd_criteria['requirement']}")
    print(f"    Status: {'PASS' if dd_criteria['passed'] else 'FAIL'}")
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
        description="Run parameter sensitivity validation (Gate 2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run parameter sensitivity test
  python scripts/run_parameter_sensitivity.py --config configs/backtest/topstep_50k_backtest.json
        """
    )
    
    parser.add_argument(
        '--config',
        type=Path,
        required=True,
        help='Path to base configuration file'
    )
    
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('./artifacts_parameter_sensitivity'),
        help='Output directory for artifacts (default: ./artifacts_parameter_sensitivity)'
    )
    
    parser.add_argument(
        '--perturbation-pct',
        type=float,
        default=0.15,
        help='Perturbation percentage (default: 0.15, creates +/-10%% and +/-20%%)'
    )
    
    parser.add_argument(
        '--cycles',
        type=int,
        default=30,
        help='Number of cycles to run per variant (default: 30)'
    )
    
    args = parser.parse_args()
    
    if not args.config.exists():
        print(f"ERROR: Config file not found: {args.config}")
        sys.exit(1)
    
    try:
        result = run_parameter_sensitivity(
            base_config_path=args.config,
            output_dir=args.output_dir,
            perturbation_pct=args.perturbation_pct,
            num_cycles=args.cycles
        )
        
        print_results(result)
        
        # Save results
        result_path = args.output_dir / 'parameter_sensitivity_result.json'
        result_path.parent.mkdir(parents=True, exist_ok=True)
        with open(result_path, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\nResults saved to: {result_path}")
        
        sys.exit(0 if result['validation_passed'] else 1)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

