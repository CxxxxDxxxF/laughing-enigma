"""Simple signal adapter implementation.

This module provides a minimal SignalAdapter with fixed position sizing
and basic validation.
"""

from typing import Optional

from .adapter import SignalAdapter, AdapterConfig, InvalidSignalError, RiskCheckError
from .emitter import RawStrategyOutput
from ..execution import Signal, SignalType


class SimpleSignalAdapter(SignalAdapter):
    """Simple signal adapter with fixed position sizing.
    
    This adapter provides minimal adaptation logic:
    - Validates raw outputs
    - Applies basic filters (ignores HOLD signals)
    - Uses fixed position sizing (uses raw quantity as-is)
    - Maps action → SignalType
    - Basic pre-execution risk checks (instrument whitelist only)
    
    This is a minimal implementation for testing the signal pipeline.
    """
    
    def validate_raw_output(self, raw_output: RawStrategyOutput) -> bool:
        """Validate raw strategy output format.
        
        Args:
            raw_output: Raw output to validate
            
        Returns:
            True if valid
            
        Raises:
            InvalidSignalError: If validation fails
        """
        if not raw_output.instrument or not raw_output.instrument.strip():
            raise InvalidSignalError(f"Invalid instrument: {raw_output.instrument}")
        
        if raw_output.action not in ("buy", "sell", "hold"):
            raise InvalidSignalError(f"Invalid action: {raw_output.action}")
        
        if raw_output.quantity < 0:
            raise InvalidSignalError(f"Invalid quantity: {raw_output.quantity}")
        
        if raw_output.action != "hold" and raw_output.quantity == 0:
            raise InvalidSignalError(f"Non-HOLD signals must have positive quantity")
        
        return True
    
    def apply_filters(self, raw_output: RawStrategyOutput) -> bool:
        """Apply signal filters.
        
        Currently filters out:
        - HOLD signals (returns False)
        
        Args:
            raw_output: Raw output to filter
            
        Returns:
            True if signal should be processed, False if ignored
        """
        # Ignore HOLD signals (they don't generate orders)
        if raw_output.action == "hold":
            return False
        
        # Apply confidence filter if configured
        if self.config.signal_filters:
            min_confidence = self.config.signal_filters.get("min_confidence")
            if min_confidence is not None:
                if raw_output.confidence is None or raw_output.confidence < min_confidence:
                    return False
        
        return True
    
    def apply_position_sizing(self, raw_output: RawStrategyOutput) -> float:
        """Apply position sizing rules.
        
        For simple adapter: returns raw quantity as-is (fixed sizing).
        
        Args:
            raw_output: Raw output with initial quantity
            
        Returns:
            Final quantity (same as raw quantity for simple adapter)
        """
        # For simple adapter, use raw quantity directly
        # Future implementations could apply percentage sizing, volatility targeting, etc.
        return raw_output.quantity
    
    def check_pre_execution_risk(self, signal: Signal) -> None:
        """Perform pre-execution risk checks.
        
        Currently checks:
        - Instrument whitelist (if configured)
        
        Args:
            signal: Signal to check
            
        Raises:
            RiskCheckError: If risk checks fail
        """
        # Check instrument whitelist
        if self.config.instrument_whitelist is not None:
            if signal.instrument not in self.config.instrument_whitelist:
                raise RiskCheckError(
                    f"Instrument {signal.instrument} not in whitelist: {self.config.instrument_whitelist}"
                )
        
        # Additional risk checks can be added here
        # (e.g., position size limits, correlation limits, etc.)
    
    def adapt(self, raw_output: RawStrategyOutput) -> Optional[Signal]:
        """Adapt a raw strategy output to an execution-ready Signal.
        
        Process:
        1. Validate raw_output
        2. Apply filters (returns None if filtered)
        3. Apply position sizing
        4. Map action → SignalType
        5. Perform pre-execution risk checks
        6. Create Signal object
        
        Args:
            raw_output: Raw strategy output to adapt
            
        Returns:
            Signal object if adaptation succeeds, None if filtered
            
        Raises:
            InvalidSignalError: If raw_output is invalid
            RiskCheckError: If signal fails risk checks
        """
        # Validate
        self.validate_raw_output(raw_output)
        
        # Apply filters
        if not self.apply_filters(raw_output):
            return None  # Signal filtered out (not an error)
        
        # Apply position sizing
        final_quantity = self.apply_position_sizing(raw_output)
        
        # Map action → SignalType
        action_map = {
            "buy": SignalType.BUY,
            "sell": SignalType.SELL,
            "hold": SignalType.HOLD,
        }
        signal_type = action_map[raw_output.action]
        
        # Create Signal (without price_limit for market orders)
        signal = Signal(
            timestamp=raw_output.timestamp,
            instrument=raw_output.instrument,
            signal_type=signal_type,
            quantity=final_quantity,
            price_limit=None,  # Market orders for simple adapter
            strategy_id=None,  # Can be set by caller if needed
            metadata=raw_output.strategy_context
        )
        
        # Perform pre-execution risk checks
        self.check_pre_execution_risk(signal)
        
        return signal

