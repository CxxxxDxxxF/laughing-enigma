
import os
from datetime import datetime, timedelta, timezone
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

def check_momentum():
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    client = StockHistoricalDataClient(api_key, secret_key)
    
    # Needs to cover 126 trading days + buffer ~ 190 calendar days
    start_date = datetime.now(timezone.utc) - timedelta(days=250)
    
    req = StockBarsRequest(
        symbol_or_symbols=["SPY"],
        timeframe=TimeFrame.Day,
        start=start_date
    )
    
    bars = client.get_stock_bars(req).df
    bars = bars.reset_index()
    
    # Sort
    if 'timestamp' in bars.columns:
        bars = bars.sort_values('timestamp')
    elif 'time' in bars.columns:
        bars = bars.sort_values('time')
        
    # Get last price
    current_price = bars.iloc[-1]['close']
    
    # Get price 126 days ago (trading days)
    if len(bars) > 126:
        past_price = bars.iloc[-127]['close'] # 126 lookback index
        momentum = (current_price / past_price) - 1.0
        
        print(f"Current Price: {current_price}")
        print(f"Price 126 days ago: {past_price}")
        print(f"Momentum (6-mo return): {momentum*100:.2f}%")
        
        if momentum > 0.05:
            print("Action: BUY (Strong Trend > 5%)")
        elif momentum > 0.0:
            print("Action: SELL (Weak Trend < 5%) - Conservative Mode")
            print("Action: BUY (Standard Mode > 0%)")
        else:
            print("Action: SELL (Negative Trend)")
    else:
        print("Not enough data")

if __name__ == "__main__":
    check_momentum()
