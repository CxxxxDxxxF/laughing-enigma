#!/usr/bin/env python3
"""Walk-forward validation script.

Splits a base config into train/test periods and validates strategy robustness.
"""

import sys
import json
import subprocess
import tempfile
import statistics
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import shutil

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def calculate_sharpe_from_equity(daily_equity: list) -> Optional[float]:
    """Calculate Sharpe ratio from daily equity series.
    
    Args:
        daily_equity: List of dicts with 'equity' field
        
    Returns:
        Sharpe ratio (period-based, not annualized), or None if insufficient data
    """
    if len(daily_equity) < 2:
        return None
    
    # Calculate daily returns
    returns = []
    for i in range(1, len(daily_equity)):
        prev_equity = daily_equity[i-1].get('equity', 0.0)
        curr_equity = daily_equity[i].get('equity', 0.0)
        
        if prev_equity > 0:
            daily_return = (curr_equity - prev_equity) / prev_equity
            returns.append(daily_return)
    
    if len(returns) < 2:
        return None
    
    # Calculate mean and std
    mean_return = statistics.mean(returns)
    std_return = statistics.stdev(returns) if len(returns) > 1 else 0.0
    
    # Sharpe = mean / std (period-based, assumes risk-free rate = 0)
    if std_return == 0:
        return None if mean_return == 0 else float('inf')
    
    sharpe = mean_return / std_return
    return sharpe


def load_evidence_report(artifacts_dir: Path, portfolio_id: str) -> Dict[str, Any]:
    """Load evidence report from artifacts directory.
    
    Args:
        artifacts_dir: Artifacts directory path
        portfolio_id: Portfolio identifier
        
    Returns:
        Evidence report as dictionary
    """
    report_path = artifacts_dir / f"evidence_report_{portfolio_id}.json"
    
    if not report_path.exists():
        raise FileNotFoundError(f"Evidence report not found: {report_path}")
    
    with open(report_path, 'r') as f:
        return json.load(f)


def extract_metrics(report: Dict[str, Any]) -> Dict[str, Any]:
    """Extract metrics from evidence report.
    
    Args:
        report: Evidence report dictionary
        
    Returns:
        Dictionary with final_equity, max_drawdown, sharpe
    """
    final_equity = report.get('final_equity', 0.0)
    max_drawdown = abs(report.get('max_drawdown', 0.0))  # Always positive
    
    # Calculate Sharpe from daily equity
    daily_equity = report.get('daily_equity', [])
    sharpe = calculate_sharpe_from_equity(daily_equity)
    
    return {
        'final_equity': final_equity,
        'max_drawdown': max_drawdown,
        'sharpe': sharpe
    }


def create_date_range_config(
    base_config: Dict[str, Any],
    start_date: str,
    end_date: str,
    suffix: str
) -> Dict[str, Any]:
    """Create a config with modified date ranges for all strategies.
    
    Args:
        base_config: Base configuration dictionary
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        suffix: Suffix to add to portfolio_id and description
        
    Returns:
        Modified configuration dictionary
    """
    config = json.loads(json.dumps(base_config))  # Deep copy
    
    # Update portfolio_id and description
    config['portfolio_id'] = f"{config.get('portfolio_id', 'portfolio')}_{suffix}"
    if 'description' in config:
        config['description'] = f"{config['description']} ({suffix})"
    
    # Update date ranges for all strategies
    if 'evaluation_config' in config and 'strategies' in config['evaluation_config']:
        for strategy in config['evaluation_config']['strategies']:
            if 'inputs' in strategy:
                strategy['inputs']['start_date'] = start_date
                strategy['inputs']['end_date'] = end_date
    
    return config


def run_backtest(config_path: Path, artifacts_dir: Path, num_cycles: int = 30) -> bool:
    """Run backtest using backtest_runner.py.
    
    Args:
        config_path: Path to config file
        artifacts_dir: Artifacts directory
        num_cycles: Number of cycles to run
        
    Returns:
        True if successful, False otherwise
    """
    cmd = [
        sys.executable,
        'scripts/backtest_runner.py',
        '--config', str(config_path),
        '--artifacts', str(artifacts_dir),
        '--cycles', str(num_cycles)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Backtest failed with exit code {e.returncode}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False


def parse_base_dates(base_config: Dict[str, Any]) -> Tuple[str, str]:
    """Extract date range from base config.
    
    Args:
        base_config: Configuration dictionary
        
    Returns:
        Tuple of (start_date, end_date) as strings
    """
    strategies = base_config.get('evaluation_config', {}).get('strategies', [])
    if not strategies:
        raise ValueError("No strategies found in config")
    
    first_strategy = strategies[0]
    inputs = first_strategy.get('inputs', {})
    start_date = inputs.get('start_date')
    end_date = inputs.get('end_date')
    
    if not start_date or not end_date:
        raise ValueError("start_date and end_date must be set in strategy inputs")
    
    return start_date, end_date


def split_date_range(start_date: str, end_date: str, train_split: float = 0.5) -> Tuple[str, str, str, str]:
    """Split date range into train and test periods.
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        train_split: Fraction of period for training (default: 0.5)
        
    Returns:
        Tuple of (train_start, train_end, test_start, test_end)
    """
    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date)
    
    total_days = (end_dt - start_dt).days
    train_days = int(total_days * train_split)
    
    train_end_dt = start_dt + timedelta(days=train_days)
    test_start_dt = train_end_dt + timedelta(days=1)  # Non-overlapping
    
    train_start = start_date
    train_end = train_end_dt.strftime('%Y-%m-%d')
    test_start = test_start_dt.strftime('%Y-%m-%d')
    test_end = end_date
    
    # Ensure test period is valid
    if test_start_dt >= end_dt:
        raise ValueError(
            f"Test period would be empty: test_start={test_start} >= end_date={end_date}. "
            f"Try a smaller train_split (current: {train_split})"
        )
    
    return train_start, train_end, test_start, test_end


def run_walkforward_validation(
    base_config_path: Path,
    output_dir: Optional[Path] = None,
    train_split: float = 0.5,
    num_cycles: int = 30
) -> Dict[str, Any]:
    """Run walk-forward validation.
    
    Args:
        base_config_path: Path to base configuration file
        output_dir: Output directory for artifacts (default: ./artifacts_walkforward)
        train_split: Fraction of period for training (default: 0.5)
        num_cycles: Number of cycles to run per period (default: 30)
        
    Returns:
        Dictionary with validation results
    """
    # Load base config
    with open(base_config_path, 'r') as f:
        base_config = json.load(f)
    
    # Extract date range
    start_date, end_date = parse_base_dates(base_config)
    train_start, train_end, test_start, test_end = split_date_range(
        start_date, end_date, train_split
    )
    
    # Verify non-overlapping
    if test_start <= train_end:
        raise ValueError(f"Date ranges overlap: train_end={train_end}, test_start={test_start}")
    
    # Set output directory
    if output_dir is None:
        output_dir = Path('./artifacts_walkforward')
    
    train_artifacts = output_dir / 'train'
    test_artifacts = output_dir / 'test'
    
    # Create temporary config files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create train config
        train_config = create_date_range_config(base_config, train_start, train_end, 'train')
        train_config_path = tmp_path / 'train_config.json'
        with open(train_config_path, 'w') as f:
            json.dump(train_config, f, indent=2)
        
        # Create test config
        test_config = create_date_range_config(base_config, test_start, test_end, 'test')
        test_config_path = tmp_path / 'test_config.json'
        with open(test_config_path, 'w') as f:
            json.dump(test_config, f, indent=2)
        
        # Run train backtest
        print(f"Running training backtest: {train_start} to {train_end}")
        train_artifacts.mkdir(parents=True, exist_ok=True)
        if not run_backtest(train_config_path, train_artifacts, num_cycles):
            raise RuntimeError("Training backtest failed")
        
        # Run test backtest
        print(f"Running testing backtest: {test_start} to {test_end}")
        test_artifacts.mkdir(parents=True, exist_ok=True)
        if not run_backtest(test_config_path, test_artifacts, num_cycles):
            raise RuntimeError("Testing backtest failed")
    
    # Load evidence reports
    portfolio_id_base = base_config.get('portfolio_id', 'portfolio')
    train_portfolio_id = f"{portfolio_id_base}_train"
    test_portfolio_id = f"{portfolio_id_base}_test"
    
    train_report = load_evidence_report(train_artifacts, train_portfolio_id)
    test_report = load_evidence_report(test_artifacts, test_portfolio_id)
    
    # Extract metrics
    train_metrics = extract_metrics(train_report)
    test_metrics = extract_metrics(test_report)
    
    # Validate pass/fail criteria
    train_sharpe = train_metrics['sharpe']
    test_sharpe = test_metrics['sharpe']
    train_max_dd = train_metrics['max_drawdown']
    test_max_dd = test_metrics['max_drawdown']
    
    # Check criteria
    sharpe_passed = True
    drawdown_passed = True
    
    if train_sharpe is None or test_sharpe is None:
        sharpe_passed = None  # Cannot evaluate
        sharpe_check = "SKIP (insufficient data)"
    else:
        sharpe_threshold = 0.5 * train_sharpe
        sharpe_passed = test_sharpe >= sharpe_threshold
        sharpe_check = f"{test_sharpe:.4f} >= {sharpe_threshold:.4f}" if sharpe_passed else f"{test_sharpe:.4f} < {sharpe_threshold:.4f} (FAIL)"
    
    if train_max_dd == 0:
        drawdown_passed = test_max_dd <= 0  # If train had no drawdown, test should have none
        drawdown_check = f"{test_max_dd:.2f} <= 0.00" if drawdown_passed else f"{test_max_dd:.2f} > 0.00 (FAIL)"
    else:
        drawdown_threshold = 1.5 * train_max_dd
        drawdown_passed = test_max_dd <= drawdown_threshold
        drawdown_check = f"${test_max_dd:.2f} <= ${drawdown_threshold:.2f}" if drawdown_passed else f"${test_max_dd:.2f} > ${drawdown_threshold:.2f} (FAIL)"
    
    overall_passed = (sharpe_passed is None or sharpe_passed) and drawdown_passed
    
    # Build result
    result = {
        'validation_passed': overall_passed,
        'date_ranges': {
            'train': {'start': train_start, 'end': train_end},
            'test': {'start': test_start, 'end': test_end}
        },
        'train_metrics': train_metrics,
        'test_metrics': test_metrics,
        'criteria': {
            'sharpe': {
                'passed': sharpe_passed,
                'check': sharpe_check,
                'requirement': 'test_sharpe >= 0.5 * train_sharpe'
            },
            'drawdown': {
                'passed': drawdown_passed,
                'check': drawdown_check,
                'requirement': 'test_max_drawdown <= 1.5 * train_max_drawdown'
            }
        }
    }
    
    return result


def print_results(result: Dict[str, Any]):
    """Print validation results to console.
    
    Args:
        result: Validation result dictionary
    """
    print("=" * 80)
    print("Walk-Forward Validation Results")
    print("=" * 80)
    print()
    
    print("Date Ranges:")
    train_range = result['date_ranges']['train']
    test_range = result['date_ranges']['test']
    print(f"  Training: {train_range['start']} to {train_range['end']}")
    print(f"  Testing:  {test_range['start']} to {test_range['end']}")
    print()
    
    print("Training Metrics:")
    train = result['train_metrics']
    print(f"  Final Equity: ${train['final_equity']:,.2f}")
    print(f"  Max Drawdown: ${train['max_drawdown']:,.2f}")
    print(f"  Sharpe Ratio: {train['sharpe']:.4f}" if train['sharpe'] is not None else "  Sharpe Ratio: N/A (insufficient data)")
    print()
    
    print("Testing Metrics:")
    test = result['test_metrics']
    print(f"  Final Equity: ${test['final_equity']:,.2f}")
    print(f"  Max Drawdown: ${test['max_drawdown']:,.2f}")
    print(f"  Sharpe Ratio: {test['sharpe']:.4f}" if test['sharpe'] is not None else "  Sharpe Ratio: N/A (insufficient data)")
    print()
    
    print("Validation Criteria:")
    sharpe_criteria = result['criteria']['sharpe']
    print(f"  Sharpe: {sharpe_criteria['check']}")
    print(f"    Requirement: {sharpe_criteria['requirement']}")
    drawdown_criteria = result['criteria']['drawdown']
    print(f"  Drawdown: {drawdown_criteria['check']}")
    print(f"    Requirement: {drawdown_criteria['requirement']}")
    print()
    
    if result['validation_passed']:
        print("✓ VALIDATION PASSED")
    else:
        print("✗ VALIDATION FAILED")
    print("=" * 80)


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run walk-forward validation on a strategy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run walk-forward validation with default 50/50 split
  python scripts/run_walkforward.py --config configs/backtest/topstep_50k_backtest.json
  
  # Custom train/test split (70% train, 30% test)
  python scripts/run_walkforward.py --config configs/backtest/topstep_50k_backtest.json --train-split 0.7
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
        default=Path('./artifacts_walkforward'),
        help='Output directory for artifacts (default: ./artifacts_walkforward)'
    )
    
    parser.add_argument(
        '--train-split',
        type=float,
        default=0.5,
        help='Fraction of period for training (default: 0.5)'
    )
    
    parser.add_argument(
        '--cycles',
        type=int,
        default=30,
        help='Number of cycles to run per period (default: 30)'
    )
    
    args = parser.parse_args()
    
    if not args.config.exists():
        print(f"ERROR: Config file not found: {args.config}")
        sys.exit(1)
    
    if not (0 < args.train_split < 1):
        print(f"ERROR: train_split must be between 0 and 1, got: {args.train_split}")
        sys.exit(1)
    
    try:
        # Run validation
        result = run_walkforward_validation(
            base_config_path=args.config,
            output_dir=args.output_dir,
            train_split=args.train_split,
            num_cycles=args.cycles
        )
        
        # Print results
        print_results(result)
        
        # Save results
        result_path = args.output_dir / 'walkforward_result.json'
        result_path.parent.mkdir(parents=True, exist_ok=True)
        with open(result_path, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\nResults saved to: {result_path}")
        
        # Exit with appropriate code
        sys.exit(0 if result['validation_passed'] else 1)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

