#!/usr/bin/env python3
"""
Dashboard CLI Entry Point
Wrapper around src.ui.cli.dashboard
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ui.cli.dashboard import main

if __name__ == "__main__":
    main()
