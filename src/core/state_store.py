#!/usr/bin/env python3
"""
STATE PERSISTENCE LAYER V2
Unified StateStore implementation merging robustness of v2 with convenience of v1.

Hardened atomic persistence with:
1. Intent-based Idempotency (OrderIntent)
2. Directory fsync + OS locking
3. Decimal-precise canonicalization
"""

import json
import os
import sys
import fcntl
import tempfile
import socket
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from enum import Enum
from decimal import Decimal, ROUND_DOWN

# Defines the decimal context for crypto (8 places) and price (2 places for USD usually, but safer to be flexible or consistent)
# User requested 8 dp default for qty.

class OrderStatus(Enum):
    """Order reconciliation states."""
    SUBMITTED_LOCAL = "submitted_local"     # Submitted but not confirmed by broker
    SUBMITTED_BROKER = "submitted_broker"   # Broker acknowledged receipt (e.g. via API return)
    ACKED = "acked"                         # Broker sent async ack
    OPEN = "open"                           # Working order
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNKNOWN = "unknown"

@dataclass
class OrderIntent:
    """
    Deterministic order intent for robust idempotency.
    
    Two orders with same intent are duplicates.
    Uses stringified Decimals for canonical representation.
    """
    symbol: str
    side: str           # 'buy' or 'sell'
    qty: str            # Canonicalized Decimal string (8 dp)
    order_type: str     # 'market', 'limit', etc.
    limit_price: Optional[str] = None
    stop_price: Optional[str] = None
    strategy_id: str = "explore"
    signal_timestamp: str = "" # ISO 8601 of the signal

    @classmethod
    def create(cls, 
               symbol: str, 
               side: str, 
               qty: Union[float, str, Decimal], 
               order_type: str = "market",
               limit_price: Optional[Union[float, str, Decimal]] = None,
               stop_price: Optional[Union[float, str, Decimal]] = None,
               strategy_id: str = "explore",
               signal_timestamp: Optional[str] = None) -> 'OrderIntent':
        
        # Normalize inputs
        norm_symbol = symbol.upper().strip()
        norm_side = side.lower().strip()
        norm_type = order_type.lower().strip()
        
        # Canonicalize Qty (8 dp floor)
        # Using cast to string first to avoid float precision issues if passed as float
        d_qty = Decimal(str(qty)).quantize(Decimal("1.00000000"), rounding=ROUND_DOWN)
        
        # Canonicalize Prices
        s_limit = None
        if limit_price is not None:
            d_limit = Decimal(str(limit_price)).quantize(Decimal("1.00"), rounding=ROUND_DOWN)
            s_limit = f"{d_limit:f}"
            
        s_stop = None
        if stop_price is not None:
            d_stop = Decimal(str(stop_price)).quantize(Decimal("1.00"), rounding=ROUND_DOWN)
            s_stop = f"{d_stop:f}"

        return cls(
            symbol=norm_symbol,
            side=norm_side,
            qty=f"{d_qty:f}",
            order_type=norm_type,
            limit_price=s_limit,
            stop_price=s_stop,
            strategy_id=strategy_id,
            signal_timestamp=signal_timestamp or ""
        )

    def intent_key(self) -> str:
        """Generate unique deterministic key."""
        parts = [
            self.symbol,
            self.side,
            self.qty,
            self.order_type,
            self.limit_price or "NONE",
            self.stop_price or "NONE",
            self.strategy_id,
            self.signal_timestamp
        ]
        return "|".join(parts)
    
    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict):
        return cls(**d)

@dataclass
class Position:
    """Open position state."""
    symbol: str
    qty: float
    entry_price: float
    entry_time: str  # ISO 8601
    stop_price: float
    high_water_mark: float
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict):
        return cls(**d)

@dataclass
class PendingOrder:
    """
    Pending order tracking.
    Stores the intent that generated it + execution state.
    """
    order_id: str
    intent: OrderIntent
    status: str       # OrderStatus.value
    submitted_at: str # ISO 8601
    updated_at: str   # ISO 8601
    filled_qty: float = 0.0
    avg_entry_price: float = 0.0
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d['intent'] = self.intent.to_dict()
        return d
    
    @classmethod
    def from_dict(cls, d: Dict):
        # Forward compatibility: ignore unknown keys
        valid_keys = cls.__annotations__.keys()
        clean_d = {k: v for k, v in d.items() if k in valid_keys}
        
        if 'intent' in clean_d and isinstance(clean_d['intent'], dict):
            clean_d['intent'] = OrderIntent.from_dict(clean_d['intent'])
        return cls(**clean_d)

@dataclass
class CircuitBreakerState:
    """
    Circuit breaker state with explicit timezone awareness.
    """
    status: str       # 'active', 'tripped', 'reset'
    start_of_day_equity: float
    current_equity: float
    daily_pnl: float
    trip_time: Optional[str]
    reset_time: Optional[str] 
    timezone: str = "America/New_York"
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict):
        return cls(**d)

@dataclass
class TradingState:
    """
    Root state object.
    """
    version: str = "2.0.0"
    last_restart: str = ""
    environment: str = "paper"
    
    positions: Dict[str, Dict] = None          # symbol -> Position.to_dict()
    pending_orders: Dict[str, Dict] = None     # order_id -> PendingOrder.to_dict()
    
    # Idempotency Registry: intent_key -> metadata dict
    # { "KEY": { "order_id": "...", "status": "...", "created_at": "..." } }
    idempotency_registry: Dict[str, Dict] = None 
    
    last_candle_timestamps: Dict[str, str] = None
    circuit_breaker: Optional[Dict] = None
    portfolio_heat: float = 0.0
    wash_sale_register: Dict[str, str] = None

    def __post_init__(self):
        if self.positions is None: self.positions = {}
        if self.pending_orders is None: self.pending_orders = {}
        if self.idempotency_registry is None: self.idempotency_registry = {}
        if self.last_candle_timestamps is None: self.last_candle_timestamps = {}
        if self.wash_sale_register is None: self.wash_sale_register = {}

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict):
        # Filter unknown fields for forward compatibility
        valid_keys = cls.__annotations__.keys()
        return cls(**{k: v for k, v in d.items() if k in valid_keys})


class StateStore:
    """
    Hardened Atomic Store.
    """
    def __init__(self, state_dir: str = "state", environment: str = "paper"):
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.environment = environment
        self.state_file = self.state_dir / "trading_state.json"
        self.lock_file = self.state_dir / "state.lock"
        self._acquire_lock()
        print(f"[StateStore] Initialized at {self.state_dir} (env={self.environment})")

    def _acquire_lock(self):
        # Open without truncation to preserve existing PID if locked
        fd = os.open(self.lock_file, os.O_RDWR | os.O_CREAT, 0o666)
        self.lock_fd = os.fdopen(fd, 'r+')
        
        try:
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # We have the lock. Truncate and write our info.
            self.lock_fd.seek(0)
            self.lock_fd.truncate()
            pid = os.getpid()
            host = socket.gethostname()
            self.lock_fd.write(f"{pid}@{host}\n")
            self.lock_fd.flush()
        except IOError:
            # Failed to lock. Read who has it.
            self.lock_fd.seek(0)
            existing = self.lock_fd.read().strip()
            self.lock_fd.close() # Close since we failed
            raise RuntimeError(f"State dir locked by {existing}")

    def _release_lock(self):
        if hasattr(self, 'lock_fd'):
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
            self.lock_fd.close()
            try:
                self.lock_file.unlink()
            except:
                pass

    def __del__(self):
        self._release_lock()

    def _atomic_write(self, data: Dict[str, Any]):
        """Write -> Fsync File -> Rename -> Fsync Dir"""
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self.state_dir, 
            prefix=f".{self.state_file.name}.", 
            suffix=".tmp"
        )
        try:
            with os.fdopen(temp_fd, 'w') as f:
                json.dump(data, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            
            os.rename(temp_path, self.state_file)
            
            # Directory Fsync
            dir_fd = os.open(str(self.state_dir), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
                
        except Exception as e:
            try:
                os.remove(temp_path)
            except:
                pass
            raise e

    def load_state(self) -> TradingState:
        if not self.state_file.exists():
            return TradingState(environment=self.environment)
        try:
            with open(self.state_file, 'r') as f:
                return TradingState.from_dict(json.load(f))
        except Exception as e:
            print(f"[CRITICAL] State load failed: {e}")
            # In a real scenario, we might want to halt or backup the corrupt file
            # For now, return empty state with warning
            return TradingState(environment=self.environment)

    def save_state(self, state: TradingState):
        state.last_restart = datetime.now(timezone.utc).isoformat()
        self._atomic_write(state.to_dict())

    # --- Idempotency Methods ---

    def register_intent(self, intent: OrderIntent, order_id: str):
        """
        Record an order intent.
        """
        state = self.load_state()
        key = intent.intent_key()
        
        now_ts = datetime.now(timezone.utc).isoformat()
        
        entry = {
            "order_id": order_id,
            "status": OrderStatus.SUBMITTED_LOCAL.value,
            "first_seen": now_ts,
            "last_seen": now_ts
        }
        
        is_new = key not in state.idempotency_registry
        
        # If already exists, we preserve first_seen
        if not is_new:
            existing = state.idempotency_registry[key]
            entry["first_seen"] = existing.get("first_seen", now_ts)
        
        state.idempotency_registry[key] = entry
        
        # Also create the PendingOrder entry
        po = PendingOrder(
            order_id=order_id,
            intent=intent,
            status=OrderStatus.SUBMITTED_LOCAL.value,
            submitted_at=now_ts,
            updated_at=now_ts
        )
        state.pending_orders[order_id] = po.to_dict()
        
        self.save_state(state)
        return is_new

    def check_idempotency(self, intent: OrderIntent) -> Optional[Dict]:
        """
        Check if intent was already processed.
        Returns the registry entry if found, None otherwise.
        """
        state = self.load_state()
        key = intent.intent_key()
        return state.idempotency_registry.get(key)

    # --- Convenience Methods (Ported from v1) ---

    def update_positions(self, positions: Dict[str, Position]):
        """Update positions in state."""
        state = self.load_state()
        # Convert Position objects to dicts
        state.positions = {k: v.to_dict() for k, v in positions.items()}
        self.save_state(state)

    def update_pending_orders(self, orders: Dict[str, PendingOrder]):
        """Update pending orders in state."""
        state = self.load_state()
        # Convert PendingOrder objects to dicts
        state.pending_orders = {k: v.to_dict() for k, v in orders.items()}
        self.save_state(state)

    def update_circuit_breaker(self, breaker: CircuitBreakerState):
        """Update circuit breaker state."""
        state = self.load_state()
        state.circuit_breaker = breaker.to_dict()
        self.save_state(state)

    def update_last_candle(self, symbol: str, timestamp: datetime):
        """Update last processed candle timestamp."""
        state = self.load_state()
        state.last_candle_timestamps[symbol] = timestamp.isoformat()
        self.save_state(state)
    
    def update_portfolio_heat(self, heat: float):
        """Update portfolio heat."""
        state = self.load_state()
        state.portfolio_heat = heat
        self.save_state(state)
    
    def record_wash_sale(self, symbol: str, loss_time: datetime):
        """Record a wash sale loss."""
        state = self.load_state()
        state.wash_sale_register[symbol] = loss_time.isoformat()
        self.save_state(state)
    
    def clear(self):
        """Clear all state (for testing)."""
        if self.state_file.exists():
            self.state_file.unlink()
