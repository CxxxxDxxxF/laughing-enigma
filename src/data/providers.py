"""Concrete implementations of MarketDataProvider.

This module provides ready-to-use providers for different environments.
"""

import csv
from typing import Dict, Optional, List, Any
from datetime import datetime
from pathlib import Path
import bisect

from ..market.interface import MarketDataProvider

class FileReplayMarketDataProvider(MarketDataProvider):
    """Provides market data by replaying a CSV file.
    
    The CSV must have at least 'timestamp' and 'close' (or 'price') columns.
    Timestamps in CSV are expected to be ISO 8601 strings.
    
    This provider implements forward-fill logic: if exact timestamp match
    is not found, it returns the most recent price at or before the requested
    timestamp.
    """
    
    def __init__(self, csv_path: str, instrument: str, timestamp_col: str = "timestamp", price_col: str = "close"):
        """Initialize provider.
        
        Args:
            csv_path: Path to CSV file
            instrument: Instrument identifier this file belongs to (e.g. 'AAPL')
            timestamp_col: Name of timestamp column
            price_col: Name of price column
        """
        self.csv_path = csv_path
        self.instrument = instrument
        self.timestamp_col = timestamp_col
        self.price_col = price_col
        
        self.data: List[tuple[datetime, float]] = []
        self._load_data()
        
    def _load_data(self):
        """Load and sort data from CSV."""
        path = Path(self.csv_path)
        if not path.exists():
            raise FileNotFoundError(f"Market data file not found: {self.csv_path}")
            
        with open(path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts_str = row[self.timestamp_col]
                    price_str = row[self.price_col]
                    
                    # Handle flexible timestamp formats if needed, but strict ISO is safer
                    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    price = float(price_str)
                    
                    self.data.append((ts, price))
                except (ValueError, KeyError) as e:
                    # Skip malformed rows
                    print(f"Warning: Skipping malformed row in {self.csv_path}: {row} ({e})")
                    continue
                    
        # Sort by timestamp to enable binary search
        self.data.sort(key=lambda x: x[0])
        print(f"Loaded {len(self.data)} price points for {self.instrument} from {self.csv_path}")

    def get_execution_price(self, instrument: str, as_of: datetime, side: str, quantity: float) -> Optional[float]:
        """Estimate execution price used mark price (zero slippage model)."""
        return self.get_mark_price(instrument, as_of)

    def get_bid_ask(self, instrument: str, as_of: datetime) -> Optional[tuple[float, float]]:
        """Return fake bid/ask spread (zero spread) around mark price."""
        price = self.get_mark_price(instrument, as_of)
        if price is None:
            return None
        return (price, price)

    def get_mark_price(self, instrument: str, as_of: datetime) -> Optional[float]:
        """Get mark price with forward fill."""
        if instrument != self.instrument:
            return None
        
        if not self.data:
            return None
            
        # Binary search for the rightmost timestamp <= requested timestamp
        timestamps = [x[0] for x in self.data]
        idx = bisect.bisect_right(timestamps, as_of)
        
        if idx == 0:
            # Requested time is before first data point
            return None
            
        best_match = self.data[idx - 1]
        return best_match[1]


class StaticMarketDataProvider(MarketDataProvider):
    """Static market data provider for testing/simulation.
    
    returns prices from offset dictionary.
    """
    
    def __init__(self, prices: Dict[str, float]):
        """Initialize with a map of instrument -> price."""
        self.prices = prices
        
    def get_mark_price(self, instrument: str, as_of: datetime) -> Optional[float]:
        return self.prices.get(instrument)

    def get_execution_price(self, instrument: str, as_of: datetime, side: str, quantity: float) -> Optional[float]:
        return self.prices.get(instrument)

    def get_bid_ask(self, instrument: str, as_of: datetime) -> Optional[tuple[float, float]]:
        p = self.prices.get(instrument)
        return (p, p) if p else None
