"""CSV-based data provider for offline backtesting.

Load historical data from local CSV files for fast, reproducible backtesting
without any network dependencies.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
import pandas as pd


class CSVDataProvider:
    """Load market data from local CSV files.
    
    Perfect for reproducible backtesting with pre-downloaded data.
    """
    
    def __init__(self, data_dir: str = "data/historical"):
        self.data_dir = Path(data_dir)
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._cache: Dict[str, pd.DataFrame] = {}
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """Load historical data from CSV.
        
        Args:
            symbol: Ticker symbol (matches filename without .csv)
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            DataFrame with OHLCV data
        """
        # Check cache first
        if symbol in self._cache:
            df = self._cache[symbol].copy()
        else:
            filepath = self.data_dir / f"{symbol}.csv"
            
            if not filepath.exists():
                raise FileNotFoundError(
                    f"No data file for {symbol}. "
                    f"Expected: {filepath}"
                )
            
            df = pd.read_csv(filepath, index_col=0, parse_dates=True)
            df.columns = [c.lower() for c in df.columns]
            self._cache[symbol] = df
            df = df.copy()
        
        # Apply date filters
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]
        
        return df
    
    def get_latest_price(self, symbol: str) -> float:
        """Get the most recent price from cached data.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Latest closing price
        """
        df = self.get_historical_data(symbol)
        if df.empty:
            raise ValueError(f"No data for {symbol}")
        return float(df['close'].iloc[-1])
    
    def list_available_symbols(self) -> List[str]:
        """List all symbols with available data.
        
        Returns:
            List of symbol names
        """
        return [f.stem for f in self.data_dir.glob("*.csv")]
    
    def preload_symbols(self, symbols: List[str]) -> None:
        """Preload symbols into cache for faster access.
        
        Args:
            symbols: List of symbols to preload
        """
        for symbol in symbols:
            try:
                self.get_historical_data(symbol)
            except FileNotFoundError:
                print(f"Warning: {symbol} not found")
    
    def clear_cache(self) -> None:
        """Clear the data cache."""
        self._cache.clear()


class ReplayDataProvider:
    """Replay historical data bar-by-bar for simulation.
    
    Useful for step-through backtesting where you need to
    simulate receiving data in real-time order.
    """
    
    def __init__(self, csv_provider: CSVDataProvider, symbols: List[str]):
        self.csv_provider = csv_provider
        self.symbols = symbols
        self._data: Dict[str, pd.DataFrame] = {}
        self._current_idx = 0
        self._load_data()
    
    def _load_data(self):
        """Load all data and align indices."""
        for symbol in self.symbols:
            try:
                self._data[symbol] = self.csv_provider.get_historical_data(symbol)
            except FileNotFoundError:
                print(f"Warning: {symbol} not available")
    
    def reset(self):
        """Reset replay to beginning."""
        self._current_idx = 0
    
    def get_next_bar(self) -> Optional[Dict[str, Dict]]:
        """Get the next bar for all symbols.
        
        Returns:
            Dict mapping symbol -> bar data, or None if exhausted
        """
        result = {}
        
        for symbol, df in self._data.items():
            if self._current_idx < len(df):
                row = df.iloc[self._current_idx]
                result[symbol] = {
                    'timestamp': df.index[self._current_idx],
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': float(row['volume'])
                }
        
        if not result:
            return None
        
        self._current_idx += 1
        return result
    
    def __iter__(self):
        self.reset()
        return self
    
    def __next__(self):
        bar = self.get_next_bar()
        if bar is None:
            raise StopIteration
        return bar
