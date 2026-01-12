#!/usr/bin/env python3
"""Tests for position sizing and risk enforcement."""

import pytest
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.execution.position_sizing import (
    can_open_position,
    AccountState,
    PortfolioState,
    PositionState,
    RiskPolicy,
    PositionDecision,
    DEFAULT_RISK_POLICY,
)
from src.core.instrument_spec import ES_FUTURE, AAPL_EQUITY, NQ_FUTURE
from src.core.market_session import create_cme_session_engine, create_equity_session_engine


class TestAccountState:
    """Test AccountState validation."""
    
    def test_valid_account_state(self):
        """Test valid account state creation."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
            margin_used=Decimal("10000"),
        )
        assert account.equity == Decimal("100000")
        assert account.cash == Decimal("50000")
   
    def test_negative_equity_raises(self):
        """Test negative equity raises ValueError."""
        with pytest.raises(ValueError, match="equity must be >= 0"):
            AccountState(
                equity=Decimal("-1000"),
                cash=Decimal("50000"),
            )


class TestRiskPolicy:
    """Test RiskPolicy validation."""
    
    def test_valid_policy(self):
        """Test valid policy creation."""
        policy = RiskPolicy(
            max_gross_exposure=0.9,
            max_position_fraction=0.15,
        )
        assert policy.max_gross_exposure == 0.9
    
    def test_invalid_gross_exposure_raises(self):
        """Test invalid gross exposure raises ValueError."""
        with pytest.raises(ValueError, match="max_gross_exposure"):
            RiskPolicy(max_gross_exposure=1.5)


class TestFuturesSizing:
    """Test futures position sizing."""
    
    def test_sufficient_margin_allowed(self):
        """Test position allowed when sufficient margin available."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
            margin_used=Decimal("0"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        # ES margin = $12,000 per contract
        # With 10% buffer: $13,200
        # 3 contracts = $39,600 total
        result = can_open_position(
            instrument=ES_FUTURE,
            quantity=3,
            price=Decimal("4500.00"),
            account=account,
            portfolio=portfolio,
        )
        
        assert result.allowed
        assert result.decision == PositionDecision.ALLOWED
        assert result.max_quantity == 3
    
    def test_insufficient_margin_denied(self):
        """Test position denied when insufficient margin."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("15000"),  # Only enough for 1 contract with buffer
            margin_used=Decimal("0"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        # Try to open 3 contracts (requires ~$39,600 with buffer)
        result = can_open_position(
            instrument=ES_FUTURE,
            quantity=3,
            price=Decimal("4500.00"),
            account=account,
            portfolio=portfolio,
        )
        
        assert not result.allowed
        assert result.decision == PositionDecision.INSUFFICIENT_MARGIN
        assert result.max_quantity == 1  # Can afford 1 contract
        assert "margin" in result.reason.lower()
    
    def test_exceeds_max_contracts_denied(self):
        """Test position denied when exceeds max contracts per symbol."""
        account = AccountState(
            equity=Decimal("1000000"),
            cash=Decimal("500000"),  # Plenty of margin
            margin_used=Decimal("0"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        # Default policy max_contracts_per_symbol = 5
        result = can_open_position(
            instrument=ES_FUTURE,
            quantity=10,  # Exceeds max
            price=Decimal("4500.00"),
            account=account,
            portfolio=portfolio,
        )
        
        assert not result.allowed
        assert result.decision == PositionDecision.EXCEEDS_POSITION_CAP
        assert result.max_quantity == 5
        assert "max" in result.reason.lower()
    
    def test_margin_buffer_applied(self):
        """Test margin buffer is correctly applied."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("13000"),  # Just under buffer requirement
            margin_used=Decimal("0"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        # ES margin = $12,000, buffer 10% = $1,200, total = $13,200
        result = can_open_position(
            instrument=ES_FUTURE,
            quantity=1,
            price=Decimal("4500.00"),
            account=account,
            portfolio=portfolio,
        )
        
        assert not result.allowed  # $13,000 < $13,200 required
        assert result.decision == PositionDecision.INSUFFICIENT_MARGIN


class TestEquitySizing:
    """Test equity position sizing."""
    
    def test_sufficient_cash_allowed(self):
        """Test position allowed when sufficient cash."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        # 100 shares @ $150 = $15,000
        result = can_open_position(
            instrument=AAPL_EQUITY,
            quantity=100,
            price=Decimal("150.00"),
            account=account,
            portfolio=portfolio,
        )
        
        assert result.allowed
        assert result.decision == PositionDecision.ALLOWED
    
    def test_insufficient_cash_denied(self):
        """Test position denied when insufficient cash."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("10000"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        # 100 shares @ $150 = $15,000 > $10,000 cash
        result = can_open_position(
            instrument=AAPL_EQUITY,
            quantity=100,
            price=Decimal("150.00"),
            account=account,
            portfolio=portfolio,
        )
        
        assert not result.allowed
        assert result.decision == PositionDecision.INSUFFICIENT_CASH
        assert result.max_quantity == 66  # $10,000 / $150 = 66 shares
    
    def test_exceeds_position_cap_denied(self):
        """Test position denied when exceeds per-position cap."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        # Max position = 20% of $100k = $20,000
        # 200 shares @ $150 = $30,000 > $20,000
        result = can_open_position(
            instrument=AAPL_EQUITY,
            quantity=200,
            price=Decimal("150.00"),
            account=account,
            portfolio=portfolio,
        )
        
        assert not result.allowed
        assert result.decision == PositionDecision.EXCEEDS_POSITION_CAP
        assert result.max_quantity == 133  # $20,000 / $150 = 133 shares
    
    def test_exceeds_gross_exposure_denied(self):
        """Test position denied when exceeds gross exposure limit."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
        )
        # Already have $90k in positions
        portfolio = PortfolioState(
            gross_exposure=Decimal("90000"),
            positions={},
        )
        
        # Max gross = 95% of $100k = $95,000
        # Current $90k + new $15k = $105k > $95k
        result = can_open_position(
            instrument=AAPL_EQUITY,
            quantity=100,
            price=Decimal("150.00"),
            account=account,
            portfolio=portfolio,
        )
        
        assert not result.allowed
        assert result.decision == PositionDecision.EXCEEDS_GROSS_EXPOSURE
        # Available exposure = $95k - $90k = $5k / $150 = 33 shares
        assert result.max_quantity == 33
    
    def test_short_selling_denied_by_default(self):
        """Test short selling denied by default policy."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        # Negative quantity = short
        result = can_open_position(
            instrument=AAPL_EQUITY,
            quantity=-100,  # Short
            price=Decimal("150.00"),
            account=account,
            portfolio=portfolio,
        )
        
        assert not result.allowed
        assert result.decision == PositionDecision.INVALID_INPUT
        assert "short" in result.reason.lower()


class TestSessionBlocking:
    """Test session-aware blocking."""
    
    def test_forced_flat_blocks_entry(self):
        """Test forced flat window blocks new entries."""
        session_engine = create_cme_session_engine(ES_FUTURE)
        
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        # Friday 3:50 PM CT - forced flat window (last 10 min)
        timestamp = datetime(2026, 1, 16, 15, 50, tzinfo=ZoneInfo("America/Chicago"))
        
        result = can_open_position(
            instrument=ES_FUTURE,
            quantity=1,
            price=Decimal("4500.00"),
            account=account,
            portfolio=portfolio,
            session_engine=session_engine,
            timestamp=timestamp,
        )
        
        assert not result.allowed
        assert result.decision == PositionDecision.SESSION_BLOCKED
        assert "session" in result.reason.lower()
    
    def test_normal_hours_allowed(self):
        """Test position allowed during normal hours."""
        session_engine = create_equity_session_engine(AAPL_EQUITY)
        
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        # Tuesday 2 PM ET - normal hours
        timestamp = datetime(2026, 1, 13, 14, 0, tzinfo=ZoneInfo("America/New_York"))
        
        result = can_open_position(
            instrument=AAPL_EQUITY,
            quantity=100,
            price=Decimal("150.00"),
            account=account,
            portfolio=portfolio,
            session_engine=session_engine,
            timestamp=timestamp,
        )
        
        assert result.allowed
        assert result.decision == PositionDecision.ALLOWED


class TestInputValidation:
    """Test input validation."""
    
    def test_zero_quantity_denied(self):
        """Test zero quantity denied."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        result = can_open_position(
            instrument=AAPL_EQUITY,
            quantity=0,
            price=Decimal("150.00"),
            account=account,
            portfolio=portfolio,
        )
        
        assert not result.allowed
        assert result.decision == PositionDecision.INVALID_INPUT
    
    def test_negative_price_denied(self):
        """Test negative price denied."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        result = can_open_position(
            instrument=AAPL_EQUITY,
            quantity=100,
            price=Decimal("-150.00"),
            account=account,
            portfolio=portfolio,
        )
        
        assert not result.allowed
        assert result.decision == PositionDecision.INVALID_INPUT


class TestDeterminism:
    """Test sizing is deterministic."""
    
    def test_same_inputs_same_output(self):
        """Test same inputs produce same result."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("10000"),
            positions={},
        )
        
        results = []
        for _ in range(5):
            result = can_open_position(
                instrument=AAPL_EQUITY,
                quantity=100,
                price=Decimal("150.00"),
                account=account,
                portfolio=portfolio,
            )
            results.append((result.allowed, result.decision, result.max_quantity))
        
        # All results should be identical
        assert len(set(results)) == 1
    
    def test_debug_output_stable(self):
        """Test debug output is deterministic."""
        account = AccountState(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
        )
        portfolio = PortfolioState(
            gross_exposure=Decimal("0"),
            positions={},
        )
        
        result1 = can_open_position(
            instrument=ES_FUTURE,
            quantity=2,
            price=Decimal("4500.00"),
            account=account,
            portfolio=portfolio,
        )
        
        result2 = can_open_position(
            instrument=ES_FUTURE,
            quantity=2,
            price=Decimal("4500.00"),
            account=account,
            portfolio=portfolio,
        )
        
        # Debug dicts should be identical
        assert result1.debug == result2.debug
