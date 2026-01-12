#!/usr/bin/env python3
"""Integration tests for position sizing gate wired into PaperExecutionEngine."""

import pytest
from datetime import datetime
from decimal import Decimal

from src.execution import PaperExecutionEngine, Signal, SignalType, OrderStatus
from src.core.instrument_spec import ES_FUTURE, AAPL_EQUITY, register_instrument


class TestPositionSizingIntegration:
    """Test position sizing gate integrated into paper engine."""
    
    def test_engine_allows_entry_with_sufficient_resources(self):
        """Test engine allows entry when resources are sufficient."""
        # Register ES in instrument registry
        register_instrument(ES_FUTURE)
        
        engine = PaperExecutionEngine(
            instrument="ES",
            account_cash=Decimal("100000"),
            account_equity=Decimal("100000"),
        )
        
        # Submit entry signal
        signal = Signal(
            timestamp=datetime(2026, 1, 13, 10, 0),
            instrument="ES",
            signal_type=SignalType.BUY,
            quantity=2,  # Well within limits
        )
        
        order = engine.submit_order(signal)
        
        assert order.status == OrderStatus.ACCEPTED
        assert order.rejection_reason is None
    
    def test_engine_allows_exit_even_from_flat(self):
        """Test engine allows exit orders (never blocks closes)."""
        register_instrument(AAPL_EQUITY)
        
        engine = PaperExecutionEngine(
            instrument="AAPL",
            account_cash=Decimal("100000"),
            account_equity=Decimal("100000"),
        )
        
        # First, open a long position
        buy_signal = Signal(
            timestamp=datetime(2026, 1, 13, 10, 0),
            instrument="AAPL",
            signal_type=SignalType.BUY,
            quantity=100,
        )
        buy_order = engine.submit_order(buy_signal)
        assert buy_order.status == OrderStatus.ACCEPTED
        
        # Execute the buy to establish position
        engine.execute_order(buy_order, current_price=150.0)
        
        # Now submit sell signal (exit)
        sell_signal = Signal(
            timestamp=datetime(2026, 1, 13, 11, 0),
            instrument="AAPL",
            signal_type=SignalType.SELL,
            quantity=100,  # Full exit
        )
        
        sell_order = engine.submit_order(sell_signal)
        
        # Should be accepted (exits are never blocked)
        assert sell_order.status == OrderStatus.ACCEPTED
    
    def test_engine_blocks_excessive_contracts(self):
        """Test engine blocks entry when exceeding max contracts."""
        register_instrument(ES_FUTURE)
        
        engine = PaperExecutionEngine(
            instrument="ES",
            account_cash=Decimal("500000"),  # Enough for margin, but still hit contract cap
            account_equity=Decimal("500000"),
        )
        
        # Try to open 10 contracts (exceeds default max of 5)
        signal = Signal(
            timestamp=datetime(2026, 1, 13, 10, 0),
            instrument="ES",
            signal_type=SignalType.BUY,
            quantity=10,
        )
        
        order = engine.submit_order(signal)
        
        assert order.status == OrderStatus.REJECTED
        # Now should get contract cap violation, not margin
        assert ("position" in order.rejection_reason.lower() or "contract" in order.rejection_reason.lower())
        assert ("cap" in order.rejection_reason.lower() or "max" in order.rejection_reason.lower() or "exceeds" in order.rejection_reason.lower())
    
    def test_entry_rejected_for_unregistered_instrument(self):
        """BLOCKER-3: Entry orders rejected when instrument not registered."""
        engine = PaperExecutionEngine(
            instrument="UNREGISTERED_SYM",
            account_cash=Decimal("100000"),
            account_equity=Decimal("100000"),
        )
        
        signal = Signal(
            timestamp=datetime(2026, 1, 13, 10, 0),
            instrument="UNREGISTERED_SYM",
            signal_type=SignalType.BUY,
            quantity=100,
        )
        
        order = engine.submit_order(signal)
        
        # Should be REJECTED - instrument not registered
        assert order.status == OrderStatus.REJECTED
        assert "not registered" in order.rejection_reason.lower()
        assert "UNREGISTERED_SYM" in order.rejection_reason
    
    def test_entry_vs_exit_detection_long_position(self):
        """Test entry vs exit detection for long positions."""
        register_instrument(AAPL_EQUITY)
        
        engine = PaperExecutionEngine(
            instrument="AAPL",
            account_cash=Decimal("100000"),
            account_equity=Decimal("100000"),
        )
        
        # Open long position
        buy_signal = Signal(
            timestamp=datetime(2026, 1, 13, 10, 0),
            instrument="AAPL",
            signal_type=SignalType.BUY,
            quantity=100,
        )
        buy_order = engine.submit_order(buy_signal)
        engine.execute_order(buy_order, current_price=150.0)
        
        # Selling from long = exit (should be allowed even if sizing would block)
        sell_signal = Signal(
            timestamp=datetime(2026, 1, 13, 11, 0),
            instrument="AAPL",
            signal_type=SignalType.SELL,
            quantity=50,  # Partial exit
        )
        sell_order = engine.submit_order(sell_signal)
        
        assert sell_order.status == OrderStatus.ACCEPTED  # Exit allowed
        
        # Buying more = increase = entry (subject to sizing)
        buy_more_signal = Signal(
            timestamp=datetime(2026, 1, 13, 12, 0),
            instrument="AAPL",
            signal_type=SignalType.BUY,
            quantity=50,
        )
        buy_more_order = engine.submit_order(buy_more_signal)
        
        # Should be accepted (within limits)
        assert buy_more_order.status == OrderStatus.ACCEPTED
