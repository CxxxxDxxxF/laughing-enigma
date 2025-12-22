"""Topstep prop firm rules implementation.

This module implements Topstep-style trading rules in a broker-agnostic way.
All thresholds are configurable (no hardcoded values).

For ambiguous or unclear rules, this implementation returns WARN violations
with code="TOPSTEP_RULE_UNSPECIFIED" to allow manual review.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import date

from .base import Ruleset, RulesViolation, RulesViolationSeverity, RulesetError
from .drawdown import DrawdownTracker, calculate_portfolio_equity


@dataclass
class TopstepRulesConfig:
    """Configuration for Topstep ruleset.
    
    All thresholds are configurable. Set to None to disable a rule.
    
    Attributes:
        max_turnover_pct: Maximum turnover as % of account (default: None = no limit)
        max_position_size: Maximum position size in units (default: None = no limit)
        max_daily_loss: Maximum daily loss in absolute terms (default: None = no limit)
        account_size: Account size for percentage calculations (required if using pct rules)
        
    Note:
        - max_position_size is checked against individual position sizes
        - max_daily_loss is checked against realized PnL from fills in the session
        - Trailing drawdown and other complex rules are not yet implemented
          (will return WARN violations with TOPSTEP_RULE_UNSPECIFIED)
    """
    
    max_turnover_pct: Optional[float] = None
    max_position_size: Optional[float] = None
    max_daily_loss: Optional[float] = None
    max_trailing_drawdown_pct: Optional[float] = None
    account_size: Optional[float] = None
    
    def __post_init__(self):
        """Validate config."""
        if self.max_turnover_pct is not None and self.account_size is None:
            raise ValueError(
                "account_size must be provided when max_turnover_pct is set"
            )
        
        if self.max_turnover_pct is not None and self.max_turnover_pct <= 0:
            raise ValueError(
                f"max_turnover_pct must be positive, got: {self.max_turnover_pct}"
            )
        
        if self.max_position_size is not None and self.max_position_size <= 0:
            raise ValueError(
                f"max_position_size must be positive, got: {self.max_position_size}"
            )
        
        if self.max_daily_loss is not None and self.max_daily_loss >= 0:
            raise ValueError(
                f"max_daily_loss must be negative (loss), got: {self.max_daily_loss}"
            )
        
        if self.max_trailing_drawdown_pct is not None:
            if self.max_trailing_drawdown_pct <= 0 or self.max_trailing_drawdown_pct > 100:
                raise ValueError(
                    f"max_trailing_drawdown_pct must be between 0 and 100, got: {self.max_trailing_drawdown_pct}"
                )


class TopstepRuleset(Ruleset):
    """Topstep prop firm ruleset implementation.
    
    This ruleset validates rebalance plans and execution results according to
    Topstep-style rules. All thresholds are configurable via TopstepRulesConfig.
    
    Implemented rules:
        - max_turnover_pct: Maximum turnover per cycle
        - max_position_size: Maximum position size
        - max_daily_loss: Maximum daily loss (based on realized PnL)
    
    Unimplemented/ambiguous rules:
        - Trailing drawdown (returns WARN with TOPSTEP_RULE_UNSPECIFIED)
        - Complex drawdown calculations (returns WARN)
    
    Determinism:
        Same inputs + same config → same violations
    """
    
    def __init__(self, config: TopstepRulesConfig):
        """Initialize Topstep ruleset.
        
        Args:
            config: Topstep rules configuration
        """
        self.config = config
    
    def validate_plan(
        self,
        rebalance_plan: Any,
        current_state: Any
    ) -> List[RulesViolation]:
        """Validate rebalance plan against Topstep rules.
        
        Checks:
        - max_turnover_pct: Total turnover must not exceed limit
        - max_position_size: Target positions must not exceed limit
        
        Args:
            rebalance_plan: RebalancePlan from rebalance.planner
            current_state: CurrentPortfolioState
            
        Returns:
            List of violations (empty if valid)
        """
        violations: List[RulesViolation] = []
        
        try:
            # Check max_turnover_pct
            if self.config.max_turnover_pct is not None:
                total_turnover = rebalance_plan.metrics.get("total_turnover", 0.0)
                turnover_pct = (total_turnover / current_state.total_capital * 100.0) if current_state.total_capital > 0 else 0.0
                
                if turnover_pct > self.config.max_turnover_pct:
                    violations.append(RulesViolation(
                        code="TOPSTEP_MAX_TURNOVER_EXCEEDED",
                        message=f"Turnover {turnover_pct:.2f}% exceeds maximum {self.config.max_turnover_pct:.2f}%",
                        severity=RulesViolationSeverity.HALT,
                        metadata={
                            "turnover_pct": turnover_pct,
                            "max_turnover_pct": self.config.max_turnover_pct,
                            "total_turnover": total_turnover,
                            "total_capital": current_state.total_capital,
                        }
                    ))
            
            # Check max_position_size (requires prices, defer to execution validation)
            # Position size validation is better done at execution time when we have actual positions
            
            # Trailing drawdown is checked at execution time (not at plan time)
            # because it requires current equity calculation from positions and prices
            
        except Exception as e:
            raise RulesetError(f"Failed to validate plan: {e}") from e
        
        return violations
    
    def validate_execution(
        self,
        execution_result: Any,
        current_state: Any,
        execution_engine: Optional[Any] = None,
        current_prices: Optional[Dict[str, float]] = None,
        day_boundary: Optional['TradingDayBoundary'] = None,
        skip_equity_recalculation: bool = False  # Phase 15: when True, use precomputed equity from tracker
    ) -> List[RulesViolation]:
        """Validate execution results against Topstep rules.
        
        Checks:
        - max_daily_loss: Daily loss (realized + unrealized PnL) must not exceed limit
        - max_position_size: Final positions must not exceed limit
        - max_trailing_drawdown_pct: Trailing drawdown must not exceed limit
        
        Args:
            execution_result: RebalanceExecutionResult from rebalance.executor
            current_state: Portfolio state before execution
            execution_engine: Optional execution engine to get positions (for position size checks)
            current_prices: Optional dictionary of instrument -> current price (for equity calculation)
            
        Returns:
            List of violations (empty if valid)
        """
        violations: List[RulesViolation] = []
        
        try:
            if execution_engine is None:
                # Cannot validate without execution engine
                return violations
            
            # Get positions from execution engine
            positions = execution_engine.positions if hasattr(execution_engine, 'positions') else {}
            
            # Get or initialize drawdown tracker from current state
            drawdown_tracker = current_state.drawdown_tracker if hasattr(current_state, 'drawdown_tracker') else None
            
            # Calculate equity and PnL
            initial_cash = current_state.total_capital
            total_realized_pnl = 0.0
            
            # Sum realized PnL from all positions
            for position in positions.values():
                total_realized_pnl += position.realized_pnl
            
            # Calculate current equity and unrealized PnL
            # Phase 15: In validation_hold_quantity mode, equity is precomputed and tracker is already updated
            # Skip recalculation to avoid overwriting measurement-only equity updates
            if skip_equity_recalculation and drawdown_tracker and drawdown_tracker.snapshots:
                # Use equity from the most recent snapshot (already computed correctly in hold-quantity mode)
                latest_snapshot = drawdown_tracker.snapshots[-1]
                equity = latest_snapshot.equity
                unrealized_pnl = latest_snapshot.unrealized_pnl
            elif current_prices is None:
                # If no prices provided, we can't calculate unrealized PnL
                # Use realized PnL only as conservative estimate
                equity = initial_cash + total_realized_pnl
                unrealized_pnl = 0.0
            else:
                equity, unrealized_pnl = calculate_portfolio_equity(
                    initial_cash=initial_cash,
                    positions=positions,
                    current_prices=current_prices,
                    realized_pnl=total_realized_pnl
                )
            
            # Initialize or update drawdown tracker
            if drawdown_tracker is None:
                # Initialize new tracker for this session/day
                from datetime import date as date_class
                drawdown_tracker = DrawdownTracker(
                    initial_balance=initial_cash,
                    trading_date=date_class.today()
                )
                # Store it back in current_state so it persists (CurrentPortfolioState is not frozen)
                if hasattr(current_state, 'drawdown_tracker'):
                    current_state.drawdown_tracker = drawdown_tracker
            
            # Use day boundary for day rollover detection
            if day_boundary is None:
                from .day_boundary import TradingDayBoundary
                day_boundary = TradingDayBoundary()  # Default: UTC, midnight
            
            # Phase 15: Only update tracker if we're not skipping equity recalculation
            # (When skip_equity_recalculation=True, tracker is already updated with correct equity)
            if not skip_equity_recalculation:
                snapshot = drawdown_tracker.update(
                    equity=equity,
                    realized_pnl=total_realized_pnl,
                    unrealized_pnl=unrealized_pnl,
                    timestamp=execution_result.execution_timestamp,
                    day_boundary=day_boundary
                )
            else:
                # Use existing snapshot (tracker already updated with correct equity in hold-quantity mode)
                # Just get the latest snapshot without updating
                if drawdown_tracker and drawdown_tracker.snapshots:
                    snapshot = drawdown_tracker.snapshots[-1]
                else:
                    snapshot = None
            
            # Invariant check: Once locked, is_locked must never revert to false
            if drawdown_tracker.is_locked == False and current_state.drawdown_tracker and current_state.drawdown_tracker.is_locked:
                violations.append(RulesViolation(
                    code="DRAW_DOWN_STATE_CORRUPTION",
                    message="Drawdown tracker lock state corrupted: tracker was locked but is now unlocked",
                    severity=RulesViolationSeverity.HALT,
                    metadata={
                        "previous_is_locked": True,
                        "current_is_locked": False,
                        "previous_high_water_mark": current_state.drawdown_tracker.high_water_mark if current_state.drawdown_tracker else None,
                        "current_high_water_mark": drawdown_tracker.high_water_mark,
                    }
                ))
            
            # Check max_daily_loss
            if self.config.max_daily_loss is not None:
                daily_loss = snapshot.equity - snapshot.initial_balance
                if daily_loss <= self.config.max_daily_loss:
                    violations.append(RulesViolation(
                        code="TOPSTEP_MAX_DAILY_LOSS_EXCEEDED",
                        message=f"Daily loss {daily_loss:.2f} exceeds maximum {self.config.max_daily_loss:.2f}",
                        severity=RulesViolationSeverity.HALT,
                        metadata={
                            "daily_loss": daily_loss,
                            "max_daily_loss": self.config.max_daily_loss,
                            "equity": snapshot.equity,
                            "initial_balance": snapshot.initial_balance,
                            "realized_pnl": total_realized_pnl,
                            "unrealized_pnl": unrealized_pnl,
                        }
                    ))
            
            # Check max_trailing_drawdown_pct
            if self.config.max_trailing_drawdown_pct is not None:
                if snapshot.state.value == "locked" and snapshot.trailing_drawdown_pct > self.config.max_trailing_drawdown_pct:
                    violations.append(RulesViolation(
                        code="TOPSTEP_MAX_TRAILING_DRAWDOWN_EXCEEDED",
                        message=f"Trailing drawdown {snapshot.trailing_drawdown_pct:.2f}% exceeds maximum {self.config.max_trailing_drawdown_pct:.2f}%",
                        severity=RulesViolationSeverity.HALT,
                        metadata={
                            "trailing_drawdown_pct": snapshot.trailing_drawdown_pct,
                            "max_trailing_drawdown_pct": self.config.max_trailing_drawdown_pct,
                            "trailing_drawdown": snapshot.trailing_drawdown,
                            "high_water_mark": snapshot.high_water_mark,
                            "equity": snapshot.equity,
                            "state": snapshot.state.value,
                        }
                    ))
            
            # Check max_position_size
            if self.config.max_position_size is not None:
                for instrument, position in positions.items():
                    position_size = abs(position.quantity)
                    if position_size > self.config.max_position_size:
                        violations.append(RulesViolation(
                            code="TOPSTEP_MAX_POSITION_SIZE_EXCEEDED",
                            message=f"Position size {position_size} for {instrument} exceeds maximum {self.config.max_position_size}",
                            severity=RulesViolationSeverity.HALT,
                            metadata={
                                "instrument": instrument,
                                "position_size": position_size,
                                "max_position_size": self.config.max_position_size,
                                "quantity": position.quantity,
                            }
                        ))
            
        except Exception as e:
            raise RulesetError(f"Failed to validate execution: {e}") from e
        
        return violations

