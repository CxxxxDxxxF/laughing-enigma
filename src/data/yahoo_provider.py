"""Yahoo Finance data provider for backtesting.

Provides free historical market data using the yfinance library.
No API key required - perfect for backtesting without broker dependency.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import pandas as pd

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    yf = None


class YahooFinanceProvider:
    """Market data provider using Yahoo Finance.
    
    Free historical data for stocks, ETFs, and indices.
    No API key required.
    """
    
    def __init__(self):
        if not YFINANCE_AVAILABLE:
            raise ImportError(
                "yfinance not installed. Run: pip install yfinance"
            )
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: Optional[datetime] = None,
        interval: str = "1d"
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data.
        
        Args:
            symbol: Ticker symbol (e.g., "SPY", "AAPL")
            start_date: Start date for data
            end_date: End date (defaults to today)
            interval: Data interval - 1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo
            
        Returns:
            DataFrame with columns: Open, High, Low, Close, Volume
        """
        end_date = end_date or datetime.now()
        
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval=interval
        )
        
        # Standardize column names
        df.columns = [c.lower() for c in df.columns]
        
        return df[['open', 'high', 'low', 'close', 'volume']]
    
    def get_latest_price(self, symbol: str) -> float:
        """Get the most recent closing price.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Latest closing price
        """
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d")
        
        if hist.empty:
            raise ValueError(f"No data available for {symbol}")
        
        return float(hist['Close'].iloc[-1])
    
    def get_multiple_symbols(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: Optional[datetime] = None,
        interval: str = "1d"
    ) -> Dict[str, pd.DataFrame]:
        """Fetch historical data for multiple symbols.
        
        Args:
            symbols: List of ticker symbols
            start_date: Start date
            end_date: End date
            interval: Data interval
            
        Returns:
            Dict mapping symbol -> DataFrame
        """
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = self.get_historical_data(
                    symbol, start_date, end_date, interval
                )
            except Exception as e:
                print(f"Warning: Failed to fetch {symbol}: {e}")
        
        return result
    
    def get_info(self, symbol: str) -> Dict[str, Any]:
        """Get ticker info and metadata.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Dict with company info, sector, etc.
        """
        ticker = yf.Ticker(symbol)
        return ticker.info


def download_backtest_data(
    symbols: List[str],
    years: int = 5,
    output_dir: str = "data/historical"
) -> None:
    """Download and save historical data for backtesting.
    
    Args:
        symbols: List of symbols to download
        years: Number of years of history
        output_dir: Directory to save CSV files
    """
    from pathlib import Path
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    provider = YahooFinanceProvider()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365)
    
    for symbol in symbols:
        try:
            df = provider.get_historical_data(symbol, start_date, end_date)
            filepath = output_path / f"{symbol}.csv"
            df.to_csv(filepath)
            print(f"✓ Downloaded {symbol}: {len(df)} rows -> {filepath}")
        except Exception as e:
            print(f"✗ Failed {symbol}: {e}")


if __name__ == "__main__":
    # Quick test
    download_backtest_data(["SPY", "QQQ", "IWM"], years=5)
