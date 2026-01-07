import sys
import shutil
import csv
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.providers import FileReplayMarketDataProvider

def test_file_replay_provider():
    print("="*50)
    print("Verifying File Replay Market Data Provider")
    print("="*50)
    
    # 1. Setup Test CSV
    test_dir = Path("./artifacts_test_provider")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    
    csv_path = test_dir / "prices.csv"
    
    # Create sample data: T0, T+10m, T+20m
    t0 = datetime(2024, 1, 1, 10, 0, 0)
    data = [
        (t0, 100.0),
        (t0 + timedelta(minutes=10), 101.0),
        (t0 + timedelta(minutes=20), 102.0),
        (t0 + timedelta(minutes=30), 103.0),
    ]
    
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "close"])
        for ts, price in data:
            writer.writerow([ts.isoformat(), price])
            
    print(f"Created test CSV at {csv_path}")
    
    # 2. Initialize Provider
    provider = FileReplayMarketDataProvider(str(csv_path), "AAPL")
    
    # 3. Test Cases for Forward Fill
    
    # Case A: Exact Match
    target = t0 + timedelta(minutes=10)
    price = provider.get_mark_price("AAPL", target)
    print(f"Case A (Exact Match): {target} -> {price}")
    assert abs(price - 101.0) < 0.001, f"Expected 101.0, got {price}"
    
    # Case B: Between points (Forward Fill)
    # T+15m should forward-fill from T+10m (101.0)
    target = t0 + timedelta(minutes=15)
    price = provider.get_mark_price("AAPL", target)
    print(f"Case B (Between): {target} -> {price}")
    assert abs(price - 101.0) < 0.001, f"Expected 101.0, got {price}"
    
    # Case C: After last point
    # T+60m should fill from T+30m (103.0)
    target = t0 + timedelta(minutes=60)
    price = provider.get_mark_price("AAPL", target)
    print(f"Case C (After Last): {target} -> {price}")
    assert abs(price - 103.0) < 0.001, f"Expected 103.0, got {price}"
    
    # Case D: Before first point
    # T-5m should return None
    target = t0 - timedelta(minutes=5)
    price = provider.get_mark_price("AAPL", target)
    print(f"Case D (Before First): {target} -> {price}")
    assert price is None, f"Expected None, got {price}"
    
    # Case E: Wrong Instrument
    price = provider.get_mark_price("GOOG", t0)
    print(f"Case E (Wrong Inst): GOOG -> {price}")
    assert price is None, f"Expected None, got {price}"
    
    print("\nSUCCESS: All replay provider logic verified.")
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_file_replay_provider()
