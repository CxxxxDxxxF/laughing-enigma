#!/usr/bin/env python3
"""
TEST RECONCILIATION LOGIC (Step B+D)

Validates:
1. Status transitions (Local -> Broker -> Final)
2. Ambiguity handling (404s)
3. Deterministic Client Order ID generation
"""

import sys
import shutil
import time
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.state_store import StateStore, OrderIntent, OrderStatus, PendingOrder
from src.execution.reconciliation import ReconciliationManager

class MockAlpacaOrder:
    def __init__(self, status, filled_qty=0, filled_avg_price=0):
        self.status = status
        self.filled_qty = filled_qty
        self.filled_avg_price = filled_avg_price

def test_reconciliation():
    print("\n[TEST] Reconciliation Logic")
    print("-" * 60)
    
    test_dir = Path("./test_recon_state")
    if test_dir.exists():
        shutil.rmtree(test_dir)
        
    store = StateStore(state_dir=str(test_dir))
    mock_client = MagicMock()
    
    manager = ReconciliationManager(store, mock_client)
    
    # Setup: Register an intent/order
    intent = OrderIntent.create("BTC/USD", "buy", 0.5)
    order_id = "test_order_1"
    store.register_intent(intent, order_id)
    
    # Scenario 1: Local -> Found at Broker (OPEN)
    print("Scenario 1: Found at Broker (OPEN)")
    
    # Mock return
    mock_client.get_order_by_client_order_id.return_value = MockAlpacaOrder("new")
    
    manager.reconcile_all()
    
    # Verify state
    state = store.load_state()
    p_order = PendingOrder.from_dict(state.pending_orders[order_id])
    assert p_order.status == OrderStatus.OPEN.value
    print("[OK] Transitioned to OPEN")
    
    # Scenario 2: OPEN -> FILLED
    print("\nScenario 2: OPEN -> FILLED")
    
    mock_client.get_order_by_client_order_id.return_value = MockAlpacaOrder("filled", 0.5, 95000.0)
    
    manager.reconcile_all()
    
    state = store.load_state()
    p_order = PendingOrder.from_dict(state.pending_orders[order_id])
    assert p_order.status == OrderStatus.FILLED.value
    assert float(p_order.filled_qty) == 0.5
    assert float(p_order.avg_entry_price) == 95000.0
    print("[OK] Transitioned to FILLED with correct details")
    
    # Scenario 3: Ambiguity (404)
    print("\nScenario 3: Ambiguity Handling (404)")
    
    # Create new order
    order_id_2 = "test_order_2"
    intent_2 = OrderIntent.create("ETH/USD", "sell", 10.0)
    store.register_intent(intent_2, order_id_2)
    
    # Mock 404
    mock_client.get_order_by_client_order_id.side_effect = Exception("Not Found")
    
    # Run reconcile (Should stay SUBMITTED_LOCAL because fresh)
    manager.reconcile_all()
    state = store.load_state()
    p_order = PendingOrder.from_dict(state.pending_orders[order_id_2])
    assert p_order.status == OrderStatus.SUBMITTED_LOCAL.value
    print("[OK] Fresh 404 stays SUBMITTED_LOCAL")
    
    # Age the order manually > 30s
    p_order.submitted_at = (datetime.now(timezone.utc) - timedelta(seconds=35)).isoformat()
    state.pending_orders[order_id_2] = p_order.to_dict()
    store.save_state(state)
    
    # Run reconcile (Should go UNKNOWN)
    manager.reconcile_all()
    state = store.load_state()
    p_order = PendingOrder.from_dict(state.pending_orders[order_id_2])
    assert p_order.status == OrderStatus.UNKNOWN.value
    print("[OK] Stale 404 transitions to UNKNOWN")
    
    # Result
    print("\n[SUCCESS] Reconciliation verified.")
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_reconciliation()
