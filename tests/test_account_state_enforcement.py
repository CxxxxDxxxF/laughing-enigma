#!/usr/bin/env python3
"""Tests for account state enforcement in PaperExecutionEngine.

AUDIT REMEDIATION: BLOCKER-1
Tests that position sizing gate uses real account state or rejects entries.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from src.execution import PaperExecutionEngine, Signal, SignalType, OrderStatus
from src.core.instrument_spec import ES_FUTURE, AAPL_EQUITY, register_instrument


class TestAccountStateEnforcement:
    """Test that account state is enforced or entry orders rejected."""
    
    def test_entry_rejected_when_account_state_missing(self):
        """BLOCKER-1 REGRESSION: Entry rejected when no account state provided."""
        register_instrument(ES_FUTURE)
        
        # Create engine WITHOUT account state
        engine = PaperExecutionEngine(instrument="ES")
        
        # Try to submit entry order
        signal = Signal(
            timestamp=datetime(2026, 1, 9, 10, 0),
            instrument="ES",
            signal_type=SignalType.BUY,
            quantity=1,
        )
        
        order = engine.submit_order(signal)
        
        # Should be REJECTED with specific reason
        assert order.status == OrderStatus.REJECTED
        assert "account state missing" in order.rejection_reason.lower()
    
    def test_entry_accepted_when_sufficient_cash_provided(self):
        """Test entry accepted when account has sufficient cash."""
        register_instrument(ES_FUTURE)
        
        # Create engine WITH account state (sufficient for 1 ES contract)
        # ES margin = $12,000, with buffer $13,200
        engine = PaperExecutionEngine(
            instrument="ES",
            account_cash=Decimal("50000"),
            account_equity=Decimal("50000"),
        )
        
        signal = Signal(
            timestamp=datetime(2026, 1, 9, 10, 0),
            instrument="ES",
            signal_type=SignalType.BUY,
            quantity=1,
        )
        
        order = engine.submit_order(signal)
        
        # Should be ACCEPTED
        assert order.status == OrderStatus.ACCEPTED
        assert order.rejection_reason is None
    
    def test_entry_rejected_when_insufficient_cash(self):
        """Test entry rejected when account has insufficient cash."""
        register_instrument(ES_FUTURE)
        
        # Create engine with LOW cash (not enough for 1 ES contract)
        # ES margin = $12,000, with buffer $13,200
        engine = PaperExecutionEngine(
            instrument="ES",
            account_cash=Decimal("5000"),  # Too low
            account_equity=Decimal("5000"),
        )
        
        signal = Signal(
            timestamp=datetime(2026, 1, 9, 10, 0),
            instrument="ES",
            signal_type=SignalType.BUY,
            quantity=1,
        )
        
        order = engine.submit_order(signal)
        
        # Should be REJECTED due to insufficient margin
        assert order.status == OrderStatus.REJECTED
        assert "margin" in order.rejection_reason.lower() or "insufficient" in order.rejection_reason.lower()
    
    def test_equity_entry_rejected_when_insufficient_cash(self):
        """Test equity entry rejected when cash < notional.
        
        NOTE: Engine uses cost_basis as price proxy, which is $1 for flat positions.
        So 100 shares * $1 = $100 notional (not $15K).
        This test validates the gate works, but price proxy is a known limitation.
        """
        register_instrument(AAPL_EQUITY)
        
        # Create very low cash account
        # With $1 proxy price, 100 shares = $100 notional
        # Set cash to $50 to force rejection
        engine = PaperExecutionEngine(
            instrument="AAPL",
            account_cash=Decimal("50"),  # Below $100 notional
            account_equity=Decimal("50"),
        )
        
        signal = Signal(
            timestamp=datetime(2026, 1, 13, 10, 0),
            instrument="AAPL",
            signal_type=SignalType.BUY,
            quantity=100,
        )
        
        order = engine.submit_order(signal)
        
        # Should be REJECTED
        assert order.status == OrderStatus.REJECTED
        assert "cash" in order.rejection_reason.lower() or "insufficient" in order.rejection_reason.lower()
    
    def test_partial_account_state_missing_rejects(self):
        """Test that providing only cash (not equity) still rejects."""
        register_instrument(ES_FUTURE)
        
        # Provide cash but NOT equity
        engine = PaperExecutionEngine(
            instrument="ES",
            account_cash=Decimal("50000"),
            # account_equity=None (not provided)
        )
        
        signal = Signal(
            timestamp=datetime(2026, 1, 9, 10, 0),
            instrument="ES",
            signal_type=SignalType.BUY,
            quantity=1,
        )
        
        order = engine.submit_order(signal)
        
        # Should be REJECTED (need both cash AND equity)
        assert order.status == OrderStatus.REJECTED
        assert "account state" in order.rejection_reason.lower()
