"""Golden-file assertions for deterministic backtest validation.

This module provides utilities to compare backtest results against
expected "golden" outputs stored as JSON files.
"""

import json
from pathlib import Path
from decimal import Decimal
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class GoldenExpectation:
    """Expected outputs from a deterministic backtest."""
    trades: List[Dict[str, Any]]
    final_cash: float
    final_pnl: float
    final_position_qty: int
    total_fills: int
    total_rejections: int


def load_golden(filepath: Path) -> GoldenExpectation:
    """Load golden expectations from JSON file.
    
    Args:
        filepath: Path to golden JSON file
        
    Returns:
        GoldenExpectation object
    """
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    return GoldenExpectation(
        trades=data.get("trades", []),
        final_cash=data.get("final_cash", 0.0),
        final_pnl=data.get("final_pnl", 0.0),
        final_position_qty=data.get("final_position_qty", 0),
        total_fills=data.get("total_fills", 0),
        total_rejections=data.get("total_rejections", 0),
    )


def save_golden(filepath: Path, result: Dict[str, Any]) -> None:
    """Save backtest result as golden file.
    
    Args:
        filepath: Path to save golden JSON
        result: Backtest result dict
    """
    with open(filepath, 'w') as f:
        json.dump(result, f, indent=2, default=str)


def assert_matches_golden(
    actual: Dict[str, Any],
    expected: GoldenExpectation,
    tolerance: float = 0.01
) -> List[str]:
    """Compare actual backtest result against golden expectation.
    
    Args:
        actual: Actual backtest result dict
        expected: Expected golden values
        tolerance: Tolerance for float comparisons
        
    Returns:
        List of discrepancy messages (empty if match)
    """
    discrepancies = []
    
    # Check trade count
    actual_trades = actual.get("trades", [])
    if len(actual_trades) != len(expected.trades):
        discrepancies.append(
            f"Trade count mismatch: got {len(actual_trades)}, expected {len(expected.trades)}"
        )
    else:
        # Check each trade
        for i, (act, exp) in enumerate(zip(actual_trades, expected.trades)):
            if act.get("side") != exp.get("side"):
                discrepancies.append(f"Trade {i} side mismatch: {act.get('side')} != {exp.get('side')}")
            if act.get("quantity") != exp.get("quantity"):
                discrepancies.append(f"Trade {i} qty mismatch: {act.get('quantity')} != {exp.get('quantity')}")
            
            # Price comparison with tolerance
            act_price = float(act.get("fill_price", 0))
            exp_price = float(exp.get("fill_price", 0))
            if abs(act_price - exp_price) > tolerance:
                discrepancies.append(f"Trade {i} price mismatch: {act_price} != {exp_price}")
    
    # Check final values
    actual_pnl = float(actual.get("final_pnl", 0))
    if abs(actual_pnl - expected.final_pnl) > tolerance:
        discrepancies.append(f"Final PnL mismatch: {actual_pnl} != {expected.final_pnl}")
    
    actual_pos = actual.get("final_position_qty", 0)
    if actual_pos != expected.final_position_qty:
        discrepancies.append(f"Final position mismatch: {actual_pos} != {expected.final_position_qty}")
    
    actual_fills = actual.get("total_fills", 0)
    if actual_fills != expected.total_fills:
        discrepancies.append(f"Total fills mismatch: {actual_fills} != {expected.total_fills}")
    
    actual_rejections = actual.get("total_rejections", 0)
    if actual_rejections != expected.total_rejections:
        discrepancies.append(f"Total rejections mismatch: {actual_rejections} != {expected.total_rejections}")
    
    return discrepancies


class InvariantChecker:
    """Check invariants at each bar during simulation."""
    
    def __init__(self, initial_cash: float, leverage_enabled: bool = False):
        self.initial_cash = initial_cash
        self.leverage_enabled = leverage_enabled
        self.violations: List[str] = []
    
    def check_bar(
        self,
        bar_index: int,
        cash: float,
        margin_used: float,
        cash_buffer: float,
        session_open: bool,
        fill_occurred: bool,
        is_exit: bool,
        order_rejected: bool,
        instrument_registered: bool,
        is_entry: bool,
    ) -> None:
        """Check all invariants for a bar.
        
        Args:
            bar_index: Current bar index
            cash: Current cash balance
            margin_used: Current margin used
            cash_buffer: Available cash buffer
            session_open: Whether market session is open
            fill_occurred: Whether a fill occurred this bar
            is_exit: Whether this was an exit order
            order_rejected: Whether order was rejected
            instrument_registered: Whether instrument is registered
            is_entry: Whether this was an entry order
        """
        # Invariant 1: No negative cash unless leverage enabled
        if not self.leverage_enabled and cash < 0:
            self.violations.append(
                f"Bar {bar_index}: Negative cash ({cash}) without leverage"
            )
        
        # Invariant 2: Margin used <= cash buffer
        if margin_used > cash_buffer:
            self.violations.append(
                f"Bar {bar_index}: Margin ({margin_used}) exceeds buffer ({cash_buffer})"
            )
        
        # Invariant 3: No fills when session closed
        if fill_occurred and not session_open:
            self.violations.append(
                f"Bar {bar_index}: Fill occurred with session closed"
            )
        
        # Invariant 4: No entry without instrument spec
        if is_entry and not instrument_registered:
            self.violations.append(
                f"Bar {bar_index}: Entry without registered instrument"
            )
        
        # Invariant 5: Exit orders never rejected
        if is_exit and order_rejected:
            self.violations.append(
                f"Bar {bar_index}: Exit order was rejected (CRITICAL)"
            )
    
    def get_violations(self) -> List[str]:
        """Get all invariant violations."""
        return self.violations
    
    def assert_no_violations(self) -> None:
        """Assert no invariant violations occurred."""
        if self.violations:
            raise AssertionError(
                f"Invariant violations detected:\n" + 
                "\n".join(f"  - {v}" for v in self.violations)
            )
