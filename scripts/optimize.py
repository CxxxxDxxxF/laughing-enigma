#!/usr/bin/env python3
"""
Optimization Runner CLI.

Manually trigger an off-hours optimization run for a specific strategy and portfolio.
This is useful for ad-hoc testing or scheduled cron jobs outside the main runner.

Usage:
    python scripts/optimize.py --portfolio <id> --strategy <name> [--duration <seconds>]
"""

import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.logger import logger
from src.core.artifacts import LocalArtifactStore
from src.optimization.off_hours_runner import run_off_hours_optimization
import src.strategy.strategies # Register strategies

def main():
    parser = argparse.ArgumentParser(description="Run Off-Hours Optimization")
    parser.add_argument("--portfolio", required=True, help="Portfolio ID to optimize for")
    parser.add_argument("--strategy", required=True, help="Strategy name (e.g., dual_momentum)")
    parser.add_argument("--duration", type=int, default=3600, help="Max duration in seconds (default: 3600)")
    parser.add_argument("--artifacts", default="data/artifacts", help="Path to artifacts directory")
    
    args = parser.parse_args()
    
    # Setup logging to console
    # setup_logging() # Already done on import
    
    # Load env (though optimization might not need keys, the deps might)
    load_dotenv()
    
    # Setup Artifact Store
    artifact_store = LocalArtifactStore(Path(args.artifacts))
    
    logger.info(f"Starting optimization for {args.portfolio} using {args.strategy}")
    logger.info(f"Max duration: {args.duration}s")
    
    try:
        result = run_off_hours_optimization(
            portfolio_id=args.portfolio,
            strategy_name=args.strategy,
            artifact_store=artifact_store,
            max_duration_seconds=args.duration
        )
        
        print("\n--- Optimization Complete ---")
        print(f"Strategies Tested: {result.strategies_tested}")
        print(f"Best Strategy ID: {result.best_strategy_id}")
        print(f"Best Metric ({result.metric_name}): {result.best_metric_value:.4f}")
        print(f"Timestamp: {result.completed_at}")
        print(f"Saved to: Runs/{result.run_id if hasattr(result, 'run_id') else 'Batch'}")
        
    except Exception as e:
        logger.error(f"Optimization failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
