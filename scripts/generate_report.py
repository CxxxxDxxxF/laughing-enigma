
"""Generate evidence report for funded firm evaluation.

Usage:
    python scripts/generate_report.py --portfolio <portfolio_id> [--artifacts <dir>] [--output <file>]
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import date

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.artifacts import LocalArtifactStore
from src.analysis.evidence_report import generate_evidence_report, report_to_dict, print_evidence_report

def main():
    parser = argparse.ArgumentParser(description="Generate Evidence Report")
    parser.add_argument("--portfolio", required=True, help="Portfolio ID")
    parser.add_argument("--artifacts", default="data/artifacts", help="Artifacts directory")
    parser.add_argument("--output", default="evidence_report.json", help="Output JSON file path")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    # Parse dates
    start_date = date.fromisoformat(args.start_date) if args.start_date else None
    end_date = date.fromisoformat(args.end_date) if args.end_date else None
    
    # Initialize artifact store
    artifacts_path = Path(args.artifacts)
    if not artifacts_path.exists():
        print(f"Error: Artifacts directory not found: {artifacts_path}")
        sys.exit(1)
        
    store = LocalArtifactStore(artifacts_path)
    
    print(f"Generating report for portfolio: {args.portfolio}")
    print(f"Source: {artifacts_path}")
    
    try:
        report = generate_evidence_report(
            artifact_store=store,
            portfolio_id=args.portfolio,
            start_date=start_date,
            end_date=end_date
        )
        
        # specific print
        print_evidence_report(report)
        
        # Save JSON
        report_dict = report_to_dict(report)
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        output_path.write_text(json.dumps(report_dict, indent=2))
        print(f"\nReport saved to: {output_path}")
        
    except Exception as e:
        print(f"Error generating report: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
