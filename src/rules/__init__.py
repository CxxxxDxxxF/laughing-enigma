"""Ruleset layer for broker-agnostic trading rules.

This module provides a framework for enforcing trading rules (e.g., Topstep,
prop firm rules) in a broker-agnostic way.
"""

from .base import (
    Ruleset,
    RulesViolation,
    RulesViolationSeverity,
    RulesetError,
)
from .topstep import (
    TopstepRulesConfig,
    TopstepRuleset,
)
from .drawdown import (
    DrawdownTracker,
    DrawdownSnapshot,
    DrawdownState,
    calculate_portfolio_equity,
)
from .day_boundary import (
    TradingDayBoundary,
    reset_daily_loss_for_new_day,
)

__all__ = [
    "Ruleset",
    "RulesViolation",
    "RulesViolationSeverity",
    "RulesetError",
    "TopstepRulesConfig",
    "TopstepRuleset",
    "DrawdownTracker",
    "DrawdownSnapshot",
    "DrawdownState",
    "calculate_portfolio_equity",
    "TradingDayBoundary",
    "reset_daily_loss_for_new_day",
]

