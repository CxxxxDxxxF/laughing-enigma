#!/usr/bin/env python3
"""
RECONCILIATION LAYER (Step B)

Ensures state consistency between local persistence and broker.
Handles:
1. 8-state order lifecycle (Submitted -> Filled/Dead)
2. Deterministic recovery from "Submitted Local" state
3. Re-submit policies (budgets, ambiguity checks)
"""

import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from ..core.state_store import StateStore, OrderStatus, PendingOrder, TradingState, OrderIntent

# If using Alpaca SDK
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderStatus as AlpacaStatus

logger = logging.getLogger("Reconciler")

class ReconciliationManager:
    """
    Manages order lifecycle and broker sync.
    """
    def __init__(self, state_store: StateStore, trading_client: TradingClient):
        self.store = state_store
        self.client = trading_client
        self.re_submit_budget = 3  # Max re-submissions per hour? Or per order?
        
    def generate_client_order_id(self, intent: OrderIntent) -> str:
        """
        Deterministic Client Order ID from intent key.
        Max 48 chars allowed by Alpaca.
        Format: "bot_<short_hash>"
        """
        key = intent.intent_key().encode('utf-8')
        hash_digest = hashlib.sha256(key).hexdigest()[:32]
        return f"bot_{hash_digest}"

    def reconcile_all(self):
        """
        Main entry point. Reconciles all pending orders.
        """
        state = self.store.load_state()
        pending = list(state.pending_orders.values())
        
        for p_dict in pending:
            p_order = PendingOrder.from_dict(p_dict)
            self._reconcile_single_order(state, p_order)
            
        self.store.save_state(state)

    def _reconcile_single_order(self, state: TradingState, p_order: PendingOrder):
        """
        Advance state machine for a single order.
        """
        current_status = p_order.status
        
        # Terminal states - nothing to do (cleanup handled elsewhere)
        if current_status in [
            OrderStatus.FILLED.value, 
            OrderStatus.CANCELED.value, 
            OrderStatus.REJECTED.value, 
            OrderStatus.EXPIRED.value
        ]:
            return

        # Deterministic Client Order ID
        client_oid = self.generate_client_order_id(p_order.intent)
        
        try:
            # 1. Try to fetch order from broker by Client Order ID
            # This is the most reliable way to find "Submitted Local" orders
            alpaca_order = self.client.get_order_by_client_order_id(client_oid)
            
            # Found it! Update status
            self._update_from_broker_order(p_order, alpaca_order)
            state.pending_orders[p_order.order_id] = p_order.to_dict()
            return
            
        except Exception as e:
            # 404 means not found (common for SUBMITTED_LOCAL)
            # Other errors might be network issues
            if "not found" not in str(e).lower():
                logger.error(f"Error fetching order {client_oid}: {e}")
                return

        # 2. Not found on broker. Handle "Submitted Local" ambiguity
        if current_status == OrderStatus.SUBMITTED_LOCAL.value:
            self._handle_submitted_local_ambiguity(p_order)
            state.pending_orders[p_order.order_id] = p_order.to_dict()

        # 3. Handle "Open" but not found? (Broker lost it? We are out of sync?)
        elif current_status in [OrderStatus.OPEN.value, OrderStatus.PARTIALLY_FILLED.value]:
            logger.critical(f"Order {p_order.order_id} was OPEN locally but NOT FOUND at broker!")
            # This is a critical desync. Verify manually or mark Unknown.
            p_order.status = OrderStatus.UNKNOWN.value
            state.pending_orders[p_order.order_id] = p_order.to_dict()

    def _handle_submitted_local_ambiguity(self, p_order: PendingOrder):
        """
        Order was submitted locally but 404 at broker.
        Decide whether to retry or mark failed.
        """
        submitted_at = datetime.fromisoformat(p_order.submitted_at)
        now = datetime.now(timezone.utc)
        age_seconds = (now - submitted_at).total_seconds()
        
        # Wait at least 30s for propagation
        if age_seconds < 30:
            return # Keep Waiting
            
        # If > 30s and still 404, assume it failed to reach broker (or rejected silently)
        # Verify budget / re-submit policy
        # For now, mark as UNKNOWN or EXPIRED to safe-fail.
        # User policy: "Only re-submit if proven not received [and intent has no order id]"
        
        logger.warning(f"Order {p_order.order_id} (Local) not found at broker after {age_seconds:.1f}s. Marking UNKNOWN.")
        p_order.status = OrderStatus.UNKNOWN.value

    def _update_from_broker_order(self, p_order: PendingOrder, alpaca_order: Any):
        """
        Map Alpaca status to local status.
        """
        a_status = alpaca_order.status # Enum or string
        filled_qty = float(alpaca_order.filled_qty) if alpaca_order.filled_qty else 0.0
        filled_avg_price = float(alpaca_order.filled_avg_price) if alpaca_order.filled_avg_price else 0.0
        
        p_order.filled_qty = filled_qty
        p_order.avg_entry_price = filled_avg_price
        p_order.updated_at = datetime.now(timezone.utc).isoformat()
        
        # Status Mapping
        # Alpaca: new, partially_filled, filled, done_for_day, canceled, expired, replaced, pending_cancel, pending_replace, etc.
        status_map = {
            'new': OrderStatus.OPEN.value,
            'partially_filled': OrderStatus.PARTIALLY_FILLED.value,
            'filled': OrderStatus.FILLED.value,
            'canceled': OrderStatus.CANCELED.value,
            'expired': OrderStatus.EXPIRED.value,
            'rejected': OrderStatus.REJECTED.value,
            'replaced': OrderStatus.CANCELED.value, # Treat replacement as cancel + new? Or track chain?
            # For simplicity, if replaced, we might want to find the NEW order. 
            # But Alpaca returns the specific order we asked for.
        }
        
        # Handle string or enum
        s_val = str(a_status).lower().split('.')[-1] # "OrderSide.BUY" -> "buy"
        
        if s_val in status_map:
            p_order.status = status_map[s_val]
        else:
            p_order.status = OrderStatus.OPEN.value # Default to open if unknown active status
        
        if p_order.status == OrderStatus.FILLED.value:
            logger.info(f"Order {p_order.order_id} FILLED: {filled_qty} @ {filled_avg_price}")

