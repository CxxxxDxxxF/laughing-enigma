#!/usr/bin/env python3
"""
ADVERSARIAL TESTS (Step D)

Validates:
1. Lock contention (Process B cannot write while Process A runs)
2. Corrupt state recovery (broken JSON)
3. Missing fields (partial state)
"""

import sys
import shutil
import time
import json
import multiprocessing
import traceback
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.state_store import StateStore, OrderIntent

def hold_lock_process(state_dir: str, duration: int):
    """Child process that holds the lock."""
    try:
        store = StateStore(state_dir=state_dir)
        print(f"[Child] Acquired lock. Sleeping {duration}s...")
        time.sleep(duration)
        print("[Child] Releasing lock.")
    except Exception as e:
        print(f"[Child] Failed to acquire lock: {e}")
        sys.exit(1)

def test_lock_contention():
    print("\n[TEST 1] Lock Contention")
    print("-" * 60)
    
    test_dir = Path("./test_lock_adv")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()
    
    # Spawn child to hold lock
    p = multiprocessing.Process(target=hold_lock_process, args=(str(test_dir), 2))
    p.start()
    
    time.sleep(0.5) # Give child time to acquire
    
    try:
        print("[Main] Attempting to acquire lock (should fail)...")
        store = StateStore(state_dir=str(test_dir))
        print("[FAIL] Main process acquired lock despite child holding it!")
        sys.exit(1)
    except RuntimeError as e:
        print(f"[OK] Main process blocked: {e}")
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        traceback.print_exc()
    
    p.join()
    
    # Should succeed now
    try:
        print("[Main] Attempting to acquire lock after child release...")
        store = StateStore(state_dir=str(test_dir))
        print("[OK] Lock acquired successfully")
    except Exception as e:
        print(f"[FAIL] Could not acquire lock after release: {e}")

    shutil.rmtree(test_dir)


def test_corrupt_state():
    print("\n[TEST 2] Corrupt State Recovery")
    print("-" * 60)
    
    test_dir = Path("./test_corrupt_adv")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    
    store = StateStore(state_dir=str(test_dir))
    
    # 1. Write valid state
    intent = OrderIntent.create("BTC/USD", "buy", 1.0)
    store.register_intent(intent, "valid_order")
    del store # Release lock
    
    # 2. Corrupt the file
    state_file = test_dir / "trading_state.json"
    with open(state_file, "w") as f:
        f.write("{ invalid_json: ... truncated")
    
    print("[Main] Wrote corrupt JSON to state file.")
    
    # 3. specific behavior check: 
    # Current implementation returns empty state on load error
    store = StateStore(state_dir=str(test_dir))
    state = store.load_state()
    
    assert len(state.pending_orders) == 0
    assert state.version == "2.0.0" # Default version
    print("[OK] Corrupt file handled (Fallback to clean state)")
    
    # 4. Partial State (Missing fields)
    del store
    with open(state_file, "w") as f:
        # valid json but missing keys
        json.dump({"version": "1.0.0", "random_field": 123}, f)
        
    store = StateStore(state_dir=str(test_dir))
    state = store.load_state()
    
    # Check if defaults populated
    assert state.positions == {}
    assert state.pending_orders == {}
    print("[OK] Partial state populated with defaults")
    
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_lock_contention()
    test_corrupt_state()
    print("\n[SUCCESS] Adversarial tests verified.")
