#!/usr/bin/env python3
"""Tests for BLOCKER-3: Unregistered instrument rejection policy.

AUDIT REMEDIATION: BLOCKER-3
- Entry orders with unregistered instruments must be REJECTED
- Exit/reduce orders must never be blocked, even if instrument is unregistered
"""

import pytest
from datetime import datetime
from decimal import Decimal

from src.execution import PaperExecutionEngine, Signal, SignalType, OrderStatus
from src.core.instrument_spec import AAPL_EQUITY, register_instrument


class TestUnregisteredInstrumentPolicy:
    """Test that unregistered instruments are rejected for entry, allowed for exit."""
    
    def test_entry_rejected_for_unregistered_symbol(self):
        """Entry order rejected when instrument not registered."""
        # Do NOT register "SPY"
        engine = PaperExecutionEngine(
            instrument="SPY",
            account_cash=Decimal("100000"),
            account_equity=Decimal("100000"),
        )
        
        signal = Signal(
            timestamp=datetime(2026, 1, 13, 10, 0),
            instrument="SPY",
            signal_type=SignalType.BUY,
            quantity=100,
        )
        
        order = engine.submit_order(signal)
        
        # Should be REJECTED
        assert order.status == OrderStatus.REJECTED
        assert "not registered" in order.rejection_reason.lower()
        assert "SPY" in order.rejection_reason
    
    def test_typo_symbol_rejected(self):
        """Typo in symbol name should be rejected."""
        # Register "AAPL" but try to trade "AAPLL" (typo)
        register_instrument(AAPL_EQUITY)
        
        engine = PaperExecutionEngine(
            instrument="AAPLL",  # Typo
            account_cash=Decimal("100000"),
            account_equity=Decimal("100000"),
        )
        
        signal = Signal(
            timestamp=datetime(2026, 1, 13, 10, 0),
            instrument="AAPLL",
            signal_type=SignalType.BUY,
            quantity=100,
        )
        
        order = engine.submit_order(signal)
        
        # Should be REJECTED - catch typos early
        assert order.status == OrderStatus.REJECTED
        assert "not registered" in order.rejection_reason.lower()
    
    def test_exit_allowed_with_registered_instrument(self):
        """Exit is allowed when instrument is registered (baseline)."""
        register_instrument(AAPL_EQUITY)
        
        engine = PaperExecutionEngine(
            instrument="AAPL",
            account_cash=Decimal("100000"),
            account_equity=Decimal("100000"),
        )
        
        # First open a position
        buy_signal = Signal(
            timestamp=datetime(2026, 1, 13, 10, 0),
            instrument="AAPL",
            signal_type=SignalType.BUY,
            quantity=100,
        )
        buy_order = engine.submit_order(buy_signal)
        assert buy_order.status == OrderStatus.ACCEPTED
        
        # Execute the buy
        engine.execute_order(buy_order, current_price=150.0)
        
        # Now exit
        sell_signal = Signal(
            timestamp=datetime(2026, 1, 13, 11, 0),
            instrument="AAPL",
            signal_type=SignalType.SELL,
            quantity=100,
        )
        sell_order = engine.submit_order(sell_signal)
        
        # Exit should be accepted
        assert sell_order.status == OrderStatus.ACCEPTED
