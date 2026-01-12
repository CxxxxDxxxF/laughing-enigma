#!/usr/bin/env python3
"""
TEST IDEMPOTENCY REDESIGN (Step A)

Validates:
1. Canonicalization of OrderIntent (qty precision, casing)
2. Intent Registry persistence
3. Duplicate blocking
"""
import sys
import shutil
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.state_store import StateStore, OrderIntent, OrderStatus, TradingState

def test_canonicalization():
    print("\n[TEST 1] Canonicalization Logic")
    print("-" * 60)
    
    # Case 1: Quantity precisions
    intent1 = OrderIntent.create("BTC/USD", "buy", 0.12345678, "limit", 95000.50)
    intent2 = OrderIntent.create("btc/usd", "BUY", "0.123456789", "Limit", "95000.5000")
    
    key1 = intent1.intent_key()
    key2 = intent2.intent_key()
    
    print(f"Key 1: {key1}")
    print(f"Key 2: {key2}")
    
    parts1 = key1.split("|")
    # symbol|side|qty|type|limit|stop|strat|signal_ts
    assert parts1[0] == "BTC/USD"
    assert parts1[1] == "buy"
    assert parts1[2] == "0.12345678"  # 8 decimals, truncated 9
    assert parts1[3] == "limit"
    assert parts1[4] == "95000.50"    # 2 decimals for price
    
    assert key1 == key2
    print("[OK] Canonicalization handles casing and precision correctly.")

    # Case 2: Market vs Limit fields
    intent_mkt = OrderIntent.create("ETH/USD", "sell", 1.0, "market")
    key_mkt = intent_mkt.intent_key()
    print(f"Market Key: {key_mkt}")
    assert "NONE" in key_mkt  # Limit and Stop should be NONE

    
def test_persistence_and_blocking():
    print("\n[TEST 2] Persistence & Duplicate Blocking")
    print("-" * 60)
    
    test_dir = Path("./test_state_v2")
    if test_dir.exists():
        shutil.rmtree(test_dir)
        
    store = StateStore(state_dir=str(test_dir))
    
    # create intent
    intent = OrderIntent.create("SOL/USD", "buy", 10.0)
    print(f"Intent Key: {intent.intent_key()}")
    
    # 1. Check - should be None
    existing = store.check_idempotency(intent)
    assert existing is None
    print("[OK] New intent not found.")
    
    # 2. Register
    order_id = "sol_order_1"
    store.register_intent(intent, order_id)
    print(f"[OK] Registered intent -> {order_id}")
    
    # 3. Check again
    existing = store.check_idempotency(intent)
    assert existing is not None
    assert existing["order_id"] == order_id
    print(f"[OK] Found existing: {existing}")
    
    # 4. Simulate Restart
    del store
    store_new = StateStore(state_dir=str(test_dir))
    
    # 5. Check duplicate after restart
    dup = store_new.check_idempotency(intent)
    assert dup is not None
    assert dup["order_id"] == order_id
    print("[OK] Duplicate detection survives restart.")
    
    # Cleanup
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_canonicalization()
    test_persistence_and_blocking()
    print("\n[SUCCESS] Step A verified.")
