#!/usr/bin/env python3
"""Determinism Verification for Layer 2 Backtest

This script verifies that --light-artifacts mode produces identical results
to full mode. It runs the backtest twice and compares final results.

Usage:
    python scripts/verify_layer2_determinism.py [--days N] [--instruments INSTR] [--mode full|light|both]
    
    --days: Number of days to run (default: 5 for fast test, 365 for full)
    --instruments: Comma-separated instruments (default: ES)
    --mode: Which mode(s) to test (default: both)
"""

import sys
import os
import json
import subprocess
import tempfile
import shutil
import argparse
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Float comparison tolerance (for floating-point precision issues)
FLOAT_TOLERANCE = 1e-10


@dataclass
class ComparisonResult:
    """Result of comparing two values."""
    match: bool
    full_value: Any
    light_value: Any
    field_path: str
    message: str


def compare_floats(full: float, light: float, field_path: str) -> ComparisonResult:
    """Compare two float values with tolerance.
    
    Uses relative tolerance for large values, absolute tolerance for small values.
    Handles special cases:
    - Infinity values
    - NaN values
    - Regular floats with adaptive tolerance
    """
    import math
    
    # Handle Infinity
    if full == float('inf') and light == float('inf'):
        return ComparisonResult(True, full, light, field_path, "Both are Infinity")
    if full == float('-inf') and light == float('-inf'):
        return ComparisonResult(True, full, light, field_path, "Both are -Infinity")
    if (full == float('inf') or full == float('-inf')) and not (light == float('inf') or light == float('-inf')):
        return ComparisonResult(False, full, light, field_path, f"Infinity mismatch: {full} vs {light}")
    if (light == float('inf') or light == float('-inf')) and not (full == float('inf') or full == float('-inf')):
        return ComparisonResult(False, full, light, field_path, f"Infinity mismatch: {full} vs {light}")
    
    # Handle NaN
    if math.isnan(full) and math.isnan(light):
        return ComparisonResult(True, full, light, field_path, "Both are NaN")
    if math.isnan(full) or math.isnan(light):
        return ComparisonResult(False, full, light, field_path, f"NaN mismatch: {full} vs {light}")
    
    # Adaptive tolerance: relative for large values, absolute for small values
    diff = abs(full - light)
    
    # For values > 1.0, use relative tolerance (1e-9 = 0.0000001%)
    # For values <= 1.0, use absolute tolerance (1e-10)
    if abs(full) > 1.0 or abs(light) > 1.0:
        # Relative tolerance: compare against larger magnitude
        max_magnitude = max(abs(full), abs(light))
        rel_tolerance = max_magnitude * 1e-9
        if diff <= rel_tolerance:
            return ComparisonResult(True, full, light, field_path, f"Match (relative diff={diff/max_magnitude:.2e})")
        else:
            return ComparisonResult(False, full, light, field_path, f"Mismatch: diff={diff:.2e}, rel_diff={diff/max_magnitude:.2e}, full={full}, light={light}")
    else:
        # Absolute tolerance for small values
        if diff <= FLOAT_TOLERANCE:
            return ComparisonResult(True, full, light, field_path, f"Match (absolute diff={diff:.2e})")
        else:
            return ComparisonResult(False, full, light, field_path, f"Mismatch: diff={diff:.2e}, full={full}, light={light}")


def compare_values(full: Any, light: Any, field_path: str = "") -> List[ComparisonResult]:
    """Compare two values recursively.
    
    Returns list of comparison results (empty if all match).
    """
    results = []
    
    # Type mismatch
    if type(full) != type(light):
        results.append(ComparisonResult(
            False, full, light, field_path,
            f"Type mismatch: {type(full).__name__} vs {type(light).__name__}"
        ))
        return results
    
    # Handle different types
    if isinstance(full, dict):
        # Compare dictionaries (order doesn't matter)
        all_keys = set(full.keys()) | set(light.keys())
        for key in all_keys:
            if key not in full:
                results.append(ComparisonResult(
                    False, None, light[key], f"{field_path}.{key}",
                    f"Key '{key}' missing in full mode"
                ))
            elif key not in light:
                results.append(ComparisonResult(
                    False, full[key], None, f"{field_path}.{key}",
                    f"Key '{key}' missing in light mode"
                ))
            else:
                results.extend(compare_values(full[key], light[key], f"{field_path}.{key}" if field_path else key))
    
    elif isinstance(full, list):
        # Compare lists (order matters)
        if len(full) != len(light):
            results.append(ComparisonResult(
                False, len(full), len(light), field_path,
                f"List length mismatch: {len(full)} vs {len(light)}"
            ))
        else:
            for i, (f, l) in enumerate(zip(full, light)):
                results.extend(compare_values(f, l, f"{field_path}[{i}]"))
    
    elif isinstance(full, (int, bool)):
        # Exact match for integers and booleans
        if full != light:
            results.append(ComparisonResult(
                False, full, light, field_path,
                f"Mismatch: {full} vs {light}"
            ))
    
    elif isinstance(full, float):
        # Float comparison with tolerance
        result = compare_floats(full, light, field_path)
        if not result.match:
            results.append(result)
    
    elif isinstance(full, str):
        # Exact match for strings
        if full != light:
            results.append(ComparisonResult(
                False, full, light, field_path,
                f"String mismatch: '{full}' vs '{light}'"
            ))
    
    else:
        # Other types (shouldn't happen, but handle gracefully)
        if full != light:
            results.append(ComparisonResult(
                False, full, light, field_path,
                f"Value mismatch: {full} vs {light}"
            ))
    
    return results


def compute_results_hash(results: Dict[str, Any]) -> str:
    """Compute deterministic hash of results for byte-level comparison.
    
    Args:
        results: Results dictionary
        
    Returns:
        SHA256 hex digest of canonical JSON representation
    """
    # Sort keys for deterministic ordering
    canonical_json = json.dumps(results, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()


def run_backtest(mode_name: str, light_artifacts: bool, project_root: Path, results_suffix: str, days: Optional[int] = None, instruments: Optional[List[str]] = None) -> Tuple[Path, str]:
    """Run Layer 2 backtest and return path to results file.
    
    Args:
        mode_name: Name for this run (for logging)
        light_artifacts: Whether to use --light-artifacts flag
        project_root: Project root directory
        results_suffix: Suffix for results filename (to avoid overwriting)
        
    Returns:
        Path to LAYER2_BACKTEST_RESULTS.json
    """
    print(f"\n{'='*80}")
    print(f"Running {mode_name} mode...")
    print(f"{'='*80}")
    
    # Change to project root
    original_cwd = Path.cwd()
    os.chdir(project_root)
    
    try:
        # Run the backtest script
        # Use python3 explicitly (python may not be available on macOS)
        python_cmd = "python3" if sys.platform != "win32" else "python"
        cmd = [python_cmd, "scripts/run_layer2_backtest.py"]
        if light_artifacts:
            cmd.append("--light-artifacts")
        if days is not None:
            cmd.extend(["--days", str(days)])
        if instruments is not None:
            cmd.extend(["--instruments", ",".join(instruments)])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False  # Don't fail on non-zero exit, we'll check results file
        )
        
        # Print output for debugging (only show progress, not full output)
        if result.stdout:
            # Filter to show only key lines
            lines = result.stdout.split('\n')
            for line in lines:
                if any(keyword in line for keyword in ['[Layer2]', 'Results:', 'SUMMARY', 'Complete', 'ERROR', 'FATAL']):
                    print(line)
        
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        # Check exit code - if non-zero, the run failed
        if result.returncode != 0:
            raise RuntimeError(
                f"{mode_name} mode failed with exit code {result.returncode}. "
                f"stdout: {result.stdout[-500:] if result.stdout else 'None'}, "
                f"stderr: {result.stderr[-500:] if result.stderr else 'None'}"
            )
        
        # Check if results file was created
        results_path = project_root / "LAYER2_BACKTEST_RESULTS.json"
        if not results_path.exists():
            raise RuntimeError(f"Results file not created: {results_path}")
        
        # Rename to avoid overwriting
        renamed_path = project_root / f"LAYER2_BACKTEST_RESULTS_{results_suffix}.json"
        if renamed_path.exists():
            renamed_path.unlink()
        results_path.rename(renamed_path)
        
        # Compute hash for this run
        results_data = load_results(renamed_path)
        results_hash = compute_results_hash(results_data)
        
        return renamed_path, results_hash
        
    finally:
        os.chdir(original_cwd)


def load_results(results_path: Path) -> Dict[str, Any]:
    """Load results from JSON file.
    
    Note: JSON may contain "Infinity" as a string, which we'll handle in comparison.
    """
    with open(results_path, 'r') as f:
        data = json.load(f)
    
    # Convert string "Infinity"/"inf" to float('inf') for consistent comparison
    # JSON may serialize float('inf') as string "inf" or "Infinity" depending on encoder
    def normalize_infinity(obj):
        if isinstance(obj, dict):
            return {k: normalize_infinity(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [normalize_infinity(item) for item in obj]
        elif isinstance(obj, str):
            if obj.lower() == "infinity" or obj.lower() == "inf":
                return float('inf')
            elif obj.lower() == "-infinity" or obj.lower() == "-inf":
                return float('-inf')
            else:
                return obj
        else:
            return obj
    
    return normalize_infinity(data)


def verify_determinism(days: int = 5, instruments: List[str] = None, mode: str = "both") -> bool:
    """Run determinism verification.
    
    Args:
        days: Number of days to run (default: 5 for fast test)
        instruments: List of instruments to test (default: ["ES"])
        mode: Which mode(s) to test - "full", "light", or "both" (default: "both")
    
    Returns:
        True if verification passes, False otherwise
    """
    if instruments is None:
        instruments = ["ES"]
    
    print("="*80)
    print("LAYER 2 DETERMINISM VERIFICATION")
    print("="*80)
    print(f"Days: {days}")
    print(f"Instruments: {', '.join(instruments)}")
    print(f"Mode: {mode}")
    print(f"Float tolerance: {FLOAT_TOLERANCE} (absolute), 1e-9 (relative for values > 1.0)")
    print()
    
    project_root = Path(__file__).parent.parent
    
    results_paths = {}
    results_hashes = {}
    
    # Run full mode if requested
    if mode in ("both", "full"):
        print("\n[1/2] Running FULL mode (all artifacts)...")
        full_results_path, full_hash = run_backtest("FULL", light_artifacts=False, project_root=project_root, results_suffix="full", days=days, instruments=instruments)
        results_paths["full"] = full_results_path
        results_hashes["full"] = full_hash
        print(f"FULL mode hash: {full_hash}")
    
    # Run light mode if requested
    if mode in ("both", "light"):
        print("\n[2/2] Running LIGHT mode (--light-artifacts)...")
        light_results_path, light_hash = run_backtest("LIGHT", light_artifacts=True, project_root=project_root, results_suffix="light", days=days, instruments=instruments)
        results_paths["light"] = light_results_path
        results_hashes["light"] = light_hash
        print(f"LIGHT mode hash: {light_hash}")
    
    # Compare results
    print("\n" + "="*80)
    print("VERIFICATION RESULTS")
    print("="*80)
    
    if mode == "both":
        # Compare full vs light
        full_results = load_results(results_paths["full"])
        light_results = load_results(results_paths["light"])
        comparison_results = compare_values(full_results, light_results, "")
        
        hash_match = results_hashes["full"] == results_hashes["light"]
        
        if hash_match and not comparison_results:
            print("\n✅ SUCCESS: Results are IDENTICAL")
            print(f"\nHash match: {hash_match}")
            print(f"Hash: {results_hashes['full']}")
            print("\nAll metrics match between full mode and --light-artifacts mode.")
            print("This confirms that --light-artifacts is a pure I/O optimization")
            print("and does not change computation, state evolution, or final results.")
            
            # Clean up temporary results files
            try:
                results_paths["full"].unlink()
                results_paths["light"].unlink()
            except Exception:
                pass  # Ignore cleanup errors
            
            return True
        else:
            print(f"\n❌ FAILURE: Results differ")
            if not hash_match:
                print(f"Hash mismatch:")
                print(f"  FULL:  {results_hashes['full']}")
                print(f"  LIGHT: {results_hashes['light']}")
            if comparison_results:
                print(f"\nFound {len(comparison_results)} field difference(s):")
                print("-"*80)
                for i, result in enumerate(comparison_results[:10], 1):  # Show first 10
                    print(f"\n{i}. Field: {result.field_path}")
                    print(f"   Full mode:  {result.full_value}")
                    print(f"   Light mode: {result.light_value}")
                    print(f"   Reason: {result.message}")
                if len(comparison_results) > 10:
                    print(f"\n... and {len(comparison_results) - 10} more differences")
            print("\n" + "="*80)
            print("❌ DETERMINISM VERIFICATION FAILED")
            print("="*80)
            print(f"\nFull mode results: {results_paths.get('full')}")
            print(f"Light mode results: {results_paths.get('light')}")
            return False
    else:
        # Single mode - just verify it runs and produces hash
        mode_name = mode.upper()
        print(f"\n✅ SUCCESS: {mode_name} mode completed")
        print(f"Hash: {results_hashes[mode]}")
        try:
            results_paths[mode].unlink()
        except Exception:
            pass
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify determinism of Layer 2 backtest",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--days",
        type=int,
        default=5,
        help="Number of days to run (default: 5 for fast test, use 365 for full)"
    )
    parser.add_argument(
        "--instruments",
        type=str,
        default="ES",
        help="Comma-separated instruments (default: ES)"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["full", "light", "both"],
        default="both",
        help="Which mode(s) to test (default: both)"
    )
    
    args = parser.parse_args()
    
    instruments = [i.strip() for i in args.instruments.split(",")]
    
    try:
        success = verify_determinism(days=args.days, instruments=instruments, mode=args.mode)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ VERIFICATION ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

