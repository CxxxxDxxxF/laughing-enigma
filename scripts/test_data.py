#!/usr/bin/env python3
"""Test data fetch with IEX feed."""

import os
from pathlib import Path
from datetime import datetime, timedelta
import zoneinfo

# Load env
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            os.environ[key.strip()] = val.strip()

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

tz = zoneinfo.ZoneInfo('America/New_York')
now = datetime.now(tz)
print('=' * 60)
print(f'  DATA FETCH TEST - {now.strftime("%Y-%m-%d %H:%M:%S %Z")}')
print('=' * 60)

data_client = StockHistoricalDataClient(api_key, secret_key)

tickers = ['NVDA', 'TSLA', 'AAPL', 'AMD']
print('\nFetching stock data with IEX feed...')

for symbol in tickers:
    try:
        end = datetime.now(tz)
        start = end - timedelta(days=5)
        
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
            limit=50,
            feed=DataFeed.IEX
        )
        
        bars = data_client.get_stock_bars(request)
        
        if symbol in bars and len(bars[symbol]) > 0:
            count = len(bars[symbol])
            last_price = float(bars[symbol][-1].close)
            print(f'  {symbol}: [OK] {count} bars, last price ${last_price:.2f}')
        else:
            print(f'  {symbol}: [!] No data in response')
    except Exception as e:
        print(f'  {symbol}: [X] Error - {e}')

print('\n[OK] Data fetch test complete')
print('=' * 60)
