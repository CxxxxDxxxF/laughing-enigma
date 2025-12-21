"""Prop-firm survivability analysis.

This module computes metrics that answer:
- How close does a strategy run to rule limits?
- How often does it almost fail?
- How many "bad days" can it survive?

Key principle:
- Violation proximity matters more than violation count
- 0.95 utilization is worse than a single WARN
- Near-misses are early warning signals

Determinism:
- Same cycles → same survivability metrics
- No randomness, no smoothing tricks
- Pure aggregation of cycle results
"""

from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..lifecycle.state_store import PortfolioStateStore
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum


class CycleStatus(str, Enum):
    """Cycle status types."""
    COMPLETED = "completed"
    SKIPPED = "skipped"
    HALTED = "halted"


@dataclass
class SurvivabilityMetrics:
    """Survivability metrics for prop-firm rule compliance.
    
    These metrics measure how close a strategy runs to rule limits
    and how well it survives over time.
    
    Attributes:
        # Daily loss utilization
        daily_loss_utilization_avg: Average daily loss utilization (daily_loss / max_daily_loss)
        daily_loss_utilization_max: Maximum daily loss utilization
        daily_loss_utilization_p90: 90th percentile daily loss utilization
        
        # Trailing drawdown proximity
        trailing_drawdown_proximity_avg: Average trailing drawdown proximity (current / max)
        trailing_drawdown_proximity_max: Maximum trailing drawdown proximity
        min_distance_to_drawdown_violation: Minimum distance to drawdown violation (1.0 = at limit)
        
        # Turnover pressure
        turnover_pressure_avg: Average turnover pressure (turnover / max_turnover)
        turnover_pressure_max: Maximum turnover pressure
        
        # Survival metrics
        days_survived: Number of trading days survived before HALT (None if never halted)
        warn_only_cycles: Number of cycles with WARN violations but no HALT
        violation_free_streak_max: Maximum consecutive cycles with no violations
        violation_free_streak_current: Current violation-free streak length
        total_cycles: Total number of cycles analyzed
        completed_cycles: Number of completed cycles (status="completed")
        halted_cycles: Number of halted cycles (status="halted")
        
        # Summary statistics
        total_violations: Total number of violations across all cycles
        halt_violations: Total number of HALT violations
        warn_violations: Total number of WARN violations
    """
    
    # Daily loss utilization
    daily_loss_utilization_avg: Optional[float] = None
    daily_loss_utilization_max: Optional[float] = None
    daily_loss_utilization_p90: Optional[float] = None
    
    # Trailing drawdown proximity
    trailing_drawdown_proximity_avg: Optional[float] = None
    trailing_drawdown_proximity_max: Optional[float] = None
    min_distance_to_drawdown_violation: Optional[float] = None  # 1.0 = at limit, >1.0 = safe
    
    # Turnover pressure
    turnover_pressure_avg: Optional[float] = None
    turnover_pressure_max: Optional[float] = None
    
    # Survival metrics
    days_survived: Optional[int] = None  # Days until first HALT
    warn_only_cycles: int = 0
    violation_free_streak_max: int = 0
    violation_free_streak_current: int = 0
    total_cycles: int = 0
    completed_cycles: int = 0
    halted_cycles: int = 0
    
    # Summary statistics
    total_violations: int = 0
    halt_violations: int = 0
    warn_violations: int = 0
    
    # Control event metrics (from survivability controls)
    cap_binding_cycles: int = 0  # Number of cycles where position size cap was binding
    avg_utilization: Optional[float] = None  # Average position size utilization (cap binding events)
    max_utilization: Optional[float] = None  # Maximum position size utilization
    avg_cash_residual: Optional[float] = None  # Average cash residual from capped allocations
    max_cash_residual: Optional[float] = None  # Maximum cash residual
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "daily_loss_utilization": {
                "avg": self.daily_loss_utilization_avg,
                "max": self.daily_loss_utilization_max,
                "p90": self.daily_loss_utilization_p90,
            },
            "trailing_drawdown_proximity": {
                "avg": self.trailing_drawdown_proximity_avg,
                "max": self.trailing_drawdown_proximity_max,
                "min_distance_to_violation": self.min_distance_to_drawdown_violation,
            },
            "turnover_pressure": {
                "avg": self.turnover_pressure_avg,
                "max": self.turnover_pressure_max,
            },
            "survival": {
                "days_survived": self.days_survived,
                "warn_only_cycles": self.warn_only_cycles,
                "violation_free_streak_max": self.violation_free_streak_max,
                "violation_free_streak_current": self.violation_free_streak_current,
                "total_cycles": self.total_cycles,
                "completed_cycles": self.completed_cycles,
                "halted_cycles": self.halted_cycles,
            },
            "violations": {
                "total": self.total_violations,
                "halt": self.halt_violations,
                "warn": self.warn_violations,
            },
            "control_events": {
                "cap_binding_cycles": self.cap_binding_cycles,
                "avg_utilization": self.avg_utilization,
                "max_utilization": self.max_utilization,
                "avg_cash_residual": self.avg_cash_residual,
                "max_cash_residual": self.max_cash_residual,
            }
        }


def analyze_survivability(
    cycle_results: List[Any],
    artifact_store: Optional[Any] = None,
    state_store: Optional[Any] = None
) -> SurvivabilityMetrics:
    """Analyze survivability metrics from cycle results.
    
    This function aggregates cycle results to compute how close a strategy
    runs to prop-firm rule limits and how well it survives over time.
    
    Args:
        cycle_results: List of CycleResult objects or dicts (from lifecycle.runner)
        artifact_store: Optional artifact store (used for loading states if needed)
        state_store: Optional portfolio state store (used for loading drawdown tracker snapshots)
        
    Returns:
        SurvivabilityMetrics with aggregated analysis
        
    Note:
        - Cycles are processed in order (assumes chronological order)
        - Metrics are computed from available data (None if insufficient data)
        - Violation proximity is prioritized over violation count
        - If state_store is provided, extracts proximity metrics from drawdown tracker snapshots
          even when no violations occurred (measurement-only mode)
    """
    if not cycle_results:
        return SurvivabilityMetrics(total_cycles=0)
    
    # Extract metrics from cycles
    daily_loss_utilizations: List[float] = []
    trailing_drawdown_proximities: List[float] = []
    turnover_pressures: List[float] = []
    
    # Control event metrics
    control_utilizations: List[float] = []  # Position size utilization from control events
    cash_residuals: List[float] = []  # Cash residual from capped allocations
    
    total_violations = 0
    halt_violations = 0
    warn_violations = 0
    warn_only_cycles = 0
    completed_cycles = 0
    halted_cycles = 0
    cap_binding_cycles = 0
    
    violation_free_streak_current = 0
    violation_free_streak_max = 0
    first_halt_cycle_idx = None
    
    # Process each cycle
    for idx, cycle in enumerate(cycle_results):
        status = cycle.status if hasattr(cycle, 'status') else cycle.get('status', 'unknown')
        
        if status == "completed":
            completed_cycles += 1
        elif status == "halted":
            halted_cycles += 1
            if first_halt_cycle_idx is None:
                first_halt_cycle_idx = idx
        
        # Extract violations
        violations = cycle.rules_violations if hasattr(cycle, 'rules_violations') else cycle.get('rules_violations', [])
        if violations is None:
            violations = []
        
        # Convert dict violations to objects if needed
        violation_list = violations if isinstance(violations, list) else []
        
        cycle_has_halt = False
        cycle_has_warn = False
        
        for v in violation_list:
            total_violations += 1
            severity = v.severity if hasattr(v, 'severity') else v.get('severity', 'warn')
            if severity == 'halt':
                halt_violations += 1
                cycle_has_halt = True
            elif severity == 'warn':
                warn_violations += 1
                cycle_has_warn = True
        
        # Track warn-only cycles
        if cycle_has_warn and not cycle_has_halt:
            warn_only_cycles += 1
        
        # Track violation-free streaks
        if not violation_list:
            violation_free_streak_current += 1
            violation_free_streak_max = max(violation_free_streak_max, violation_free_streak_current)
        else:
            violation_free_streak_current = 0
        
        # Extract daily loss utilization
        # Daily loss utilization = daily_loss / max_daily_loss
        # We extract this from violation metadata (which includes equity and initial_balance)
        # OR from drawdown tracker snapshots if state_store is available (measurement-only mode)
        ruleset_config = cycle.ruleset_config if hasattr(cycle, 'ruleset_config') else cycle.get('ruleset_config', {})
        max_daily_loss = ruleset_config.get('max_daily_loss') if isinstance(ruleset_config, dict) else None
        
        if max_daily_loss is not None and max_daily_loss < 0:  # Negative value means loss
            # First, try to extract from violations (if any)
            seen_utilizations = set()
            for v in violation_list:
                code = v.code if hasattr(v, 'code') else v.get('code', '')
                metadata = v.metadata if hasattr(v, 'metadata') else v.get('metadata', {})
                
                if 'DAILY_LOSS' in code or 'daily_loss' in metadata:
                    # Extract daily_loss directly or compute from equity and initial_balance
                    daily_loss = metadata.get('daily_loss')
                    if daily_loss is None and 'equity' in metadata and 'initial_balance' in metadata:
                        daily_loss = metadata['equity'] - metadata['initial_balance']
                    
                    if daily_loss is not None and daily_loss < 0:  # Loss is negative
                        utilization = abs(daily_loss) / abs(max_daily_loss)
                        util_key = round(utilization, 6)
                        if util_key not in seen_utilizations:
                            daily_loss_utilizations.append(utilization)
                            seen_utilizations.add(util_key)
                else:
                    # Also check all violations for equity/initial_balance metadata (even if not DAILY_LOSS code)
                    if 'equity' in metadata and 'initial_balance' in metadata:
                        equity = metadata['equity']
                        initial_balance = metadata['initial_balance']
                        daily_loss = equity - initial_balance
                        if daily_loss < 0:
                            utilization = abs(daily_loss) / abs(max_daily_loss)
                            util_key = round(utilization, 6)
                            if util_key not in seen_utilizations:
                                daily_loss_utilizations.append(utilization)
                                seen_utilizations.add(util_key)
            
            # Extract from drawdown tracker snapshots if state_store is available (measurement-only mode)
            # This extracts proximity even when no violations occurred
            if state_store is not None:
                state_after_id = cycle.state_after_id if hasattr(cycle, 'state_after_id') else cycle.get('state_after_id')
                portfolio_id = cycle.portfolio_id if hasattr(cycle, 'portfolio_id') else cycle.get('portfolio_id')
                
                if state_after_id and portfolio_id:
                    try:
                        state = state_store._load_state(portfolio_id, state_after_id)
                        if state.drawdown_tracker and state.drawdown_tracker.snapshots:
                            # Use the latest snapshot (most recent state)
                            latest_snapshot = state.drawdown_tracker.snapshots[-1]
                            # Daily loss = equity - initial_balance (negative if losing)
                            daily_loss = latest_snapshot.equity - latest_snapshot.initial_balance
                            if daily_loss < 0:  # Only record losses
                                utilization = abs(daily_loss) / abs(max_daily_loss)
                                util_key = round(utilization, 6)
                                if util_key not in seen_utilizations:
                                    daily_loss_utilizations.append(utilization)
                                    seen_utilizations.add(util_key)
                    except Exception as e:
                        # Silently continue if state loading fails (measurement-only)
                        pass
        
        # Extract control events (position size cap bindings)
        control_events = cycle.survivability_control_events if hasattr(cycle, 'survivability_control_events') else cycle.get('survivability_control_events', [])
        if control_events is None:
            control_events = []
        
        cycle_has_cap_binding = False
        for event in control_events:
            event_dict = event if isinstance(event, dict) else (event.to_dict() if hasattr(event, 'to_dict') else {})
            code = event_dict.get('code', '')
            metadata = event_dict.get('metadata', {})
            
            if code == "POSITION_SIZE_CAP_BINDING":
                cycle_has_cap_binding = True
                utilization = metadata.get('utilization')
                if utilization is not None:
                    control_utilizations.append(utilization)
                
                # Extract capped_amount as cash residual proxy
                capped_amount = metadata.get('capped_amount')
                if capped_amount is not None:
                    cash_residuals.append(capped_amount)
        
        if cycle_has_cap_binding:
            cap_binding_cycles += 1
        
        # Extract trailing drawdown proximity
        # Compute from drawdown tracker snapshots, not from violations
        # For each snapshot:
        #   - Compute drawdown = max(0, high_water_mark - equity)
        #   - Compute proximity = drawdown_amount / max_drawdown_amount
        #   - max_drawdown_amount = high_water_mark * (max_trailing_drawdown_pct / 100.0)
        #   - This is equivalent to: proximity = trailing_drawdown_pct / max_trailing_drawdown_pct
        # Include proximity even if is_locked later becomes false (don't gate on lock state)
        max_trailing_drawdown_pct = ruleset_config.get('max_trailing_drawdown_pct') if isinstance(ruleset_config, dict) else None
        
        if max_trailing_drawdown_pct is not None and max_trailing_drawdown_pct > 0:
            # Extract from drawdown tracker snapshots (measurement-only mode)
            # Process ALL snapshots, not just the latest
            if state_store is not None:
                state_after_id = cycle.state_after_id if hasattr(cycle, 'state_after_id') else cycle.get('state_after_id')
                portfolio_id = cycle.portfolio_id if hasattr(cycle, 'portfolio_id') else cycle.get('portfolio_id')
                
                if state_after_id and portfolio_id:
                    try:
                        state = state_store._load_state(portfolio_id, state_after_id)
                        if state.drawdown_tracker and state.drawdown_tracker.snapshots:
                            # Process all snapshots to compute proximity
                            for snapshot in state.drawdown_tracker.snapshots:
                                # Compute drawdown from high_water_mark and equity
                                drawdown_amount = max(0.0, snapshot.high_water_mark - snapshot.equity)
                                
                                # Compute max drawdown amount from percentage limit
                                if snapshot.high_water_mark > 0:
                                    max_drawdown_amount = snapshot.high_water_mark * (max_trailing_drawdown_pct / 100.0)
                                    
                                    if max_drawdown_amount > 0:
                                        # Compute proximity = drawdown / max_drawdown
                                        proximity = drawdown_amount / max_drawdown_amount
                                        # Include proximity even if drawdown is zero (measurement completeness)
                                        trailing_drawdown_proximities.append(proximity)
                    except Exception as e:
                        # Silently continue if state loading fails (measurement-only)
                        pass
            
            # Also extract from violations (for completeness, but snapshot-based is primary)
            for v in violation_list:
                metadata = v.metadata if hasattr(v, 'metadata') else v.get('metadata', {})
                trailing_drawdown_pct = metadata.get('trailing_drawdown_pct')
                
                if trailing_drawdown_pct is not None and trailing_drawdown_pct >= 0:
                    proximity = trailing_drawdown_pct / max_trailing_drawdown_pct
                    trailing_drawdown_proximities.append(proximity)
        
        # Extract turnover pressure from rebalance summary
        summary = cycle.summary if hasattr(cycle, 'summary') else cycle.get('summary', {})
        rebalance_summary = summary.get('rebalance_summary', {}) if isinstance(summary, dict) else {}
        
        if isinstance(rebalance_summary, dict):
            total_turnover = rebalance_summary.get('total_turnover', 0.0)
            total_capital = summary.get('allocation_summary', {}).get('total_capital', 1.0)
            turnover_pct = (total_turnover / total_capital * 100.0) if total_capital > 0 else 0.0
            
            max_turnover_pct = ruleset_config.get('max_turnover_pct') if isinstance(ruleset_config, dict) else None
            
            if max_turnover_pct is not None and max_turnover_pct > 0:
                pressure = turnover_pct / max_turnover_pct
                turnover_pressures.append(pressure)
    
    # Compute aggregate metrics
    daily_loss_utilization_avg = None
    daily_loss_utilization_max = None
    daily_loss_utilization_p90 = None
    
    if daily_loss_utilizations:
        sorted_utilizations = sorted(daily_loss_utilizations)
        daily_loss_utilization_avg = sum(sorted_utilizations) / len(sorted_utilizations)
        daily_loss_utilization_max = max(sorted_utilizations)
        p90_idx = int(len(sorted_utilizations) * 0.9)
        daily_loss_utilization_p90 = sorted_utilizations[p90_idx] if p90_idx < len(sorted_utilizations) else sorted_utilizations[-1]
    
    trailing_drawdown_proximity_avg = None
    trailing_drawdown_proximity_max = None
    min_distance_to_drawdown_violation = None
    
    if trailing_drawdown_proximities:
        sorted_proximities = sorted(trailing_drawdown_proximities)
        trailing_drawdown_proximity_avg = sum(sorted_proximities) / len(sorted_proximities)
        trailing_drawdown_proximity_max = max(sorted_proximities)
        
        # Compute minimum distance to violation across all cycles
        # Distance = 1.0 - proximity (1.0 = at limit, >1.0 = safe, <0 = already violated)
        # We want the minimum distance (closest we got to violation)
        distances = [max(0.0, 1.0 - p) for p in sorted_proximities]
        min_distance_to_drawdown_violation = min(distances) if distances else None
    
    # Validation assertion: If lock_in_ever_occurred == True and any snapshot has equity < high_water_mark,
    # then trailing drawdown proximity must be > 0 for at least one cycle
    # This is a measurement validation, not a business logic change
    lock_in_ever_occurred = False
    any_equity_below_hwm = False
    
    if state_store is not None:
        # Check all cycles for lock-in occurrence and equity below HWM
        for cycle in cycle_results:
            state_after_id = cycle.state_after_id if hasattr(cycle, 'state_after_id') else cycle.get('state_after_id')
            portfolio_id = cycle.portfolio_id if hasattr(cycle, 'portfolio_id') else cycle.get('portfolio_id')
            
            if state_after_id and portfolio_id:
                try:
                    state = state_store._load_state(portfolio_id, state_after_id)
                    if state.drawdown_tracker:
                        # Check if lock ever occurred
                        if state.drawdown_tracker.is_locked:
                            lock_in_ever_occurred = True
                        
                        # Check if any snapshot has equity < high_water_mark (drawdown exists)
                        if state.drawdown_tracker.snapshots:
                            for snapshot in state.drawdown_tracker.snapshots:
                                if snapshot.equity < snapshot.high_water_mark:
                                    any_equity_below_hwm = True
                                    break
                except Exception:
                    # Silently continue if state loading fails (validation only)
                    pass
    
    # Validation warning if measurement error detected
    if lock_in_ever_occurred and any_equity_below_hwm:
        if not trailing_drawdown_proximities or max(trailing_drawdown_proximities, default=0.0) == 0.0:
            # This is a measurement error - we should have proximity > 0
            import warnings
            warnings.warn(
                f"VALIDATION WARNING: Lock-in occurred and equity < high_water_mark detected, "
                f"but trailing_drawdown_proximity is zero or missing. "
                f"This indicates a measurement error in survivability analysis.",
                UserWarning
            )
    
    turnover_pressure_avg = None
    turnover_pressure_max = None
    
    if turnover_pressures:
        turnover_pressure_avg = sum(turnover_pressures) / len(turnover_pressures)
        turnover_pressure_max = max(turnover_pressures)
    
    # Compute control event metrics
    avg_utilization = None
    max_utilization = None
    if control_utilizations:
        avg_utilization = sum(control_utilizations) / len(control_utilizations)
        max_utilization = max(control_utilizations)
    
    avg_cash_residual = None
    max_cash_residual = None
    if cash_residuals:
        avg_cash_residual = sum(cash_residuals) / len(cash_residuals)
        max_cash_residual = max(cash_residuals)
    
    # Compute days survived (estimate from cycle timestamps)
    days_survived = None
    if first_halt_cycle_idx is not None and first_halt_cycle_idx > 0:
        # Estimate days from cycle count (assuming roughly daily cycles)
        days_survived = first_halt_cycle_idx
    elif first_halt_cycle_idx == 0:
        days_survived = 0
    
    return SurvivabilityMetrics(
        daily_loss_utilization_avg=daily_loss_utilization_avg,
        daily_loss_utilization_max=daily_loss_utilization_max,
        daily_loss_utilization_p90=daily_loss_utilization_p90,
        trailing_drawdown_proximity_avg=trailing_drawdown_proximity_avg,
        trailing_drawdown_proximity_max=trailing_drawdown_proximity_max,
        min_distance_to_drawdown_violation=min_distance_to_drawdown_violation,
        turnover_pressure_avg=turnover_pressure_avg,
        turnover_pressure_max=turnover_pressure_max,
        days_survived=days_survived,
        warn_only_cycles=warn_only_cycles,
        violation_free_streak_max=violation_free_streak_max,
        violation_free_streak_current=violation_free_streak_current,
        total_cycles=len(cycle_results),
        completed_cycles=completed_cycles,
        halted_cycles=halted_cycles,
        total_violations=total_violations,
        halt_violations=halt_violations,
        warn_violations=warn_violations,
        cap_binding_cycles=cap_binding_cycles,
        avg_utilization=avg_utilization,
        max_utilization=max_utilization,
        avg_cash_residual=avg_cash_residual,
        max_cash_residual=max_cash_residual,
    )

