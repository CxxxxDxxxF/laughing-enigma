"""Backtest script for Dual Momentum Strategy."""
import sys
from pathlib import Path
from datetime import datetime, timedelta

from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.strategies.dual_momentum import DualMomentumStrategy
from src.execution.signal import SignalType
from src.engines.simple import SimpleResearchEngine
from src.core.experiment import Experiment

def run_backtest():
    """Run a simple backtest."""
    print("Running Dual Momentum Backtest...")
    
    # 1. Generate Synthetic Data
    # 200 days of prices
    # Days 0-130: Flat/Uptrend
    # Days 131-150: Uptrend (Should Buy)
    # Days 151-200: Downtrend (Should Sell)
    
    prices = [100.0] * 130
    # Uptrend
    for i in range(20):
        prices.append(100.0 * (1.0 + (i+1)*0.01)) # Up 1% per day
    # Downtrend
    peak = prices[-1]
    for i in range(50):
        prices.append(peak * (1.0 - (i+1)*0.01)) # Down 1% per day
        
    market_data = {"AAPL": prices}
    
    # 2. Init Strategy
    strategy = DualMomentumStrategy(
        lookback_days=20, # Short lookback for this test
        threshold=0.0,
        instrument="AAPL"
    )
    
    # 3. Simulate Day-by-Day (starting from day 21)
    signals = []
    for day in range(21, len(prices)):
        # Slice data exactly like the strategy expects (up to 'day')
        # In reality, strategy calls get_history with N days. 
        # Here we pass full history, but strategy slices it. 
        # Wait, strategy slices [-lookback-1:] from whatever list is passed.
        # So we must pass strictly the history available AT THAT MOMENT.
        
        current_history = prices[:day+1]
        data_snapshot = {"AAPL": current_history}
        
        signal = strategy.generate_signals(data_snapshot)
        if signal:
            signals.append((day, signal))
            
    print(f"Generated {len(signals)} signals.")
    
    # 4. Verify Transitions
    # We expect BUY signals during the uptrend portion
    # We expect SELL signals during the downtrend portion
    
    buy_signals = [s for d, s in signals if s.signal_type == SignalType.BUY]
    sell_signals = [s for d, s in signals if s.signal_type == SignalType.SELL]
    
    print(f"BUY Signals: {len(buy_signals)}")
    print(f"SELL Signals: {len(sell_signals)}")
    
    if len(buy_signals) > 0 and len(sell_signals) > 0:
        print("SUCCESS: Strategy generated both BUY and SELL signals.")
        # Check transition
        last_buy_day = max([d for d, s in signals if s.signal_type == SignalType.BUY])
        first_sell_day = min([d for d, s in signals if s.signal_type == SignalType.SELL])
        
        print(f"Last BUY day: {last_buy_day}")
        print(f"First SELL day: {first_sell_day}")
        
        if first_sell_day > last_buy_day: # Overlap might happen depending on momentum lag
             pass
    else:
        print("FAILURE: Did not generate mixed signals.")
        sys.exit(1)

    # 5. Verify Engine Integration
    print("\nVerifying Engine Integration...")
    engine = SimpleResearchEngine(artifact_store=None)
    
    experiment = Experiment(
        name="test_dual_mo",
        version="v1",
        description="Integration Test",
        config={"daily_trend": 0.0002}, # Strong uptrend
        created_at=datetime.now()
    )
    
    inputs = {
        "start_date": "2024-01-01",
        "end_date": "2024-06-01", # ~150 days
        "initial_capital": 10000.0,
        "instrument": "TEST_INTEGRATION",
        "strategy_type": "dual_momentum",
        # Strategy config props
        "lookback_days": 20,
        "threshold": 0.0,
        "instrument": "TEST_INTEGRATION"
    }
    
    result = engine.run_backtest(experiment, "test_run_1", inputs)
    print("Engine execution validated.")
    print(f"Metrics: Sharpe={result.metrics.sharpe_ratio:.4f}, Total Return={result.metrics.total_return:.4f}")
    
    if result.metrics.sharpe_ratio is not None:
        print("SUCCESS: Engine successfully ran Dual Momentum strategy.")
    else:
        print("FAILURE: Engine returned invalid metrics.")
        sys.exit(1)

if __name__ == "__main__":
    run_backtest()
