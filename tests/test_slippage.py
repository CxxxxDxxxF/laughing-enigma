#!/usr/bin/env python3
"""Tests for deterministic slippage model."""

import pytest
from decimal import Decimal

from src.execution.slippage import (
    compute_slippage_ticks,
    apply_slippage_to_price,
    compute_gap_slippage_ticks,
    default_slippage_config_for,
    SlippageConfig,
    FUTURES_SLIPPAGE_CONFIG,
    EQUITY_SLIPPAGE_CONFIG,
)
from src.core.instrument_spec import ES_FUTURE, AAPL_EQUITY, NQ_FUTURE


class TestSlippageConfig:
    """Test SlippageConfig validation."""
    
    def test_valid_config(self):
        """Test valid config creation."""
        config = SlippageConfig(
            base_ticks=1,
            vol_sensitivity=2.0,
            max_ticks=10,
            order_type_multipliers={"MARKET": 1.0, "LIMIT": 0.0},
        )
        assert config.base_ticks == 1
        assert config.vol_sensitivity == 2.0
        assert config.max_ticks == 10
    
    def test_negative_base_ticks_raises(self):
        """Test negative base_ticks raises ValueError."""
        with pytest.raises(ValueError, match="base_ticks must be >= 0"):
            SlippageConfig(
                base_ticks=-1,
                vol_sensitivity=2.0,
                max_ticks=10,
                order_type_multipliers={"MARKET": 1.0},
            )
    
    def test_max_less_than_base_raises(self):
        """Test max_ticks < base_ticks raises ValueError."""
        with pytest.raises(ValueError, match="max_ticks.*must be >= base_ticks"):
            SlippageConfig(
                base_ticks=10,
                vol_sensitivity=2.0,
                max_ticks=5,
                order_type_multipliers={"MARKET": 1.0},
            )


class TestDefaultConfigs:
    """Test default config factories."""
    
    def test_futures_default(self):
        """Test futures get futures config."""
        config = default_slippage_config_for(ES_FUTURE)
        assert config == FUTURES_SLIPPAGE_CONFIG
        assert config.base_ticks == 1
        assert config.max_ticks == 10
    
    def test_equity_default(self):
        """Test equities get equity config."""
        config = default_slippage_config_for(AAPL_EQUITY)
        assert config == EQUITY_SLIPPAGE_CONFIG
        assert config.base_ticks == 2
        assert config.max_ticks == 20


class TestComputeSlippageTicks:
    """Test slippage tick computation."""
    
    def test_zero_vol_market_order(self):
        """Test market order with no volatility gives base slippage."""
        ticks = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="MARKET",
            vol_metric=0.0,
        )
        # Futures: base_ticks=1, order_multiplier=1.0
        assert ticks == 1
    
    def test_zero_vol_limit_order(self):
        """Test limit order with no volatility gives zero slippage."""
        ticks = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="LIMIT",
            vol_metric=0.0,
        )
        # Limit multiplier = 0.0
        assert ticks == 0
    
    def test_monotonic_in_vol(self):
        """Test slippage increases monotonically with volatility."""
        ticks_0 = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="MARKET",
            vol_metric=0.0,
        )
        
        ticks_1 = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="MARKET",
            vol_metric=1.0,
        )
        
        ticks_2 = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="MARKET",
            vol_metric=2.0,
        )
        
        assert ticks_0 <= ticks_1 <= ticks_2
    
    def test_bounded_by_max_ticks(self):
        """Test slippage capped at max_ticks."""
        # ES futures max_ticks = 10
        ticks = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="MARKET",
            vol_metric=100.0,  # Huge volatility
        )
        
        assert ticks == 10  # Capped at max
    
    def test_vol_sensitivity(self):
        """Test volatility scaling."""
        # Futures: base=1, vol_sensitivity=3.0, market_multiplier=1.0
        # vol_metric=1.0 => base + (3.0 * 1.0) = 1 + 3 = 4 ticks
        ticks = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="MARKET",
            vol_metric=1.0,
        )
        
        assert ticks == 4
    
    def test_equity_higher_base(self):
        """Test equities have higher base slippage."""
        futures_ticks = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="MARKET",
            vol_metric=0.0,
        )
        
        equity_ticks = compute_slippage_ticks(
            instrument=AAPL_EQUITY,
            order_type="MARKET",
            vol_metric=0.0,
        )
        
        # Equity base=2, Futures base=1
        assert equity_ticks > futures_ticks
    
    def test_stop_less_than_market(self):
        """Test stop orders have less slippage than market."""
        market_ticks = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="MARKET",
            vol_metric=1.0,
        )
        
        stop_ticks = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="STOP",
            vol_metric=1.0,
        )
        
        # Stop multiplier = 0.8 (less than market 1.0)
        assert stop_ticks <= market_ticks
    
    def test_negative_vol_raises(self):
        """Test negative vol_metric raises ValueError."""
        with pytest.raises(ValueError, match="vol_metric must be >= 0"):
            compute_slippage_ticks(
                instrument=ES_FUTURE,
                order_type="MARKET",
                vol_metric=-1.0,
            )
    
    def test_unknown_order_type_raises(self):
        """Test unknown order_type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown order_type"):
            compute_slippage_ticks(
                instrument=ES_FUTURE,
                order_type="INVALID",
                vol_metric=0.0,
            )
    
    def test_custom_config(self):
        """Test using custom config."""
        custom_config = SlippageConfig(
            base_ticks=5,
            vol_sensitivity=1.0,
            max_ticks=20,
            order_type_multipliers={"MARKET": 1.0, "STOP": 0.5, "LIMIT": 0.0},
        )
        
        ticks = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="MARKET",
            vol_metric=0.0,
            config=custom_config,
        )
        
        assert ticks == 5  # Custom base


class TestApplySlippageToPrice:
    """Test price adjustment with slippage."""
    
    def test_buy_increases_price(self):
        """Test BUY side increases price."""
        base_price = Decimal("4500.00")
        slippage_ticks = 4  # 4 * 0.25 = 1.00 point
        
        adjusted = apply_slippage_to_price(
            instrument=ES_FUTURE,
            side="BUY",
            base_price=base_price,
            slippage_ticks=slippage_ticks,
        )
        
        expected = Decimal("4501.00")  # 4500 + 1.00
        assert adjusted == expected
    
    def test_sell_decreases_price(self):
        """Test SELL side decreases price."""
        base_price = Decimal("4500.00")
        slippage_ticks = 4  # 4 * 0.25 = 1.00 point
        
        adjusted = apply_slippage_to_price(
            instrument=ES_FUTURE,
            side="SELL",
            base_price=base_price,
            slippage_ticks=slippage_ticks,
        )
        
        expected = Decimal("4499.00")  # 4500 - 1.00
        assert adjusted == expected
    
    def test_zero_slippage_no_change(self):
        """Test zero slippage returns original price."""
        base_price = Decimal("150.00")
        
        adjusted = apply_slippage_to_price(
            instrument=AAPL_EQUITY,
            side="BUY",
            base_price=base_price,
            slippage_ticks=0,
        )
        
        assert adjusted == base_price
    
    def test_tick_rounding(self):
        """Test result is tick-rounded."""
        base_price = Decimal("4500.00")
        slippage_ticks = 1  # 1 * 0.25 = 0.25
        
        adjusted = apply_slippage_to_price(
            instrument=ES_FUTURE,
            side="BUY",
            base_price=base_price,
            slippage_ticks=slippage_ticks,
        )
        
        # Should be on tick boundary
        assert adjusted % ES_FUTURE.tick_size == 0
        assert adjusted == Decimal("4500.25")
    
    def test_equity_penny_increment(self):
        """Test equity slippage in penny increments."""
        base_price = Decimal("150.00")
        slippage_ticks = 5  # 5 * 0.01 = 0.05
        
        adjusted = apply_slippage_to_price(
            instrument=AAPL_EQUITY,
            side="BUY",
            base_price=base_price,
            slippage_ticks=slippage_ticks,
        )
        
        assert adjusted == Decimal("150.05")
        assert adjusted % AAPL_EQUITY.tick_size == 0
    
    def test_invalid_side_raises(self):
        """Test invalid side raises ValueError."""
        with pytest.raises(ValueError, match="side must be"):
            apply_slippage_to_price(
                instrument=ES_FUTURE,
                side="INVALID",
                base_price=Decimal("4500.00"),
                slippage_ticks=1,
            )


class TestGapSlippage:
    """Test gap-specific slippage calculation."""
    
    def test_gap_adds_penalty(self):
        """Test gap adds penalty to base slippage."""
        base_slippage = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="STOP",
            vol_metric=0.0,
        )
        
        gap_slippage = compute_gap_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="STOP",
            gap_size_ticks=20,  # 20 tick gap
            vol_metric=0.0,
        )
        
        # Gap penalty = min(20 * 0.1, 5) = 2 ticks
        expected = base_slippage + 2
        assert gap_slippage == expected
    
    def test_gap_penalty_capped(self):
        """Test gap penalty capped at 5 ticks."""
        gap_slippage = compute_gap_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="STOP",
            gap_size_ticks=100,  # Huge gap
            vol_metric=0.0,
        )
        
        # Base (1) + gap penalty (max 5) = 6 ticks
        # (assuming stop multiplier 0.8: (1 + 0) * 0.8 = 0.8 rounded to 0, then +5 = 5)
        # Actually: base=1, vol_penalty=0, total before multiplier = 1
        # After multiplier 0.8: 0.8 -> 0
        # Then gap penalty: 0 + 5 = 5
        # Let me recalculate: base_slippage for STOP with vol=0 should give us some value
        base_slippage = compute_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="STOP",
            vol_metric=0.0,
        )
        # Futures: base=1, multiplier=0.8 => 1 * 0.8 = 0 (rounded down)
        assert base_slippage == 0
        
        # Gap penalty = min(100 * 0.1, 5) = 5
        expected = 0 + 5
        assert gap_slippage == expected
    
    def test_gap_slippage_bounded_by_max(self):
        """Test total gap slippage still bounded by max_ticks."""
        # Use high vol + large gap to exceed max
        gap_slippage = compute_gap_slippage_ticks(
            instrument=ES_FUTURE,
            order_type="MARKET",
            gap_size_ticks=100,
            vol_metric=10.0,  # High vol
        )
        
        # Should be capped at ES max_ticks = 10
        assert gap_slippage == 10


class TestDeterminism:
    """Test slippage is deterministic."""
    
    def test_same_inputs_same_output(self):
        """Test same inputs produce same slippage."""
        results = []
        for _ in range(5):
            ticks = compute_slippage_ticks(
                instrument=ES_FUTURE,
                order_type="MARKET",
                vol_metric=1.5,
            )
            results.append(ticks)
        
        # All results should be identical
        assert len(set(results)) == 1
    
    def test_price_adjustment_deterministic(self):
        """Test price adjustment is deterministic."""
        results = []
        for _ in range(5):
            adjusted = apply_slippage_to_price(
                instrument=ES_FUTURE,
                side="BUY",
                base_price=Decimal("4500.00"),
                slippage_ticks=3,
            )
            results.append(adjusted)
        
        # All results should be identical
        assert len(set(results)) == 1
