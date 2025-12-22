#!/usr/bin/env python3
"""Strategy validation suite aggregator.

Runs all three validation gates:
- Gate 1: Walk-Forward Validation
- Gate 2: Parameter Perturbation
- Gate 3: Regime Stress

Aggregates results and provides overall pass/fail decision.
"""

import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_gate1(
    config_path: Path,
    artifacts_dir: Path,
    train_split: float = 0.5,
    num_cycles: int = 30,
    output_subdir: Optional[Path] = None
) -> tuple[bool, Dict[str, Any]]:
    """Run Gate 1: Walk-Forward Validation."""
    if output_subdir is None:
        output_subdir = artifacts_dir / 'gate1_walkforward'
    else:
        output_subdir = artifacts_dir / output_subdir
    
    output_subdir.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        sys.executable,
        'scripts/run_walkforward.py',
        '--config', str(config_path),
        '--output-dir', str(output_subdir),
        '--train-split', str(train_split),
        '--cycles', str(num_cycles)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Load result JSON
        result_path = output_subdir / 'walkforward_result.json'
        if result_path.exists():
            with open(result_path, 'r') as f:
                result_data = json.load(f)
            return result_data.get('validation_passed', False), result_data
        else:
            return False, {'error': 'Result file not found'}
    except subprocess.CalledProcessError as e:
        return False, {
            'error': f'Gate 1 failed with exit code {e.returncode}',
            'stdout': e.stdout,
            'stderr': e.stderr
        }
    except Exception as e:
        return False, {'error': str(e)}


def run_gate2(
    config_path: Path,
    artifacts_dir: Path,
    param_name: str,
    pct: Optional[float] = None,
    values: Optional[list] = None,
    strategy_id: Optional[str] = None,
    num_cycles: int = 30,
    output_subdir: Optional[Path] = None
) -> tuple[bool, Dict[str, Any]]:
    """Run Gate 2: Parameter Perturbation."""
    if output_subdir is None:
        output_subdir = artifacts_dir / 'gate2_parameter_perturbation'
    else:
        output_subdir = artifacts_dir / output_subdir
    
    output_subdir.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        sys.executable,
        'scripts/run_parameter_perturbation.py',
        '--config', str(config_path),
        '--param', param_name,
        '--artifacts', str(output_subdir),
        '--cycles', str(num_cycles)
    ]
    
    if pct is not None:
        cmd.extend(['--pct', str(pct)])
    elif values is not None:
        cmd.extend(['--values'] + [str(v) for v in values])
    else:
        return False, {'error': 'Either --pct or --values must be provided'}
    
    if strategy_id is not None:
        cmd.extend(['--strategy-id', strategy_id])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Load result JSON
        result_path = output_subdir / 'parameter_perturbation_result.json'
        if result_path.exists():
            with open(result_path, 'r') as f:
                result_data = json.load(f)
            return result_data.get('validation_passed', False), result_data
        else:
            return False, {'error': 'Result file not found'}
    except subprocess.CalledProcessError as e:
        return False, {
            'error': f'Gate 2 failed with exit code {e.returncode}',
            'stdout': e.stdout,
            'stderr': e.stderr
        }
    except Exception as e:
        return False, {'error': str(e)}


def run_gate3(
    config_path: Path,
    artifacts_dir: Path,
    regimes: Optional[list] = None,
    num_cycles: int = 30,
    output_subdir: Optional[Path] = None
) -> tuple[bool, Dict[str, Any]]:
    """Run Gate 3: Regime Stress."""
    if output_subdir is None:
        output_subdir = artifacts_dir / 'gate3_regime_stress'
    else:
        output_subdir = artifacts_dir / output_subdir
    
    output_subdir.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        sys.executable,
        'scripts/run_regime_stress.py',
        '--config', str(config_path),
        '--artifacts', str(output_subdir),
        '--cycles', str(num_cycles)
    ]
    
    if regimes is not None:
        cmd.extend(['--regimes'] + regimes)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Load result JSON
        result_path = output_subdir / 'regime_stress_result.json'
        if result_path.exists():
            with open(result_path, 'r') as f:
                result_data = json.load(f)
            return result_data.get('validation_passed', False), result_data
        else:
            return False, {'error': 'Result file not found'}
    except subprocess.CalledProcessError as e:
        return False, {
            'error': f'Gate 3 failed with exit code {e.returncode}',
            'stdout': e.stdout,
            'stderr': e.stderr
        }
    except Exception as e:
        return False, {'error': str(e)}


def run_validation_suite(
    config_path: Path,
    artifacts_dir: Path,
    train_split: float = 0.5,
    param_name: str = 'daily_trend',
    pct: Optional[float] = 0.2,
    values: Optional[list] = None,
    strategy_id: Optional[str] = None,
    regimes: Optional[list] = None,
    num_cycles: int = 30
) -> Dict[str, Any]:
    """Run complete validation suite (all three gates)."""
    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 80)
    print("Strategy Validation Suite")
    print("=" * 80)
    print()
    print(f"Config: {config_path}")
    print(f"Artifacts: {artifacts_dir}")
    print()
    
    # Run Gate 1: Walk-Forward Validation
    print("Running Gate 1: Walk-Forward Validation...")
    print("-" * 80)
    gate1_passed, gate1_result = run_gate1(
        config_path, artifacts_dir, train_split, num_cycles
    )
    print(f"Gate 1: {'PASS' if gate1_passed else 'FAIL'}")
    if 'error' in gate1_result:
        print(f"  Error: {gate1_result['error']}")
    print()
    
    # Run Gate 2: Parameter Perturbation
    print("Running Gate 2: Parameter Perturbation...")
    print("-" * 80)
    gate2_passed, gate2_result = run_gate2(
        config_path, artifacts_dir, param_name, pct, values, strategy_id, num_cycles
    )
    print(f"Gate 2: {'PASS' if gate2_passed else 'FAIL'}")
    if 'error' in gate2_result:
        print(f"  Error: {gate2_result['error']}")
    print()
    
    # Run Gate 3: Regime Stress
    print("Running Gate 3: Regime Stress...")
    print("-" * 80)
    gate3_passed, gate3_result = run_gate3(
        config_path, artifacts_dir, regimes, num_cycles
    )
    print(f"Gate 3: {'PASS' if gate3_passed else 'FAIL'}")
    if 'error' in gate3_result:
        print(f"  Error: {gate3_result['error']}")
    print()
    
    # Aggregate results
    all_passed = gate1_passed and gate2_passed and gate3_passed
    
    result = {
        'validation_passed': all_passed,
        'gate1_walkforward': {
            'passed': gate1_passed,
            'result': gate1_result
        },
        'gate2_parameter_perturbation': {
            'passed': gate2_passed,
            'result': gate2_result
        },
        'gate3_regime_stress': {
            'passed': gate3_passed,
            'result': gate3_result
        }
    }
    
    return result


def print_summary(result: Dict[str, Any]):
    """Print validation suite summary."""
    print("=" * 80)
    print("Validation Suite Summary")
    print("=" * 80)
    print()
    
    for gate_name, gate_data in [
        ('Gate 1: Walk-Forward Validation', result['gate1_walkforward']),
        ('Gate 2: Parameter Perturbation', result['gate2_parameter_perturbation']),
        ('Gate 3: Regime Stress', result['gate3_regime_stress'])
    ]:
        status = 'PASS' if gate_data['passed'] else 'FAIL'
        print(f"{gate_name}: {status}")
        if 'error' in gate_data.get('result', {}):
            print(f"  Error: {gate_data['result']['error']}")
    print()
    
    if result['validation_passed']:
        print("✓ OVERALL: VALIDATION PASSED")
        print("  Strategy is ready for further testing/deployment consideration")
    else:
        print("✗ OVERALL: VALIDATION FAILED")
        print("  Strategy did not pass all validation gates")
        print("  RECOMMENDATION: Do not deploy until all gates pass")
    print("=" * 80)


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run complete strategy validation suite (all three gates)",
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
    
    # Gate 1 args
    parser.add_argument(
        '--train-split',
        type=float,
        default=0.5,
        help='Train/test split for walk-forward (default: 0.5)'
    )
    
    # Gate 2 args
    parser.add_argument(
        '--param',
        type=str,
        default='daily_trend',
        help='Parameter name for perturbation test (default: daily_trend)'
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
        '--strategy-id',
        type=str,
        help='Strategy ID to target (if multiple strategies)'
    )
    
    # Gate 3 args
    parser.add_argument(
        '--regimes',
        type=str,
        nargs='+',
        help='List of regimes to test (default: trending mean_reverting flat volatile)'
    )
    
    # Common args
    parser.add_argument(
        '--cycles',
        type=int,
        default=30,
        help='Number of cycles to run per gate (default: 30)'
    )
    
    args = parser.parse_args()
    
    if not args.config.exists():
        print(f"ERROR: Config file not found: {args.config}")
        sys.exit(2)
    
    # Default pct if neither pct nor values provided
    if args.pct is None and args.values is None:
        args.pct = 0.2
    
    try:
        result = run_validation_suite(
            config_path=args.config,
            artifacts_dir=args.artifacts,
            train_split=args.train_split,
            param_name=args.param,
            pct=args.pct,
            values=args.values,
            strategy_id=args.strategy_id,
            regimes=args.regimes,
            num_cycles=args.cycles
        )
        
        print_summary(result)
        
        # Save results
        result_path = args.artifacts / 'validation_suite_result.json'
        result_path.parent.mkdir(parents=True, exist_ok=True)
        with open(result_path, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\nResults saved to: {result_path}")
        
        sys.exit(0 if result['validation_passed'] else 1)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == '__main__':
    main()

