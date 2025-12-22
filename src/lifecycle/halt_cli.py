"""CLI commands for halt flag inspection and clearing.

Provides manual intervention workflow for halted portfolios.
No auto-resume - requires explicit user action to clear halt flags.
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .runner import HaltFlagStore, CycleError
from ..core.artifacts import LocalArtifactStore


def inspect_halt(artifact_store_path: Path, portfolio_id: str) -> None:
    """Inspect halt flag for a portfolio.
    
    Args:
        artifact_store_path: Path to artifact store base directory
        portfolio_id: Portfolio identifier
        
    Raises:
        SystemExit: If halt flag doesn't exist or cannot be read
    """
    artifact_store = LocalArtifactStore(artifact_store_path)
    halt_store = HaltFlagStore(artifact_store)
    
    if not halt_store.halt_flag_exists(portfolio_id):
        print(f"Portfolio {portfolio_id} is not halted.")
        sys.exit(0)
    
    halt_data = halt_store.read_halt_flag(portfolio_id)
    if halt_data is None:
        print(f"ERROR: Halt flag exists but cannot be read for portfolio {portfolio_id}")
        sys.exit(1)
    
    # Get file path for reference
    flag_path = halt_store._get_halt_flag_path(portfolio_id)
    
    print(f"Portfolio {portfolio_id} is HALTED")
    print("=" * 70)
    print(f"Cycle ID: {halt_data.get('cycle_id', 'Unknown')}")
    print(f"Timestamp: {halt_data.get('halted_at', 'Unknown')}")
    print(f"Reason: {halt_data.get('reason', 'Unknown')}")
    
    violations = halt_data.get('violations_summary', [])
    if violations:
        print(f"\nViolations ({len(violations)}):")
        for i, violation in enumerate(violations, 1):
            print(f"  {i}. [{violation.get('severity', 'unknown')}] {violation.get('code', 'UNKNOWN')}")
            print(f"     {violation.get('message', 'No message')}")
    else:
        print("\nNo violations summary available.")
    
    print("\n" + "=" * 70)
    print(f"Halt flag file: {flag_path}")
    print("\nTo clear the halt flag, use:")
    print(f"  python -m src.lifecycle.halt_cli clear {portfolio_id} --artifacts {artifact_store_path}")


def clear_halt(artifact_store_path: Path, portfolio_id: str, force: bool = False) -> None:
    """Clear halt flag for a portfolio.
    
    Args:
        artifact_store_path: Path to artifact store base directory
        portfolio_id: Portfolio identifier
        force: If True, skip confirmation prompt
        
    Raises:
        SystemExit: If halt flag doesn't exist or clearing fails
    """
    artifact_store = LocalArtifactStore(artifact_store_path)
    halt_store = HaltFlagStore(artifact_store)
    
    if not halt_store.halt_flag_exists(portfolio_id):
        print(f"Portfolio {portfolio_id} is not halted. Nothing to clear.")
        sys.exit(0)
    
    # Show halt info before clearing
    halt_data = halt_store.read_halt_flag(portfolio_id)
    if halt_data:
        print(f"Portfolio {portfolio_id} halt information:")
        print(f"  Halted at: {halt_data.get('halted_at', 'Unknown')}")
        print(f"  Cycle ID: {halt_data.get('cycle_id', 'Unknown')}")
        print(f"  Reason: {halt_data.get('reason', 'Unknown')}")
        print()
    
    # Confirm before clearing (unless force)
    if not force:
        response = input(f"Clear halt flag for portfolio {portfolio_id}? (yes/no): ")
        if response.lower() not in ("yes", "y"):
            print("Aborted.")
            sys.exit(0)
    
    try:
        halt_store.clear_halt_flag(portfolio_id)
        print(f"Halt flag cleared for portfolio {portfolio_id}.")
        print("Portfolio can now resume trading.")
    except CycleError as e:
        print(f"ERROR: Failed to clear halt flag: {e}")
        sys.exit(1)


def main():
    """CLI entry point for halt management."""
    parser = argparse.ArgumentParser(
        description="Manage halt flags for portfolios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Inspect halt flag
  python -m src.lifecycle.halt_cli inspect validation_portfolio --artifacts ./artifacts
  
  # Clear halt flag (with confirmation)
  python -m src.lifecycle.halt_cli clear validation_portfolio --artifacts ./artifacts
  
  # Clear halt flag (force, no confirmation)
  python -m src.lifecycle.halt_cli clear validation_portfolio --artifacts ./artifacts --force
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Inspect command
    inspect_parser = subparsers.add_parser("inspect", help="Inspect halt flag for a portfolio")
    inspect_parser.add_argument("portfolio_id", help="Portfolio identifier")
    inspect_parser.add_argument("--artifacts", type=Path, default=Path("./artifacts"),
                               help="Path to artifact store base directory (default: ./artifacts)")
    
    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear halt flag for a portfolio")
    clear_parser.add_argument("portfolio_id", help="Portfolio identifier")
    clear_parser.add_argument("--artifacts", type=Path, default=Path("./artifacts"),
                             help="Path to artifact store base directory (default: ./artifacts)")
    clear_parser.add_argument("--force", action="store_true",
                             help="Skip confirmation prompt")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == "inspect":
        inspect_halt(args.artifacts, args.portfolio_id)
    elif args.command == "clear":
        clear_halt(args.artifacts, args.portfolio_id, force=args.force)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

