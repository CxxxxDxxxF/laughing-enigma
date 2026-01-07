"""Live execution engine implementation using Alpaca.

This module provides the live execution engine that interfaces with
Alpaca brokerage for real trading.
"""

import time
import logging
from typing import Dict, List, Optional
from datetime import datetime
import uuid

from .signal import Signal, SignalType
from .order import Order, OrderStatus, OrderType, OrderSide
from .fill import Fill
from .position import Position
from .engine import ExecutionEngine, ExecutionEngineError, OrderRejectionError, RiskLimitExceededError, RiskLimits
from .alpaca_client import AlpacaClient, AlpacaClientError

logger = logging.getLogger(__name__)


class LiveExecutionEngine(ExecutionEngine):
    """Live execution engine using Alpaca API.
    
    Translates internal Signals to Alpaca Orders and tracks execution.
    """
    

    def __init__(
        self,
        instrument: Optional[str] = None,  # Optional validation
        alpaca_client: Optional[AlpacaClient] = None,
        risk_limits: Optional[RiskLimits] = None,
        force_trades: bool = True
    ):
        """Initialize live execution engine.
        
        Args:
            instrument: Optional instrument to restrict trading to
            alpaca_client: AlpacaClient instance
            risk_limits: Risk limits configuration
            force_trades: If False, orders will be "accepted" locally but not sent to Alpaca.
        """
        self.instrument = instrument
        self.client = alpaca_client or AlpacaClient()
        self.risk_limits = risk_limits or RiskLimits()
        self.session_id = f"live_{uuid.uuid4().hex[:8]}"
        self.force_trades = force_trades
        
        # Ensure connection
        if not self.client.is_connected:
            try:
                self.client.connect()
            except AlpacaClientError as e:
                logger.warning(f"Failed to connect to Alpaca on init: {e}")
                
        # Cache for order tracking
        self._local_orders: Dict[str, Order] = {}
        self._broker_order_ids: Dict[str, str] = {}  # local_id -> broker_id
        self._fills: Dict[str, List[Fill]] = {}      # local_id -> List[Fill]
        
    def submit_order(self, signal: Signal) -> Order:
        """Submit an order to Alpaca.
        
        Args:
            signal: Signal to convert to order
            
        Returns:
            Order with status ACCEPTED or REJECTED
            
        Raises:
            ExecutionEngineError: If order submission fails
        """
        # 1. Validate instrument
        if self.instrument and signal.instrument != self.instrument:
            raise OrderRejectionError(f"Engine restricted to {self.instrument}, got {signal.instrument}")
            
        if self.risk_limits and not self.risk_limits.is_instrument_allowed(signal.instrument):
            raise RiskLimitExceededError(f"Instrument {signal.instrument} not allow-listed")
            
        # 2. Create local order object
        import dataclasses
        order = Order(
            id=str(uuid.uuid4()),
            instrument=signal.instrument,
            quantity=signal.quantity,
            side=OrderSide.BUY.value if signal.quantity > 0 else OrderSide.SELL.value,
            order_type=OrderType.MARKET,  # MVP: Market orders only
            signal_id=signal.strategy_id
        )
        # If trades are disabled, skip Alpaca submission
        if not self.force_trades:
            order = dataclasses.replace(order, status=OrderStatus.ACCEPTED, accepted_at=datetime.now())
            self._local_orders[order.id] = order
            return order
        
        # 3. Submit to Alpaca
        try:
            # We used alpaca-py client in the wrapper
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide as AlpacaOrderSide, TimeInForce
            
            req = MarketOrderRequest(
                symbol=signal.instrument,
                qty=abs(signal.quantity),
                side=AlpacaOrderSide.BUY if signal.quantity > 0 else AlpacaOrderSide.SELL,
                time_in_force=TimeInForce.DAY
            )
            
            alpaca_order = self.client._trading_client.submit_order(req)
            
            # Update local order with Alpaca ID
            order = dataclasses.replace(order, status=OrderStatus.ACCEPTED, accepted_at=datetime.now())
            self._broker_order_ids[order.id] = str(alpaca_order.id)
            self._local_orders[order.id] = order
            return order
            
        except Exception as e:
            logger.error(f"Alpaca order submission failed: {e}")
            order = dataclasses.replace(order, status=OrderStatus.REJECTED, rejection_reason=str(e))
            self._local_orders[order.id] = order
            return order

    def execute_order(self, order: Order, current_price: float, timestamp: Optional[datetime] = None) -> List[Fill]:
        """Check status of submitted order and return fills.
        
        In simulation, this *performs* the execution.
        In live, this *checks* the execution.
        
        Args:
            order: Order to check
            current_price: Unused in live mode (price determined by market)
            timestamp: Unused
            
        Returns:
            List of Fills (if executed)
        """
        if order.status not in (OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED):
             return []
             
        broker_id = self._broker_order_ids.get(order.id)
        if not broker_id:
            # If force_trades is False, we never submitted, so no broker ID.
            # We treat this as "no fill yet" or could simulate fill if we wanted.
            # For now, return empty to simulate pending/hold. 
            if not self.force_trades:
                return [] 
            logger.warning(f"Order {order.id} has no broker ID to check")
            return []
            
        try:
            # Poll Alpaca for status
            time.sleep(1) 
            
            alpaca_order = self.client._trading_client.get_order_by_id(broker_id)
            
            # Check status
            status = str(alpaca_order.status)
            import dataclasses
            
            if status == 'filled':
                
                # Retrieve filled price/qty
                fill_price = float(alpaca_order.filled_avg_price) if alpaca_order.filled_avg_price else current_price
                fill_qty = float(alpaca_order.filled_qty)
                
                # Create fill object
                fill = Fill(
                    fill_id=f"fill_{broker_id}",
                    order_id=order.id,
                    instrument=order.instrument,
                    side=order.side,  # kept as string now
                    quantity=fill_qty if order.side == "buy" else -fill_qty,
                    price=fill_price,
                    timestamp=alpaca_order.filled_at or datetime.now(),
                    fee=0.0 # TODO: Retrieve fees if available
                )
                
                # Update order
                order = dataclasses.replace(order, status=OrderStatus.FILLED, filled_at=fill.timestamp)
                self._local_orders[order.id] = order
                
                # Store fill
                if order.id not in self._fills:
                    self._fills[order.id] = []
                self._fills[order.id].append(fill)
                
                return [fill]
                
            elif status in ('canceled', 'expired', 'rejected'):
                new_status = OrderStatus.CANCELED if status == 'canceled' else OrderStatus.REJECTED
                order = dataclasses.replace(order, status=new_status)
                self._local_orders[order.id] = order
                return []
                
            # Still pending/new/accepted
            return []
            
        except Exception as e:
            logger.error(f"Failed to check execution for order {order.id}: {e}")
            return []

    def cancel_order(self, order_id: str) -> Order:
        """Cancel an order on Alpaca."""
        # Find local order
        order = self.get_order(order_id)
        if not order:
             raise ValueError(f"Order {order_id} not found")
             
        broker_id = self._broker_order_ids.get(order.id)
        if not broker_id:
             return order # Can't cancel what wasn't submitted
             
        try:
            self.client._trading_client.cancel_order_by_id(broker_id)
            import dataclasses
            order = dataclasses.replace(order, status=OrderStatus.CANCELED)
            self._local_orders[order.id] = order
            return order
        except Exception as e:
            raise ExecutionEngineError(f"Failed to cancel order: {e}")

    def sync_portfolio_state(self, state: 'CurrentPortfolioState') -> 'CurrentPortfolioState':
        """Sync state with Alpaca account."""
        try:
            account = self.client.get_account()
            
            import dataclasses
            # Update capital and cash from Alpaca
            # account.equity is total account value
            # account.cash is available cash (using cash instead of buying_power for conservative measure)
            new_state = dataclasses.replace(
                state,
                total_capital=float(account.equity),
                cash_balance=float(account.cash)
            )
            logger.info(f"Synced portfolio state with Alpaca: Cash=${new_state.cash_balance:.2f}, Equity=${new_state.total_capital:.2f}")
            return new_state
            
        except Exception as e:
            logger.error(f"Failed to sync portfolio state: {e}")
            return state

    def get_position(self, instrument: str) -> Position:
        """Get live position from Alpaca."""
        try:
            alpaca_positions = self.client.get_positions()
            for pos in alpaca_positions:
                if pos.symbol == instrument:
                    return Position(
                        instrument=instrument,
                        quantity=float(pos.qty) if pos.side == 'long' else -float(pos.qty),
                        cost_basis=float(pos.avg_entry_price)
                    )
            # Not found = no position
            return Position(instrument=instrument, quantity=0.0, cost_basis=0.0)
            
        except Exception as e:
            logger.error(f"Failed to get position for {instrument}: {e}")
            raise ExecutionEngineError(f"Failed to sync position: {e}")

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order from local cache (Alpaca history sync is expensive)."""
        return self._local_orders.get(order_id)

    def list_orders(self, instrument: Optional[str] = None, status: Optional[str] = None) -> List[Order]:
        """List local orders."""
        orders = list(self._local_orders.values())
        if instrument:
            orders = [o for o in orders if o.instrument == instrument]
        if status:
            # Simple status mapping 
            pass 
        return orders

    def get_fills(self, order_id: str) -> List[Fill]:
        """Get fills for local order."""
        return self._fills.get(order_id, [])

    def reset(self) -> None:
        """Reset local state (does not affect Alpaca account!)."""
        self._local_orders.clear()
        self._broker_order_ids.clear()
        self._fills.clear()


