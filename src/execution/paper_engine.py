"""Paper trading execution engine implementation.

This module provides a deterministic paper trading execution engine
for single-instrument backtesting with market orders only.
"""

import json
from typing import Dict, List, Optional
from datetime import datetime

from .signal import Signal, SignalType
from .order import Order, OrderStatus, OrderType
from .fill import Fill
from .position import Position
from .engine import ExecutionEngine, ExecutionEngineError, OrderRejectionError, RiskLimitExceededError, RiskLimits
from .clock import ExecutionClock, SimulationClock
from .id_provider import IDProvider, SimulationIDProvider

try:
    from ..core.artifacts import ArtifactStore, ArtifactStoreError
except ImportError:
    # Allow import without core dependency for testing
    ArtifactStore = None
    ArtifactStoreError = Exception


class PaperExecutionEngine(ExecutionEngine):
    """Deterministic paper trading execution engine.
    
    This engine implements execution for paper trading with the following
    constraints:
    - Single instrument only
    - Market orders only (price_limit ignored, fills at current_price)
    - Immediate full fills (no partial fills)
    - Fixed fee model
    - Single position per instrument
    
    State is managed in-memory. Orders, fills, and positions are tracked
    and updated deterministically.
    
    Attributes:
        risk_limits: Risk limits configuration
        instrument: Single instrument this engine trades (enforced)
        fixed_fee: Fixed fee per fill (in dollars)
        orders: Dictionary of order_id -> Order
        fills: Dictionary of order_id -> List[Fill]
        positions: Dictionary of instrument -> Position
    """
    
    def __init__(
        self,
        instrument: str,
        risk_limits: Optional[RiskLimits] = None,
        fixed_fee: float = 0.0,
        artifact_store: Optional['ArtifactStore'] = None,
        session_id: Optional[str] = None,
        clock: Optional[ExecutionClock] = None,
        id_provider: Optional[IDProvider] = None,
        slippage_factor: float = 0.0
    ):
        """Initialize paper execution engine.
        
        Args:
            instrument: Single instrument identifier (enforced)
            risk_limits: Risk limits configuration (default: no limits)
            fixed_fee: Fixed fee per fill in dollars (default: 0.0)
            artifact_store: Optional artifact store for persistence
            session_id: Optional session identifier (defaults to generated from id_provider)
            clock: Optional execution clock for timestamp generation (default: SimulationClock)
                  In LIVE mode, use FixedClock seeded from cycle_timestamp for determinism
            id_provider: Optional ID provider for ID generation (default: SimulationIDProvider)
                        In LIVE mode, use DeterministicIDProvider seeded from cycle_id for determinism
            
        Raises:
            ValueError: If instrument is empty or fixed_fee is negative
        """
        if not instrument or not instrument.strip():
            raise ValueError("instrument must be non-empty")
        
        if fixed_fee < 0:
            raise ValueError(f"fixed_fee must be non-negative, got: {fixed_fee}")
        
        self.instrument = instrument
        self.risk_limits = risk_limits or RiskLimits()
        self.fixed_fee = fixed_fee
        self.slippage_factor = slippage_factor  # Task 2.3: Slippage modeling
        self.artifact_store = artifact_store
        self.id_provider = id_provider or SimulationIDProvider()
        self.clock = clock or SimulationClock()  # Default to simulation clock
        self.session_id = session_id or self.id_provider.new_session_id()
        
        # State storage
        self.orders: Dict[str, Order] = {}
        self.fills: Dict[str, List[Fill]] = {}  # order_id -> List[Fill]
        self.positions: Dict[str, Position] = {}  # instrument -> Position
        
        # Daily loss tracking (for max_daily_loss enforcement)
        self.daily_start_value: Optional[float] = None
        self.daily_start_date: Optional[datetime] = None
    
    def _get_or_create_position(self, instrument: str) -> Position:
        """Get existing position or create flat position.
        
        Args:
            instrument: Instrument identifier
            
        Returns:
            Position (flat if doesn't exist)
            
        Note:
            For flat positions, cost_basis is set to 1.0 as a placeholder
            since it's not meaningful when quantity is 0.
        """
        if instrument not in self.positions:
            self.positions[instrument] = Position(
                instrument=instrument,
                quantity=0.0,
                cost_basis=1.0,  # Placeholder value for flat positions
                realized_pnl=0.0,
                updated_at=self.clock.now()
            )
        return self.positions[instrument]
    
    def _check_risk_limits(self, signal: Signal, current_price: float) -> None:
        """Check if order would violate risk limits.
        
        Args:
            signal: Signal to check
            current_price: Current market price (for position value calculation)
            
        Raises:
            RiskLimitExceededError: If risk limits would be violated
        """
        # Check instrument is allowed
        if not self.risk_limits.is_instrument_allowed(signal.instrument):
            raise RiskLimitExceededError(
                f"Instrument {signal.instrument} not in allowed list"
            )
        
        # Check single instrument constraint
        if signal.instrument != self.instrument:
            raise RiskLimitExceededError(
                f"Engine configured for {self.instrument}, got signal for {signal.instrument}"
            )
        
        # Get current position
        current_position = self._get_or_create_position(signal.instrument)
        
        # Determine new position quantity
        if signal.signal_type == SignalType.BUY:
            new_quantity = current_position.quantity + signal.quantity
        elif signal.signal_type == SignalType.SELL:
            new_quantity = current_position.quantity - signal.quantity
        else:  # HOLD
            return  # No risk checks needed for HOLD
        
        # Check max position size
        if self.risk_limits.max_position_size is not None:
            if abs(new_quantity) > self.risk_limits.max_position_size:
                raise RiskLimitExceededError(
                    f"Position size {abs(new_quantity)} would exceed max {self.risk_limits.max_position_size}"
                )
        
        # Check max daily loss (simplified: check current realized PnL)
        if self.risk_limits.max_daily_loss is not None:
            # For this simple implementation, we check realized PnL
            # A more sophisticated implementation would track unrealized PnL too
            if current_position.realized_pnl < self.risk_limits.max_daily_loss:
                raise RiskLimitExceededError(
                    f"Daily loss {current_position.realized_pnl} would exceed max {self.risk_limits.max_daily_loss}"
                )
    
    def submit_order(self, signal: Signal) -> Order:
        """Submit an order from a signal.
        
        Process:
        1. Validate signal (non-HOLD, valid quantity)
        2. Check risk limits (using current price - caller must provide)
        3. Create Order with ACCEPTED status
        4. Store order
        
        Note: For market orders, we cannot check risk limits without current_price.
        This is a limitation of the current interface. In practice, the caller
        should check risk limits before calling, or we accept the order and
        validate during execution.
        
        For now, we accept HOLD signals as no-op and reject invalid signals.
        
        Args:
            signal: Signal to convert to order
            
        Returns:
            Order with status ACCEPTED (if valid) or REJECTED
            
        Raises:
            ExecutionEngineError: If order cannot be processed
        """
        # Handle HOLD signals (no action)
        if signal.signal_type == SignalType.HOLD:
            order_id = self.id_provider.new_order_id(signal_id=signal.strategy_id)
            order = Order(
                id=order_id,
                signal_id=None,
                instrument=signal.instrument,
                order_type=OrderType.MARKET,
                side="buy",  # Dummy value for HOLD
                quantity=0.0,
                status=OrderStatus.REJECTED,
                created_at=signal.timestamp,
                rejection_reason="HOLD signals do not generate orders"
            )
            self.orders[order_id] = order
            return order
        
        # Validate signal instrument matches engine instrument
        if signal.instrument != self.instrument:
            order_id = self.id_provider.new_order_id(signal_id=signal.strategy_id)
            order = Order(
                id=order_id,
                signal_id=None,
                instrument=signal.instrument,
                order_type=OrderType.MARKET,
                side="buy",  # Dummy value
                quantity=signal.quantity,
                status=OrderStatus.REJECTED,
                created_at=signal.timestamp,
                rejection_reason=f"Instrument mismatch: engine trades {self.instrument}, signal is for {signal.instrument}"
            )
            self.orders[order_id] = order
            return order
        
        # Check instrument is allowed
        if not self.risk_limits.is_instrument_allowed(signal.instrument):
            order_id = self.id_provider.new_order_id(signal_id=signal.strategy_id)
            order = Order(
                id=order_id,
                signal_id=None,
                instrument=signal.instrument,
                order_type=OrderType.MARKET,
                side="buy" if signal.signal_type == SignalType.BUY else "sell",
                quantity=signal.quantity,
                status=OrderStatus.REJECTED,
                created_at=signal.timestamp,
                rejection_reason=f"Instrument {signal.instrument} not in allowed list"
            )
            self.orders[order_id] = order
            return order
        
        # Create order (risk limits checked during execution when we have current_price)
        order_id = self.id_provider.new_order_id(signal_id=signal.strategy_id)
        order = Order(
            id=order_id,
            signal_id=None,
            instrument=signal.instrument,
            order_type=OrderType.MARKET,
            side="buy" if signal.signal_type == SignalType.BUY else "sell",
            quantity=signal.quantity,
            status=OrderStatus.ACCEPTED,
            created_at=signal.timestamp,
            accepted_at=self.clock.now()
        )
        
        self.orders[order_id] = order
        self.fills[order_id] = []  # Initialize fills list
        
        # Persist if artifact store is configured
        if self.artifact_store:
            self.persist_session()
        
        return order
    
    def execute_order(self, order: Order, current_price: float, timestamp: Optional[datetime] = None) -> List[Fill]:
        """Execute an order (deterministic paper trading simulation).
        
        For market orders, fills immediately at current_price.
        Full fills only (no partial fills).
        
        Process:
        1. Validate order is in executable state
        2. Check risk limits with current price
        3. Create Fill at current_price
        4. Update position
        5. Update order status to FILLED
        
        Args:
            order: Order to execute (must be ACCEPTED or PARTIALLY_FILLED)
            current_price: Current market price (used for fill)
            timestamp: Optional timestamp for execution (defaults to now)
            
        Returns:
            List containing single Fill (full fill)
            
        Raises:
            ExecutionEngineError: If order cannot be executed
            ValueError: If order is not in executable state
            RiskLimitExceededError: If risk limits would be violated
        """
        if timestamp is None:
            timestamp = self.clock.now()
        
        # Validate order state
        if order.status not in (OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED):
            raise ValueError(
                f"Order {order.id} is in state {order.status.value}, cannot execute. "
                f"Must be ACCEPTED or PARTIALLY_FILLED"
            )
        
        # Check instrument matches
        if order.instrument != self.instrument:
            raise ExecutionEngineError(
                f"Order instrument {order.instrument} does not match engine instrument {self.instrument}"
            )
        
        # Check risk limits with current price
        # Create a temporary signal for risk checking
        signal_type = SignalType.BUY if order.side == "buy" else SignalType.SELL
        temp_signal = Signal(
            timestamp=timestamp,
            instrument=order.instrument,
            signal_type=signal_type,
            quantity=order.quantity
        )
        
        try:
            self._check_risk_limits(temp_signal, current_price)
        except RiskLimitExceededError as e:
            # Reject the order
            rejected_order = Order(
                id=order.id,
                signal_id=order.signal_id,
                instrument=order.instrument,
                order_type=order.order_type,
                side=order.side,
                quantity=order.quantity,
                price_limit=order.price_limit,
                status=OrderStatus.REJECTED,
                created_at=order.created_at,
                accepted_at=order.accepted_at,
                rejection_reason=str(e)
            )
            self.orders[order.id] = rejected_order
            raise OrderRejectionError(f"Order rejected due to risk limits: {e}") from e
        
        # Create fill (full fill, immediate) with slippage applied (Task 2.3)
        # Slippage is a percentage increase for BUY, decrease for SELL
        slippage_adjustment = 1.0
        if self.slippage_factor > 0:
            if order.side == "buy":
                slippage_adjustment = 1.0 + self.slippage_factor
            else:  # sell
                slippage_adjustment = 1.0 - self.slippage_factor
        
        fill_price = current_price * slippage_adjustment
        
        fill_id = self.id_provider.new_fill_id(order_id=order.id)
        fill = Fill(
            id=fill_id,
            order_id=order.id,
            instrument=order.instrument,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            fee=self.fixed_fee,
            filled_at=timestamp
        )
        
        # Update fills
        if order.id not in self.fills:
            self.fills[order.id] = []
        self.fills[order.id].append(fill)
        
        # Update position
        current_position = self._get_or_create_position(order.instrument)
        new_position = current_position.apply_fill(fill)
        self.positions[order.instrument] = new_position
        
        # Update order status to FILLED
        filled_order = Order(
            id=order.id,
            signal_id=order.signal_id,
            instrument=order.instrument,
            order_type=order.order_type,
            side=order.side,
            quantity=order.quantity,
            price_limit=order.price_limit,
            status=OrderStatus.FILLED,
            created_at=order.created_at,
            accepted_at=order.accepted_at,
            filled_at=timestamp
        )
        self.orders[order.id] = filled_order
        
        # Persist if artifact store is configured
        if self.artifact_store:
            self.persist_session()
        
        return [fill]
    
    def cancel_order(self, order_id: str) -> Order:
        """Cancel an active order.
        
        Args:
            order_id: ID of order to cancel
            
        Returns:
            Updated Order with status CANCELED
            
        Raises:
            ExecutionEngineError: If order cannot be canceled
            ValueError: If order is not found or not in cancellable state
        """
        if order_id not in self.orders:
            raise ValueError(f"Order {order_id} not found")
        
        order = self.orders[order_id]
        
        if not order.is_active():
            raise ExecutionEngineError(
                f"Order {order_id} is in state {order.status.value}, cannot cancel. "
                f"Only active orders (CREATED, ACCEPTED, PARTIALLY_FILLED) can be canceled"
            )
        
        canceled_order = Order(
            id=order.id,
            signal_id=order.signal_id,
            instrument=order.instrument,
            order_type=order.order_type,
            side=order.side,
            quantity=order.quantity,
            price_limit=order.price_limit,
            status=OrderStatus.CANCELED,
            created_at=order.created_at,
            accepted_at=order.accepted_at,
            canceled_at=self.clock.now()
        )
        
        self.orders[order_id] = canceled_order
        
        # Persist if artifact store is configured
        if self.artifact_store:
            self.persist_session()
        
        return canceled_order
    
    def get_position(self, instrument: str) -> Position:
        """Get current position for an instrument.
        
        Args:
            instrument: Instrument identifier
            
        Returns:
            Position (quantity=0 if no position exists)
        """
        return self._get_or_create_position(instrument)
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID.
        
        Args:
            order_id: Order identifier
            
        Returns:
            Order if found, None otherwise
        """
        return self.orders.get(order_id)
    
    def list_orders(
        self,
        instrument: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Order]:
        """List orders with optional filters.
        
        Args:
            instrument: Filter by instrument (None = all instruments)
            status: Filter by status string (None = all statuses)
            
        Returns:
            List of matching orders
        """
        orders = list(self.orders.values())
        
        if instrument is not None:
            orders = [o for o in orders if o.instrument == instrument]
        
        if status is not None:
            try:
                status_enum = OrderStatus(status)
                orders = [o for o in orders if o.status == status_enum]
            except ValueError:
                # Invalid status string, return empty list
                return []
        
        return orders
    
    def get_fills(self, order_id: str) -> List[Fill]:
        """Get all fills for an order.
        
        Args:
            order_id: Order identifier
            
        Returns:
            List of fills (may be empty if order has no fills)
        """
        return self.fills.get(order_id, [])
    
    def reset(self) -> None:
        """Reset engine state (for testing/new sessions).
        
        Clears all orders, positions, and fills.
        """
        self.orders.clear()
        self.fills.clear()
        self.positions.clear()
        self.daily_start_value = None
        self.daily_start_date = None
    
    def persist_session(self) -> None:
        """Persist session state to artifact store.
        
        Stores:
        - orders.json: All orders
        - fills.json: All fills (by order_id)
        - positions.json: All positions
        - risk_limits.json: Risk limits configuration
        - session_metadata.json: Session metadata
        
        Raises:
            ExecutionEngineError: If artifact_store is None or persistence fails
        """
        if self.artifact_store is None:
            raise ExecutionEngineError("Cannot persist session: artifact_store is None")
        
        try:
            # Store orders
            orders_data = [order.to_dict() for order in self.orders.values()]
            orders_json = json.dumps(orders_data, indent=2).encode('utf-8')
            self.artifact_store.store(self.session_id, "orders.json", orders_json)
            
            # Store fills (flatten list of lists)
            all_fills = []
            for order_id, fill_list in self.fills.items():
                all_fills.extend([fill.to_dict() for fill in fill_list])
            fills_json = json.dumps(all_fills, indent=2).encode('utf-8')
            self.artifact_store.store(self.session_id, "fills.json", fills_json)
            
            # Store positions
            positions_data = [pos.to_dict() for pos in self.positions.values()]
            positions_json = json.dumps(positions_data, indent=2).encode('utf-8')
            self.artifact_store.store(self.session_id, "positions.json", positions_json)
            
            # Store risk limits
            risk_limits_data = {
                "max_position_size": self.risk_limits.max_position_size,
                "max_daily_loss": self.risk_limits.max_daily_loss,
                "max_leverage": self.risk_limits.max_leverage,
                "allowed_instruments": self.risk_limits.allowed_instruments,
            }
            risk_limits_json = json.dumps(risk_limits_data, indent=2).encode('utf-8')
            self.artifact_store.store(self.session_id, "risk_limits.json", risk_limits_json)
            
            # Store session metadata
            metadata = {
                "session_id": self.session_id,
                "instrument": self.instrument,
                "fixed_fee": self.fixed_fee,
                "created_at": self.clock.now().isoformat(),
            }
            metadata_json = json.dumps(metadata, indent=2).encode('utf-8')
            self.artifact_store.store(self.session_id, "session_metadata.json", metadata_json)
            
        except Exception as e:
            raise ExecutionEngineError(f"Failed to persist session: {e}") from e
    
    @classmethod
    def load_session(
        cls,
        session_id: str,
        artifact_store: 'ArtifactStore'
    ) -> 'PaperExecutionEngine':
        """Load session from artifact store.
        
        Args:
            session_id: Session identifier
            artifact_store: Artifact store to load from
            
        Returns:
            PaperExecutionEngine with loaded state
            
        Raises:
            ExecutionEngineError: If session cannot be loaded
        """
        try:
            # Load session metadata
            metadata_data = artifact_store.retrieve(session_id, "session_metadata.json")
            if metadata_data is None:
                raise ExecutionEngineError(f"Session {session_id} not found")
            
            metadata = json.loads(metadata_data.decode('utf-8'))
            instrument = metadata["instrument"]
            fixed_fee = metadata.get("fixed_fee", 0.0)
            
            # Load risk limits
            risk_limits_data = artifact_store.retrieve(session_id, "risk_limits.json")
            risk_limits = None
            if risk_limits_data:
                rl_dict = json.loads(risk_limits_data.decode('utf-8'))
                risk_limits = RiskLimits(
                    max_position_size=rl_dict.get("max_position_size"),
                    max_daily_loss=rl_dict.get("max_daily_loss"),
                    max_leverage=rl_dict.get("max_leverage", 1.0),
                    allowed_instruments=rl_dict.get("allowed_instruments"),
                )
            
            # Create engine
            engine = cls(
                instrument=instrument,
                risk_limits=risk_limits,
                fixed_fee=fixed_fee,
                artifact_store=artifact_store,
                session_id=session_id
            )
            
            # Load orders
            orders_data = artifact_store.retrieve(session_id, "orders.json")
            if orders_data:
                orders_list = json.loads(orders_data.decode('utf-8'))
                engine.orders = {order_dict["id"]: Order.from_dict(order_dict) for order_dict in orders_list}
            
            # Load fills
            fills_data = artifact_store.retrieve(session_id, "fills.json")
            if fills_data:
                fills_list = json.loads(fills_data.decode('utf-8'))
                engine.fills = {}
                for fill_dict in fills_list:
                    fill = Fill.from_dict(fill_dict)
                    if fill.order_id not in engine.fills:
                        engine.fills[fill.order_id] = []
                    engine.fills[fill.order_id].append(fill)
            
            # Load positions
            positions_data = artifact_store.retrieve(session_id, "positions.json")
            if positions_data:
                positions_list = json.loads(positions_data.decode('utf-8'))
                engine.positions = {pos_dict["instrument"]: Position.from_dict(pos_dict) for pos_dict in positions_list}
            
            return engine
            
        except Exception as e:
            raise ExecutionEngineError(f"Failed to load session {session_id}: {e}") from e

