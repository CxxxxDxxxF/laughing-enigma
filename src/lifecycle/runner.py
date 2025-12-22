"""Portfolio lifecycle runner.

This module orchestrates the complete portfolio lifecycle:
1. Evaluate strategies (batch evaluation)
2. Allocate capital across top strategies
3. Plan rebalance from current state to target allocations
4. Execute rebalance plan through paper execution engine

This is pure orchestration - no new business logic, only wiring existing components.

Determinism guarantees:
- Same configs + same data → same cycle result
- No background state
- No mutable globals
- Deterministic execution order
"""

import json
import sys
import argparse
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from enum import Enum

from ..evaluation.batch import (
    BatchEvaluationConfig,
    run_batch_evaluation,
    StrategyEvaluation,
)
from ..allocation.allocator import (
    AllocationConfig,
    allocate_capital,
    AllocationResult,
)
from ..rebalance.planner import (
    RebalanceConfig,
    plan_rebalance,
    RebalancePlan,
    CurrentPortfolioState,
)
from ..rebalance.executor import (
    RebalanceSignalMapper,
    execute_rebalance_plan,
    RebalanceExecutionResult,
)
from ..engines.simple import SimpleResearchEngine
from ..core.artifacts import ArtifactStore, LocalArtifactStore
from ..execution import PaperExecutionEngine
from .state_store import PortfolioStateStore, LocalPortfolioStateStore
from .cadence import CycleCadenceConfig, check_cadence
from .guardrails import GuardrailsConfig, check_allocation_guardrails, check_rebalance_guardrails, check_execution_guardrails
from ..rules import Ruleset, RulesViolation, RulesViolationSeverity


class ExecutionMode(str, Enum):
    """Execution mode for portfolio cycles.
    
    SIMULATION: Allows relaxed constraints for testing/backtesting
    LIVE_DRY: Enforces strict LIVE constraints but does not place real orders (for testing/validation)
    LIVE: Enforces strict constraints for production trading with real orders
    """
    SIMULATION = "simulation"
    LIVE_DRY = "live_dry"
    LIVE = "live"


class CycleError(Exception):
    """Error raised when portfolio cycle execution fails."""
    pass


class CycleHaltError(CycleError):
    """Error raised when cycle halts in LIVE mode.
    
    This exception is raised instead of returning a halted CycleResult
    to prevent continuation after a halt in LIVE mode.
    """
    def __init__(self, message: str, result: 'CycleResult'):
        super().__init__(message)
        self.result = result


class HaltFlagStore:
    """Helper for managing persistent halt flags for portfolios.
    
    Halt flags are written to artifacts/portfolio/{portfolio_id}/HALTED
    and prevent cycles from running in LIVE mode until manually cleared.
    """
    
    def __init__(self, artifact_store: ArtifactStore):
        """Initialize halt flag store.
        
        Args:
            artifact_store: ArtifactStore instance for persistence
        """
        self.artifact_store = artifact_store
    
    def _get_halt_flag_path(self, portfolio_id: str) -> Path:
        """Get path for halt flag file.
        
        Args:
            portfolio_id: Portfolio identifier
            
        Returns:
            Path to halt flag file
        """
        # Get base path from artifact store
        if hasattr(self.artifact_store, 'base_path'):
            base_path = Path(self.artifact_store.base_path)
        else:
            base_path = Path("./artifacts")
        
        return base_path / "portfolio" / portfolio_id / "HALTED"
    
    def write_halt_flag(
        self,
        portfolio_id: str,
        cycle_id: str,
        reason: str,
        halted_at: datetime,
        violations_summary: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Write halt flag to disk (atomic write).
        
        Args:
            portfolio_id: Portfolio identifier
            cycle_id: Cycle ID that triggered the halt
            reason: Halt reason
            halted_at: Timestamp when halt occurred
            violations_summary: Optional list of violation dicts
            
        Raises:
            CycleError: If write fails
        """
        try:
            flag_path = self._get_halt_flag_path(portfolio_id)
            
            # Create data structure
            flag_data = {
                "halted_at": halted_at.isoformat(),
                "cycle_id": cycle_id,
                "reason": reason,
                "violations_summary": violations_summary or []
            }
            
            # Atomic write: write to temp file, then rename
            flag_json = json.dumps(flag_data, indent=2).encode('utf-8')
            temp_path = flag_path.with_suffix('.tmp')
            
            # Create parent directory if needed
            flag_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write to temp file
            temp_path.write_bytes(flag_json)
            
            # Atomic rename
            temp_path.replace(flag_path)
            
        except Exception as e:
            raise CycleError(f"Failed to write halt flag for portfolio {portfolio_id}: {e}") from e
    
    def halt_flag_exists(self, portfolio_id: str) -> bool:
        """Check if halt flag exists.
        
        Args:
            portfolio_id: Portfolio identifier
            
        Returns:
            True if halt flag exists, False otherwise
        """
        flag_path = self._get_halt_flag_path(portfolio_id)
        return flag_path.exists()
    
    def read_halt_flag(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        """Read halt flag data.
        
        Args:
            portfolio_id: Portfolio identifier
            
        Returns:
            Halt flag data as dict, or None if flag doesn't exist
            
        Raises:
            CycleError: If read fails
        """
        flag_path = self._get_halt_flag_path(portfolio_id)
        
        if not flag_path.exists():
            return None
        
        try:
            data = json.loads(flag_path.read_bytes().decode('utf-8'))
            return data
        except Exception as e:
            raise CycleError(f"Failed to read halt flag for portfolio {portfolio_id}: {e}") from e
    
    def clear_halt_flag(self, portfolio_id: str) -> None:
        """Clear halt flag (manual unhalt).
        
        Args:
            portfolio_id: Portfolio identifier
            
        Raises:
            CycleError: If clear fails
        """
        flag_path = self._get_halt_flag_path(portfolio_id)
        
        if not flag_path.exists():
            return  # Already cleared
        
        try:
            flag_path.unlink()
        except Exception as e:
            raise CycleError(f"Failed to clear halt flag for portfolio {portfolio_id}: {e}") from e


def _is_live_mode(execution_mode: ExecutionMode) -> bool:
    """Check if execution mode is LIVE or LIVE_DRY.
    
    Args:
        execution_mode: Execution mode
        
    Returns:
        True if mode is LIVE or LIVE_DRY (both enforce strict constraints)
    """
    return execution_mode in (ExecutionMode.LIVE, ExecutionMode.LIVE_DRY)


def _validate_live_mode_timestamps(
    execution_mode: ExecutionMode,
    cycle_timestamp: Optional[datetime]
) -> None:
    """Validate that timestamps are explicitly provided in LIVE/LIVE_DRY mode.
    
    Args:
        execution_mode: Execution mode
        cycle_timestamp: Cycle timestamp (must be explicitly provided in LIVE/LIVE_DRY mode, not None)
        
    Raises:
        CycleError: If LIVE/LIVE_DRY mode but timestamp is None (would be generated from datetime.now())
    """
    if _is_live_mode(execution_mode) and cycle_timestamp is None:
        raise CycleError("LIVE/LIVE_DRY mode requires explicit cycle_timestamp parameter (cannot use datetime.now() fallback)")


def _validate_live_mode_guardrails(
    execution_mode: ExecutionMode,
    guardrails_config: Optional[GuardrailsConfig]
) -> None:
    """Validate that guardrails are properly configured for LIVE/LIVE_DRY mode.
    
    Args:
        execution_mode: Execution mode
        guardrails_config: Guardrails configuration (should be non-permissive in LIVE/LIVE_DRY mode)
        
    Raises:
        CycleError: If LIVE/LIVE_DRY mode but guardrails are missing or too permissive
    """
    if not _is_live_mode(execution_mode):
        return
    
    if guardrails_config is None:
        raise CycleError("LIVE mode requires guardrails_config to be set")
    
    if guardrails_config.max_turnover_pct_per_cycle >= 1.0:
        raise CycleError(
            f"LIVE mode requires max_turnover_pct_per_cycle < 1.0, "
            f"got: {guardrails_config.max_turnover_pct_per_cycle}"
        )
    
    if guardrails_config.max_failed_intents is None:
        raise CycleError("LIVE mode requires max_failed_intents to be set")
    
    if guardrails_config.min_execution_success_rate <= 0.0:
        raise CycleError(
            f"LIVE mode requires min_execution_success_rate > 0.0, "
            f"got: {guardrails_config.min_execution_success_rate}"
        )
    
    if guardrails_config.max_single_strategy_allocation_fraction >= 1.0:
        raise CycleError(
            f"LIVE mode requires max_single_strategy_allocation_fraction < 1.0, "
            f"got: {guardrails_config.max_single_strategy_allocation_fraction}"
        )


def _validate_portfolio_not_halted(
    execution_mode: ExecutionMode,
    state_store: Optional[PortfolioStateStore],
    portfolio_id: str,
    artifact_store: ArtifactStore
) -> None:
    """Validate that portfolio is not in halted state in LIVE/LIVE_DRY mode.
    
    Args:
        execution_mode: Execution mode
        state_store: Portfolio state store (not used, kept for API compatibility)
        portfolio_id: Portfolio identifier
        artifact_store: Artifact store (used to check halt flag)
        
    Raises:
        CycleError: If LIVE/LIVE_DRY mode and portfolio is in halted state
    """
    if not _is_live_mode(execution_mode):
        return
    
    halt_store = HaltFlagStore(artifact_store)
    if halt_store.halt_flag_exists(portfolio_id):
        halt_data = halt_store.read_halt_flag(portfolio_id)
        reason = halt_data.get("reason", "Unknown") if halt_data else "Unknown"
        cycle_id = halt_data.get("cycle_id", "Unknown") if halt_data else "Unknown"
        raise CycleError(
            f"Portfolio {portfolio_id} is halted (halted at cycle {cycle_id}: {reason}). "
            "Manual intervention required before continuing. Use clear_halt_flag() to unhalt."
        )


def _validate_live_mode_cycle_id(
    execution_mode: ExecutionMode,
    cycle_id: Optional[str],
    config_cycle_id: Optional[str]
) -> None:
    """Validate that cycle_id is explicitly provided in LIVE/LIVE_DRY mode.
    
    Args:
        execution_mode: Execution mode
        cycle_id: Cycle ID parameter (may be None)
        config_cycle_id: Cycle ID from config (may be None)
        
    Raises:
        CycleError: If LIVE/LIVE_DRY mode but cycle_id is not explicitly provided
    """
    if _is_live_mode(execution_mode):
        if cycle_id is None and config_cycle_id is None:
            raise CycleError(
                "LIVE/LIVE_DRY mode requires explicit cycle_id parameter or config.cycle_id "
                "(cannot auto-generate from datetime.now())"
            )


@dataclass
class PortfolioCycleConfig:
    """Configuration for a complete portfolio cycle.
    
    This config contains all sub-configs needed to run a full cycle:
    evaluation → allocation → rebalance → execution
    
    Attributes:
        portfolio_id: Portfolio identifier (required for stateful operation)
        evaluation_config: Batch evaluation configuration
        allocation_config: Capital allocation configuration
        rebalance_config: Rebalance planning configuration
        execution_config: Rebalance execution configuration
            - price_by_strategy_or_instrument: Dict[str, float] - prices for execution
            - rounding_method: str - rounding method ("floor", "round", "ceil")
            - min_quantity: float - minimum quantity
        cadence_config: Optional cadence configuration (None = no cadence check)
        guardrails_config: Optional guardrails configuration (None = no guardrails)
        cycle_id: Optional cycle identifier (auto-generated if not provided)
    """
    
    portfolio_id: str
    evaluation_config: BatchEvaluationConfig
    allocation_config: AllocationConfig
    rebalance_config: RebalanceConfig
    execution_config: Dict[str, Any]
    cadence_config: Optional[CycleCadenceConfig] = None
    guardrails_config: Optional[GuardrailsConfig] = None
    ruleset_type: Optional[str] = None  # "topstep" or None
    ruleset_config: Optional[Dict[str, Any]] = None
    day_boundary_config: Optional[Dict[str, Any]] = None  # Trading day boundary config (timezone, session_start_time)
    cycle_id: Optional[str] = None
    validation_hold_quantity: bool = False  # Phase 15 validation-only: skip allocation/rebalance, hold positions
    validation_bootstrap_first_cycle: bool = True  # Phase 15: run cycle 1 normally to establish position
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PortfolioCycleConfig':
        """Load config from dictionary.
        
        Args:
            data: Dictionary containing config data
            
        Returns:
            PortfolioCycleConfig instance
            
        Raises:
            CycleError: If config is invalid
        """
        try:
            # Import here to avoid circular dependencies
            from ..evaluation.batch import BatchEvaluationConfig
            from ..allocation.allocator import AllocationConfig
            from ..rebalance.planner import RebalanceConfig, CurrentPortfolioState
            
            eval_config = BatchEvaluationConfig.from_dict(data["evaluation_config"])
            
            alloc_data = data["allocation_config"]
            alloc_config = AllocationConfig(
                total_capital=alloc_data["total_capital"],
                top_n_strategies=alloc_data.get("top_n_strategies"),
                min_robustness_score=alloc_data.get("min_robustness_score", 0.0),
                max_allocation_per_strategy=alloc_data.get("max_allocation_per_strategy", 1.0),
                min_allocation_per_strategy=alloc_data.get("min_allocation_per_strategy", 0.0),
                allocation_method=alloc_data.get("allocation_method", "robustness_weighted"),
                max_total_leverage=alloc_data.get("max_total_leverage", 1.0),
                require_all_passed=alloc_data.get("require_all_passed", False),
            )
            
            rebalance_data = data["rebalance_config"]
            rebalance_config = RebalanceConfig(
                rebalance_threshold_pct=rebalance_data.get("rebalance_threshold_pct", 0.05),
                max_turnover_pct=rebalance_data.get("max_turnover_pct", 1.0),
                min_trade_size=rebalance_data.get("min_trade_size", 0.0),
                allow_partial_rebalance=rebalance_data.get("allow_partial_rebalance", True),
            )
            
            # Cadence config
            cadence_config = None
            if "cadence_config" in data and data["cadence_config"]:
                from .cadence import CycleCadenceConfig
                cad_data = data["cadence_config"]
                cadence_config = CycleCadenceConfig(
                    frequency=cad_data.get("frequency", "manual"),
                    min_seconds_between_cycles=cad_data.get("min_seconds_between_cycles"),
                    timezone=cad_data.get("timezone", "UTC"),
                )
            
            # Guardrails config
            guardrails_config = None
            if "guardrails_config" in data and data["guardrails_config"]:
                from .guardrails import GuardrailsConfig
                guard_data = data["guardrails_config"]
                guardrails_config = GuardrailsConfig(
                    max_turnover_pct_per_cycle=guard_data.get("max_turnover_pct_per_cycle", 1.0),
                    max_failed_intents=guard_data.get("max_failed_intents"),
                    min_execution_success_rate=guard_data.get("min_execution_success_rate", 0.0),
                    max_single_strategy_allocation_fraction=guard_data.get("max_single_strategy_allocation_fraction", 1.0),
                    halt_on_any_error=guard_data.get("halt_on_any_error", False),
                )
            
            # Ruleset config
            ruleset_type = data.get("ruleset_type")
            ruleset_config = data.get("ruleset_config")
            
            # Day boundary config (for session-based trading days)
            day_boundary_config = data.get("day_boundary_config")
            
            # Validation-only flags (Phase 15)
            validation_hold_quantity = data.get("validation_hold_quantity", False)
            validation_bootstrap_first_cycle = data.get("validation_bootstrap_first_cycle", True)
            
            return cls(
                portfolio_id=data["portfolio_id"],
                evaluation_config=eval_config,
                allocation_config=alloc_config,
                rebalance_config=rebalance_config,
                execution_config=data["execution_config"],
                cadence_config=cadence_config,
                guardrails_config=guardrails_config,
                ruleset_type=ruleset_type,
                ruleset_config=ruleset_config,
                day_boundary_config=day_boundary_config,
                cycle_id=data.get("cycle_id"),
                validation_hold_quantity=validation_hold_quantity,
                validation_bootstrap_first_cycle=validation_bootstrap_first_cycle,
            )
        except KeyError as e:
            raise CycleError(f"Missing required config field: {e}") from e
        except Exception as e:
            raise CycleError(f"Invalid config format: {e}") from e
    
    @classmethod
    def from_json_file(cls, config_path: Path) -> 'PortfolioCycleConfig':
        """Load config from JSON file.
        
        Args:
            config_path: Path to JSON config file
            
        Returns:
            PortfolioCycleConfig instance
            
        Raises:
            CycleError: If file cannot be read or parsed
        """
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except FileNotFoundError:
            raise CycleError(f"Config file not found: {config_path}")
        except json.JSONDecodeError as e:
            raise CycleError(f"Invalid JSON in config file: {e}") from e
        except Exception as e:
            raise CycleError(f"Failed to load config: {e}") from e
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize config to dictionary."""
        return {
            "evaluation_config": self.evaluation_config.to_dict(),
            "allocation_config": {
                "total_capital": self.allocation_config.total_capital,
                "top_n_strategies": self.allocation_config.top_n_strategies,
                "min_robustness_score": self.allocation_config.min_robustness_score,
                "max_allocation_per_strategy": self.allocation_config.max_allocation_per_strategy,
                "min_allocation_per_strategy": self.allocation_config.min_allocation_per_strategy,
                "allocation_method": self.allocation_config.allocation_method,
                "max_total_leverage": self.allocation_config.max_total_leverage,
                "require_all_passed": self.allocation_config.require_all_passed,
            },
            "rebalance_config": {
                "rebalance_threshold_pct": self.rebalance_config.rebalance_threshold_pct,
                "max_turnover_pct": self.rebalance_config.max_turnover_pct,
                "min_trade_size": self.rebalance_config.min_trade_size,
                "allow_partial_rebalance": self.rebalance_config.allow_partial_rebalance,
            },
            "portfolio_id": self.portfolio_id,
            "execution_config": self.execution_config,
            "cadence_config": {
                "frequency": self.cadence_config.frequency,
                "min_seconds_between_cycles": self.cadence_config.min_seconds_between_cycles,
                "timezone": self.cadence_config.timezone,
            } if self.cadence_config else None,
            "guardrails_config": {
                "max_turnover_pct_per_cycle": self.guardrails_config.max_turnover_pct_per_cycle,
                "max_failed_intents": self.guardrails_config.max_failed_intents,
                "min_execution_success_rate": self.guardrails_config.min_execution_success_rate,
                "max_single_strategy_allocation_fraction": self.guardrails_config.max_single_strategy_allocation_fraction,
                "halt_on_any_error": self.guardrails_config.halt_on_any_error,
            } if self.guardrails_config else None,
            "ruleset_type": self.ruleset_type,
            "ruleset_config": self.ruleset_config,
            "cycle_id": self.cycle_id,
        }


@dataclass
class CycleResult:
    """Result of a complete portfolio cycle.
    
    Attributes:
        cycle_id: Unique identifier for this cycle
        cycle_timestamp: When cycle was executed
        portfolio_id: Portfolio identifier
        evaluation_id: ID of evaluation result (None if skipped)
        allocation_id: ID of allocation result (None if skipped)
        rebalance_plan_id: ID of rebalance plan (None if skipped)
        rebalance_execution_id: ID of rebalance execution (None if skipped)
        state_before_id: ID of portfolio state before cycle (None if no previous state)
        state_after_id: ID of portfolio state after cycle (None if skipped/halted)
        summary: Summary metrics across the cycle
        status: Cycle status ("completed", "skipped", "halted")
        skip_reason: Reason if status is "skipped" or "halted"
    """
    
    cycle_id: str
    cycle_timestamp: datetime
    portfolio_id: str
    evaluation_id: Optional[str]
    allocation_id: Optional[str]
    rebalance_plan_id: Optional[str]
    rebalance_execution_id: Optional[str]
    state_before_id: Optional[str]
    state_after_id: Optional[str]
    summary: Dict[str, Any]
    status: str  # "completed", "skipped", "halted"
    skip_reason: Optional[str] = None
    rules_violations: List[Dict[str, Any]] = None  # List of RulesViolation dicts
    ruleset_type: Optional[str] = None
    ruleset_config: Optional[Dict[str, Any]] = None
    survivability_control_events: List[Dict[str, Any]] = None  # List of ControlEvent dicts
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "cycle_id": self.cycle_id,
            "cycle_timestamp": self.cycle_timestamp.isoformat(),
            "portfolio_id": self.portfolio_id,
            "evaluation_id": self.evaluation_id,
            "allocation_id": self.allocation_id,
            "rebalance_plan_id": self.rebalance_plan_id,
            "rebalance_execution_id": self.rebalance_execution_id,
            "state_before_id": self.state_before_id,
            "state_after_id": self.state_after_id,
            "summary": self.summary,
            "status": self.status,
            "skip_reason": self.skip_reason,
            "rules_violations": self.rules_violations or [],
            "ruleset_type": self.ruleset_type,
            "ruleset_config": self.ruleset_config,
        }


def run_portfolio_cycle(
    config: PortfolioCycleConfig,
    research_engine: SimpleResearchEngine,
    artifact_store: ArtifactStore,
    execution_engine_factory: Callable[[], PaperExecutionEngine],
    state_store: Optional[PortfolioStateStore] = None,
    cycle_id: Optional[str] = None,
    execution_mode: ExecutionMode = ExecutionMode.SIMULATION,
    cycle_timestamp: Optional[datetime] = None
) -> CycleResult:
    # Step 0: Debug print - verify flags are being read
    print(f"RUN_CYCLE cycle_id={config.cycle_id or cycle_id} hold={config.validation_hold_quantity} bootstrap={config.validation_bootstrap_first_cycle}")
    """Run a complete portfolio lifecycle cycle.
    
    Orchestrates:
    1. Load current portfolio state (if state_store provided)
    2. Check cadence (skip if too soon)
    3. Batch evaluation of strategies
    4. Capital allocation across top strategies (with guardrails)
    5. Rebalance planning from current state to targets (with guardrails)
    6. Rebalance execution through paper engine (with guardrails)
    7. Update portfolio state (if state_store provided)
    
    Determinism guarantees:
    - Same configs + same data → same cycle result
    - No background state
    - Deterministic execution order
    
    Args:
        config: Portfolio cycle configuration
        research_engine: Research engine for backtesting
        artifact_store: Artifact store for persistence
        execution_engine_factory: Factory function that creates PaperExecutionEngine
                                 (must create isolated sessions)
        state_store: Optional portfolio state store (for stateful operation)
        cycle_id: Optional cycle identifier (auto-generated if not provided)
        execution_mode: Execution mode (SIMULATION, LIVE_DRY, or LIVE)
        cycle_timestamp: Optional explicit cycle timestamp (required in LIVE mode)
        
    Returns:
        CycleResult with references to all sub-artifacts and summary
        
    Raises:
        CycleError: If cycle execution fails
        
    Example:
        >>> def create_engine():
        ...     return PaperExecutionEngine(instrument="AAPL", artifact_store=store)
        >>> state_store = LocalPortfolioStateStore(artifact_store)
        >>> result = run_portfolio_cycle(
        ...     config=cycle_config,
        ...     research_engine=engine,
        ...     artifact_store=store,
        ...     execution_engine_factory=create_engine,
        ...     state_store=state_store
        ... )
        >>> print(f"Cycle {result.cycle_id} status: {result.status}")
    """
    # Top-level validation for LIVE mode (before timestamp fallback)
    _validate_live_mode_timestamps(execution_mode, cycle_timestamp)
    _validate_live_mode_guardrails(execution_mode, config.guardrails_config)
    _validate_portfolio_not_halted(execution_mode, state_store, config.portfolio_id, artifact_store)
    _validate_live_mode_cycle_id(execution_mode, cycle_id, config.cycle_id)
    
    if cycle_timestamp is None:
        cycle_timestamp = datetime.now()
    
    # Generate cycle_id if not provided
    if cycle_id is None:
        cycle_id = config.cycle_id
        if cycle_id is None:
            # Prefer generating from cycle_timestamp if available (deterministic)
            if cycle_timestamp is not None:
                cycle_id = f"cycle_{cycle_timestamp.strftime('%Y%m%d_%H%M%S')}"
            else:
                # Fallback to datetime.now() only when cycle_timestamp is also None
                cycle_id = f"cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    state_before_id = None
    state_after_id = None
    rules_violations: List[RulesViolation] = []
    ruleset: Optional[Ruleset] = None
    
    try:
        # Step 0: Load current state (if state_store provided)
        current_state = None
        if state_store:
            current_state = state_store.load_latest_state(config.portfolio_id)
            # DEBUG: Print loaded state info
            if current_state:
                print(f"  Loaded state: allocations={list(current_state.strategy_allocations.keys()) if current_state.strategy_allocations else []}, len={len(current_state.strategy_allocations)}")
            else:
                print(f"  No state loaded (first cycle)")
            if current_state:
                # Save snapshot of state before cycle with unique ID (preserve drawdown_tracker)
                state_before_id = state_store.save_state(
                    config.portfolio_id,
                    CurrentPortfolioState(
                        strategy_allocations=current_state.strategy_allocations,
                        total_capital=current_state.total_capital,
                        timestamp=current_state.timestamp,  # Preserve original state timestamp
                        drawdown_tracker=current_state.drawdown_tracker,  # Preserve tracker
                        positions_by_instrument=current_state.positions_by_instrument  # Preserve positions
                    ),
                    state_id=f"{cycle_id}_before"  # Use cycle_id prefix for unique ID
                )
                
                # Guardrail: Check for time reversal (timestamp monotonicity)
                # Execution timestamp must be >= last state timestamp
                if cycle_timestamp < current_state.timestamp:
                    # Time reversal detected - HALT cycle
                    violations = [{
                        "code": "TIME_REVERSAL",
                        "message": f"Execution timestamp {cycle_timestamp.isoformat()} is before last state timestamp {current_state.timestamp.isoformat()}",
                        "severity": "halt",
                        "metadata": {
                            "cycle_timestamp": cycle_timestamp.isoformat(),
                            "last_state_timestamp": current_state.timestamp.isoformat(),
                        }
                    }]
                    result = CycleResult(
                        cycle_id=cycle_id,
                        cycle_timestamp=cycle_timestamp,
                        portfolio_id=config.portfolio_id,
                        evaluation_id=None,
                        allocation_id=None,
                        rebalance_plan_id=None,
                        rebalance_execution_id=None,
                        state_before_id=state_before_id,
                        state_after_id=None,
                        summary={},
                    status="halted",
                    skip_reason=f"Time reversal detected: cycle timestamp {cycle_timestamp.isoformat()} < last state timestamp {current_state.timestamp.isoformat()}",
                    rules_violations=violations,
                    ruleset_type=config.ruleset_type,
                    ruleset_config=config.ruleset_config,
                    survivability_control_events=[],
                    )
                    if _is_live_mode(execution_mode):
                        # Write halt flag before raising exception
                        halt_store = HaltFlagStore(artifact_store)
                        halt_store.write_halt_flag(
                            portfolio_id=config.portfolio_id,
                            cycle_id=cycle_id,
                            reason=result.skip_reason,
                            halted_at=cycle_timestamp,
                            violations_summary=violations
                        )
                        raise CycleHaltError(
                            f"Cycle halted in LIVE mode: {result.skip_reason}. "
                            "Manual intervention required before continuing.",
                            result=result
                        )
                    return result
        
        # Step 0.5: Check cadence (if configured)
        # Normalize cadence_config to CycleCadenceConfig object if it's a dict
        cadence_config_obj = config.cadence_config
        if cadence_config_obj and isinstance(cadence_config_obj, dict):
            cadence_config_obj = CycleCadenceConfig(
                frequency=cadence_config_obj.get("frequency", "manual"),
                min_seconds_between_cycles=cadence_config_obj.get("min_seconds_between_cycles"),
                timezone=cadence_config_obj.get("timezone", "UTC")
            )
        
        if cadence_config_obj:
            # Load last cycle timestamp (from last cycle result if available)
            # For simplicity, check if we have a recent state timestamp
            last_cycle_timestamp = None
            if current_state:
                last_cycle_timestamp = current_state.timestamp
            
            should_run, skip_reason = check_cadence(
                cadence_config_obj,
                last_cycle_timestamp,
                cycle_timestamp
            )
            
            if not should_run:
                # Skip cycle
                return CycleResult(
                    cycle_id=cycle_id,
                    cycle_timestamp=cycle_timestamp,
                    portfolio_id=config.portfolio_id,
                    evaluation_id=None,
                    allocation_id=None,
                    rebalance_plan_id=None,
                    rebalance_execution_id=None,
                    state_before_id=state_before_id,
                    state_after_id=None,
                    summary={},
                    status="skipped",
                    skip_reason=skip_reason,
                    rules_violations=[],
                    ruleset_type=config.ruleset_type,
                    ruleset_config=config.ruleset_config,
                    survivability_control_events=[],
                )
        
        # Initialize current state if not loaded
        if current_state is None:
            current_state = CurrentPortfolioState(
                strategy_allocations={},
                total_capital=config.allocation_config.total_capital,
                timestamp=cycle_timestamp,
                positions_by_instrument=None
            )
            if state_store:
                state_before_id = state_store.save_state(config.portfolio_id, current_state)
        
        # Check if we should bootstrap first cycle or use hold-quantity validation mode
        should_use_hold_quantity_mode = config.validation_hold_quantity
        is_first_cycle = current_state is None or len(current_state.strategy_allocations) == 0
        use_normal_cycle = not should_use_hold_quantity_mode or (config.validation_bootstrap_first_cycle and is_first_cycle)
        
        # DEBUG: Print cycle decision logic
        print(f"  should_use_hold_quantity_mode={should_use_hold_quantity_mode}")
        print(f"  is_first_cycle={is_first_cycle} (current_state={current_state is not None}, allocations_len={len(current_state.strategy_allocations) if current_state else 0})")
        print(f"  validation_bootstrap_first_cycle={config.validation_bootstrap_first_cycle}")
        print(f"  use_normal_cycle={use_normal_cycle}")
        
        # Step 1: Batch evaluation (skip if hold-quantity mode)
        evaluation = None
        evaluation_id = None
        if use_normal_cycle:
            evaluation = run_batch_evaluation(
                config=config.evaluation_config,
                research_engine=research_engine,
                artifact_store=artifact_store,
                execution_engine_factory=execution_engine_factory
            )
            evaluation_id = evaluation.evaluation_id
        
        # Step 2: Capital allocation (skip if hold-quantity mode)
        allocation_result = None
        allocation_id = None
        if use_normal_cycle:
            # Generate allocation_id from cycle_id if available
            allocation_id_param = f"{cycle_id}_alloc" if cycle_id else None
            # TIMESTAMP CHAIN: allocation_timestamp MUST be derived from cycle_timestamp
            # In LIVE mode, all timestamps (allocation, plan, execution) must come from
            # a single source of truth (cycle_timestamp) to avoid clock skew.
            # Do not independently supply timestamps from different clocks.
            allocation_result = allocate_capital(
                evaluation=evaluation,
                config=config.allocation_config,
                allocation_id=allocation_id_param,
                allocation_timestamp=cycle_timestamp,  # Derived from cycle_timestamp
                execution_mode=execution_mode
            )
        
        # Check allocation guardrails (skip if hold-quantity mode)
        if use_normal_cycle and config.guardrails_config:
            alloc_list = [{"allocation_fraction": a.allocation_fraction} for a in allocation_result.allocations]
            passes, violation = check_allocation_guardrails(
                config.guardrails_config,
                alloc_list,
                allocation_result.total_capital
            )
            if not passes:
                # Halt cycle
                from ..allocation.allocator import persist_allocation
                allocation_id = persist_allocation(allocation_result, artifact_store)
                result = CycleResult(
                    cycle_id=cycle_id,
                    cycle_timestamp=cycle_timestamp,
                    portfolio_id=config.portfolio_id,
                    evaluation_id=evaluation_id,
                    allocation_id=allocation_id,
                    rebalance_plan_id=None,
                    rebalance_execution_id=None,
                    state_before_id=state_before_id,
                    state_after_id=None,
                    summary={
                        "evaluation_summary": evaluation.summary,
                        "allocation_summary": {
                            "total_capital": allocation_result.total_capital,
                            "allocated_capital": allocation_result.allocated_capital,
                            "num_strategies": len(allocation_result.allocations),
                        },
                    },
                    status="halted",
                    skip_reason=f"Allocation guardrail violation: {violation}",
                    rules_violations=[],
                    ruleset_type=config.ruleset_type,
                    ruleset_config=config.ruleset_config,
                    survivability_control_events=[],
                )
                if _is_live_mode(execution_mode):
                    # Write halt flag before raising exception
                    halt_store = HaltFlagStore(artifact_store)
                    halt_store.write_halt_flag(
                        portfolio_id=config.portfolio_id,
                        cycle_id=cycle_id,
                        reason=result.skip_reason,
                        halted_at=cycle_timestamp,
                        violations_summary=result.rules_violations
                    )
                    raise CycleHaltError(
                        f"Cycle halted in LIVE mode: {result.skip_reason}. "
                        "Manual intervention required before continuing.",
                        result=result
                    )
                return result
        
        if use_normal_cycle:
            from ..allocation.allocator import persist_allocation
            allocation_id = persist_allocation(allocation_result, artifact_store)
            
            # Step 2.5: Apply survivability controls (clamp allocations to position size limits)
            survivability_control_events: List[Dict[str, Any]] = []
            if config.ruleset_type == "topstep" and config.ruleset_config:
                from ..control import SurvivabilityControlConfig, apply_survivability_controls
                
                # Extract max_position_size from ruleset config
                max_position_size = config.ruleset_config.get("max_position_size")
                if max_position_size is not None:
                    # Get prices from execution config
                    price_by_strategy_or_instrument = config.execution_config.get(
                        "price_by_strategy_or_instrument", {}
                    )
                    
                    # Get instrument (assumes single instrument per portfolio)
                    # Extract from execution engine factory by creating a temporary engine
                    instrument = None
                    try:
                        temp_engine = execution_engine_factory()
                        if hasattr(temp_engine, 'instrument'):
                            instrument = temp_engine.instrument
                    except Exception:
                        # If engine creation fails, try to infer from price dict
                        # Try common instrument keys first
                        for key in ["AAPL", "SPY", "ES"]:  # Common instrument identifiers
                            if key in price_by_strategy_or_instrument:
                                instrument = key
                                break
                    
                    # Create control config
                    control_config = SurvivabilityControlConfig(
                        position_cap_policy="cap_quantity",
                        max_position_size_default=max_position_size,
                        allow_cash_residual=True,
                        redistribute_residual=False  # Default: leave residual as cash
                    )
                    
                    # Apply controls
                    allocation_result, control_events = apply_survivability_controls(
                        allocation_result=allocation_result,
                        price_by_strategy_or_instrument=price_by_strategy_or_instrument,
                        config=control_config,
                        instrument=instrument
                    )
                    
                    # Convert events to dicts
                    survivability_control_events = [e.to_dict() for e in control_events]
                    
                    # Repersist adjusted allocation
                    allocation_id = persist_allocation(allocation_result, artifact_store)
        
        # Step 3: Rebalance planning (skip if hold-quantity mode)
        rebalance_plan = None
        rebalance_plan_id = None
        if use_normal_cycle:
            # Generate plan_id from cycle_id if available
            plan_id_param = f"{cycle_id}_plan" if cycle_id else None
            # TIMESTAMP CHAIN: plan_timestamp MUST be derived from cycle_timestamp
            # In LIVE mode, all timestamps must come from a single source to avoid clock skew.
            rebalance_plan = plan_rebalance(
                allocation_result=allocation_result,
                current_state=current_state,
                config=config.rebalance_config,
                plan_id=plan_id_param,
                plan_timestamp=cycle_timestamp,  # Derived from cycle_timestamp
                execution_mode=execution_mode
            )
        
        # Check rebalance guardrails
        if config.guardrails_config:
            passes, violation = check_rebalance_guardrails(
                config.guardrails_config,
                rebalance_plan.metrics.get("total_turnover", 0.0),
                current_state.total_capital
            )
            if not passes:
                # Halt cycle
                from ..rebalance.planner import persist_rebalance_plan
                rebalance_plan_id = persist_rebalance_plan(rebalance_plan, artifact_store)
                result = CycleResult(
                    cycle_id=cycle_id,
                    cycle_timestamp=cycle_timestamp,
                    portfolio_id=config.portfolio_id,
                    evaluation_id=evaluation_id,
                    allocation_id=allocation_id,
                    rebalance_plan_id=rebalance_plan_id,
                    rebalance_execution_id=None,
                    state_before_id=state_before_id,
                    state_after_id=None,
                    summary={
                        "evaluation_summary": evaluation.summary,
                        "allocation_summary": {
                            "total_capital": allocation_result.total_capital,
                            "allocated_capital": allocation_result.allocated_capital,
                            "num_strategies": len(allocation_result.allocations),
                        },
                        "rebalance_summary": rebalance_plan.metrics,
                    },
                    status="halted",
                    skip_reason=f"Rebalance guardrail violation: {violation}",
                    rules_violations=[],
                    ruleset_type=config.ruleset_type,
                    ruleset_config=config.ruleset_config,
                    survivability_control_events=[],
                )
                if _is_live_mode(execution_mode):
                    # Write halt flag before raising exception
                    halt_store = HaltFlagStore(artifact_store)
                    halt_store.write_halt_flag(
                        portfolio_id=config.portfolio_id,
                        cycle_id=cycle_id,
                        reason=result.skip_reason,
                        halted_at=cycle_timestamp,
                        violations_summary=result.rules_violations
                    )
                    raise CycleHaltError(
                        f"Cycle halted in LIVE mode: {result.skip_reason}. "
                        "Manual intervention required before continuing.",
                        result=result
                    )
                return result
        
        if use_normal_cycle:
            from ..rebalance.planner import persist_rebalance_plan
            rebalance_plan_id = persist_rebalance_plan(rebalance_plan, artifact_store)
        
        # Step 3.5: Validate rebalance plan against ruleset (skip if hold-quantity mode)
        if use_normal_cycle and config.ruleset_type == "topstep" and config.ruleset_config:
            from ..rules import TopstepRulesConfig, TopstepRuleset
            ruleset_config = TopstepRulesConfig(**config.ruleset_config)
            ruleset = TopstepRuleset(ruleset_config)
            plan_violations = ruleset.validate_plan(rebalance_plan, current_state)
            rules_violations.extend(plan_violations)
            
            # Check for HALT violations
            halt_violations = [v for v in plan_violations if v.severity == RulesViolationSeverity.HALT]
            if halt_violations:
                result = CycleResult(
                    cycle_id=cycle_id,
                    cycle_timestamp=cycle_timestamp,
                    portfolio_id=config.portfolio_id,
                    evaluation_id=evaluation_id,
                    allocation_id=allocation_id,
                    rebalance_plan_id=rebalance_plan_id,
                    rebalance_execution_id=None,
                    state_before_id=state_before_id,
                    state_after_id=None,
                    summary={
                        "evaluation_summary": evaluation.summary,
                        "allocation_summary": {
                            "total_capital": allocation_result.total_capital,
                            "allocated_capital": allocation_result.allocated_capital,
                            "num_strategies": len(allocation_result.allocations),
                        },
                        "rebalance_summary": rebalance_plan.metrics,
                    },
                    status="halted",
                    skip_reason=f"Ruleset violation: {halt_violations[0].message}",
                    rules_violations=[v.to_dict() for v in rules_violations],
                    ruleset_type=config.ruleset_type,
                    ruleset_config=config.ruleset_config,
                    survivability_control_events=[],
                )
                if _is_live_mode(execution_mode):
                    # Write halt flag before raising exception
                    halt_store = HaltFlagStore(artifact_store)
                    halt_store.write_halt_flag(
                        portfolio_id=config.portfolio_id,
                        cycle_id=cycle_id,
                        reason=result.skip_reason,
                        halted_at=cycle_timestamp,
                        violations_summary=result.rules_violations
                    )
                    raise CycleHaltError(
                        f"Cycle halted in LIVE mode: {result.skip_reason}. "
                        "Manual intervention required before continuing.",
                        result=result
                    )
                return result
        
        # Step 4: Rebalance execution (skip if hold-quantity mode)
        execution_engine = None
        execution_result = None
        rebalance_execution_id = None
        
        if use_normal_cycle:
            # In LIVE/LIVE_DRY mode, engine must use FixedClock and DeterministicIDProvider
            # seeded from cycle_timestamp/cycle_id to ensure deterministic timestamps and IDs.
            # In SIMULATION mode, use SimulationClock and SimulationIDProvider (defaults).
            from ..execution.clock import FixedClock
            from ..execution.id_provider import DeterministicIDProvider
            base_engine = execution_engine_factory()
            if _is_live_mode(execution_mode):
                # Replace clock with FixedClock for deterministic timestamps
                base_engine.clock = FixedClock(cycle_timestamp)
                # Replace ID provider with DeterministicIDProvider for deterministic IDs
                # Use cycle_id as seed if available, else cycle_timestamp.isoformat()
                id_seed = cycle_id if cycle_id else cycle_timestamp.isoformat()
                base_engine.id_provider = DeterministicIDProvider(seed=id_seed)
            execution_engine = base_engine
            
            price_by_strategy_or_instrument = config.execution_config.get(
                "price_by_strategy_or_instrument", {}
            )
            
            mapper = RebalanceSignalMapper(
                rounding_method=config.execution_config.get("rounding_method", "floor"),
                min_quantity=config.execution_config.get("min_quantity", 0.0)
            )
            
            # Generate execution_id from cycle_id if available
            execution_id_param = f"{cycle_id}_exec" if cycle_id else None
            # TIMESTAMP CHAIN: execution_timestamp MUST be derived from cycle_timestamp
            # In LIVE mode, all timestamps (allocation, plan, execution) must come from
            # a single source of truth (cycle_timestamp) to avoid clock skew.
            # The execution engine's internal order/fill timestamps will also use this
            # timestamp via the ExecutionClock abstraction.
            execution_result = execute_rebalance_plan(
                plan=rebalance_plan,
                execution_engine=execution_engine,
                price_by_strategy_or_instrument=price_by_strategy_or_instrument,
                mapper=mapper,
                execution_id=execution_id_param,
                execution_timestamp=cycle_timestamp,  # Derived from cycle_timestamp
                execution_mode=execution_mode
            )
        
        # Check execution guardrails (skip if hold-quantity mode)
        if use_normal_cycle and config.guardrails_config:
            passes, violation = check_execution_guardrails(
                config.guardrails_config,
                execution_result.execution_summary["successful_intents"],
                execution_result.execution_summary["failed_intents"],
                execution_result.execution_summary["total_intents"]
            )
            if not passes:
                # Halt cycle (but execution already happened)
                from ..rebalance.executor import persist_rebalance_execution
                rebalance_execution_id = persist_rebalance_execution(execution_result, artifact_store)
                result = CycleResult(
                    cycle_id=cycle_id,
                    cycle_timestamp=cycle_timestamp,
                    portfolio_id=config.portfolio_id,
                    evaluation_id=evaluation_id,
                    allocation_id=allocation_id,
                    rebalance_plan_id=rebalance_plan_id,
                    rebalance_execution_id=rebalance_execution_id,
                    state_before_id=state_before_id,
                    state_after_id=None,  # Don't update state if halted
                    summary={
                        "evaluation_summary": evaluation.summary,
                        "allocation_summary": {
                            "total_capital": allocation_result.total_capital,
                            "allocated_capital": allocation_result.allocated_capital,
                            "num_strategies": len(allocation_result.allocations),
                        },
                        "rebalance_summary": rebalance_plan.metrics,
                        "execution_summary": execution_result.execution_summary,
                    },
                    status="halted",
                    skip_reason=f"Execution guardrail violation: {violation}",
                    rules_violations=[],
                    ruleset_type=config.ruleset_type,
                    ruleset_config=config.ruleset_config,
                    survivability_control_events=[],
                )
                if _is_live_mode(execution_mode):
                    # Write halt flag before raising exception
                    halt_store = HaltFlagStore(artifact_store)
                    halt_store.write_halt_flag(
                        portfolio_id=config.portfolio_id,
                        cycle_id=cycle_id,
                        reason=result.skip_reason,
                        halted_at=cycle_timestamp,
                        violations_summary=result.rules_violations
                    )
                    raise CycleHaltError(
                        f"Cycle halted in LIVE mode: {result.skip_reason}. "
                        "Manual intervention required before continuing.",
                        result=result
                    )
                return result
        
        if use_normal_cycle:
            from ..rebalance.executor import persist_rebalance_execution
            rebalance_execution_id = persist_rebalance_execution(execution_result, artifact_store)
        
        # Step 4.5: Validate execution against ruleset (or mark-to-market validation for hold-quantity mode)
        # Initialize ruleset if configured
        if config.ruleset_type == "topstep" and config.ruleset_config:
            from ..rules import TopstepRulesConfig, TopstepRuleset
            if ruleset is None:
                ruleset_config = TopstepRulesConfig(**config.ruleset_config)
                ruleset = TopstepRuleset(ruleset_config)
        
        # Initialize computed_equity in outer scope (used in hold-quantity mode)
        computed_equity = None
        
        # DEBUG: Print which path we're taking
        print(f"  use_normal_cycle={use_normal_cycle}, ruleset={ruleset is not None}")
        
        if ruleset:
            # Get current prices from execution config for equity calculation
            price_by_strategy_or_instrument = config.execution_config.get(
                "price_by_strategy_or_instrument", {}
            )
            # Convert to instrument -> price mapping (assumes single instrument per engine)
            current_prices = {}
            if use_normal_cycle and execution_engine and hasattr(execution_engine, 'instrument'):
                instrument = execution_engine.instrument
                # Try instrument key first, then try strategy keys
                price = price_by_strategy_or_instrument.get(instrument)
                if price is None:
                    # Try first strategy ID as fallback
                    for key, val in price_by_strategy_or_instrument.items():
                        price = val
                        break
                if price is not None:
                    current_prices[instrument] = price
            elif not use_normal_cycle:
                # Hold-quantity mode: extract prices from config
                # Assumes single instrument (same as normal mode)
                # Try to find instrument key first (e.g., "AAPL"), then fallback to strategy keys
                if current_state.positions_by_instrument:
                    # Extract instrument from positions
                    instrument = list(current_state.positions_by_instrument.keys())[0]
                    price = price_by_strategy_or_instrument.get(instrument)
                    if price is not None:
                        current_prices[instrument] = price
                    else:
                        # Fallback to first value in price dict
                        for key, val in price_by_strategy_or_instrument.items():
                            current_prices[key] = val
                            break
                else:
                    # No positions, take first price from config
                    for key, val in price_by_strategy_or_instrument.items():
                        current_prices[key] = val
                        break
            
            # Initialize exec_violations for halt check
            exec_violations = []
            
            if use_normal_cycle:
                # Normal mode: validate execution result
                # Create day boundary for validation (use config if available)
                from ..rules.day_boundary import TradingDayBoundary
                day_boundary = TradingDayBoundary.from_config(config.day_boundary_config)
                
                # validate_execution expects day_boundary parameter for Topstep ruleset
                import inspect
                sig = inspect.signature(ruleset.validate_execution)
                if 'day_boundary' in sig.parameters:
                    exec_violations = ruleset.validate_execution(
                        execution_result, current_state, execution_engine=execution_engine, 
                        current_prices=current_prices, day_boundary=day_boundary
                    )
                else:
                    exec_violations = ruleset.validate_execution(
                        execution_result, current_state, execution_engine=execution_engine, 
                        current_prices=current_prices
                    )
                rules_violations.extend(exec_violations)
            else:
                # Hold-quantity mode: mark-to-market validation using positions from state
                # Contract: This is the ONLY place equity is computed and tracker is updated
                # validate_execution(skip_equity_recalculation=True) will NOT recompute or update again
                
                # Initialize survivability_control_events for this branch
                survivability_control_events = []
                
                # Step 1: Reconstruct positions from current_state.positions_by_instrument
                from ..execution.position import Position
                from ..rules.drawdown import calculate_portfolio_equity
                positions = {}
                if current_state.positions_by_instrument:
                    for instrument, pos_dict in current_state.positions_by_instrument.items():
                        positions[instrument] = Position.from_dict(pos_dict)
                
                # DEBUG: Prove positions and prices exist
                print(f"  positions_by_instrument count: {len(current_state.positions_by_instrument or {})}")
                print(f"  positions_by_instrument keys: {list((current_state.positions_by_instrument or {}).keys())}")
                print(f"  current_prices size: {len(current_prices)}")
                print(f"  current_prices keys: {list(current_prices.keys())}")
                if "AAPL" in current_prices:
                    print(f"  AAPL price: ${current_prices['AAPL']:.2f}")
                else:
                    print(f"  WARNING: AAPL not in current_prices")
                
                # Assert invariants - stop if data is missing
                assert current_state.positions_by_instrument, "No positions present in state, cannot mark-to-market"
                assert current_prices, "current_prices empty, cannot mark-to-market"
                assert "AAPL" in current_prices, "Missing AAPL price"
                
                # Step 2: Build current_prices from execution_config
                if not current_prices:
                    price_by_strategy_or_instrument = config.execution_config.get(
                        "price_by_strategy_or_instrument", {}
                    )
                    if current_state.positions_by_instrument:
                        instrument = list(current_state.positions_by_instrument.keys())[0]
                        price = price_by_strategy_or_instrument.get(instrument)
                        if price is None:
                            # Fallback to first value
                            price = list(price_by_strategy_or_instrument.values())[0] if price_by_strategy_or_instrument else None
                        if price is not None:
                            current_prices[instrument] = price
                
                # Step 3: Compute mark-to-market equity
                initial_cash = current_state.total_capital
                total_realized_pnl = sum(pos.realized_pnl for pos in positions.values())
                
                if current_prices:
                    equity, unrealized_pnl = calculate_portfolio_equity(
                        initial_cash=initial_cash,
                        positions=positions,
                        current_prices=current_prices,
                        realized_pnl=total_realized_pnl
                    )
                else:
                    # No prices available, use realized PnL only (conservative)
                    equity = initial_cash + total_realized_pnl
                    unrealized_pnl = 0.0
                
                # Step 4: Update drawdown tracker with computed equity (ONLY update point in hold-quantity mode)
                # validate_execution(skip_equity_recalculation=True) will NOT recompute or update again
                computed_equity = equity  # Store for persistence and proof prints (set in outer scope)
                if current_state.drawdown_tracker is not None:
                    from ..rules.day_boundary import TradingDayBoundary
                    day_boundary = TradingDayBoundary.from_config(config.day_boundary_config)
                    
                    # Update tracker with mark-to-market equity
                    snapshot = current_state.drawdown_tracker.update(
                        equity=equity,
                        realized_pnl=total_realized_pnl,
                        unrealized_pnl=unrealized_pnl,
                        timestamp=cycle_timestamp,
                        day_boundary=day_boundary
                    )
                    # Tracker is updated in-place; current_state.drawdown_tracker now has the updated state
                
                # Phase 15 validation-only proof prints
                if positions:
                    inst = list(positions.keys())[0]
                    pos = positions[inst]
                    current_price_val = current_prices.get(inst, 0.0) if current_prices else 0.0
                    tracker_locked = current_state.drawdown_tracker.is_locked if current_state.drawdown_tracker else False
                    tracker_hwm = current_state.drawdown_tracker.high_water_mark if current_state.drawdown_tracker else 0.0
                    print(f"  [Hold-Qty Validation] price=${current_price_val:.2f}, qty={pos.quantity:.1f}, "
                          f"equity=${computed_equity:,.2f}, locked={tracker_locked}, hwm=${tracker_hwm:,.2f}")
                
                # Apply survivability controls to positions (Phase 16: enforce position size caps)
                if config.ruleset_type == "topstep" and config.ruleset_config:
                    from ..control import ControlEvent, ControlEventSeverity
                    
                    max_position_size = config.ruleset_config.get("max_position_size")
                    if max_position_size is not None:
                        # Get current prices
                        price_by_strategy_or_instrument = config.execution_config.get(
                            "price_by_strategy_or_instrument", {}
                        )
                        
                        # Apply position size caps to each position
                        position_control_events = []
                        for inst, position in positions.items():
                            # Get price for this instrument
                            price = price_by_strategy_or_instrument.get(inst)
                            if price is None or price <= 0:
                                continue
                            
                            # Check if quantity exceeds max_position_size
                            if abs(position.quantity) > max_position_size:
                                # Clamp quantity to max_position_size (preserve direction)
                                original_quantity = position.quantity
                                capped_quantity = max_position_size if original_quantity > 0 else -max_position_size
                                
                                # Create new Position with capped quantity (Position is immutable)
                                positions[inst] = Position(
                                    instrument=position.instrument,
                                    quantity=capped_quantity,
                                    cost_basis=position.cost_basis,
                                    realized_pnl=position.realized_pnl,
                                    updated_at=position.updated_at
                                )
                                
                                # Record control event
                                utilization = abs(original_quantity) / max_position_size
                                event = ControlEvent(
                                    code="POSITION_SIZE_CAP_BINDING",
                                    message=f"Position {inst} quantity clamped: "
                                           f"{original_quantity} -> {capped_quantity} "
                                           f"(utilization: {utilization:.2%})",
                                    severity=ControlEventSeverity.WARN,
                                    metadata={
                                        "instrument": inst,
                                        "original_quantity": original_quantity,
                                        "capped_quantity": capped_quantity,
                                        "price": price,
                                        "max_position_size": max_position_size,
                                        "utilization": utilization,
                                    }
                                )
                                position_control_events.append(event.to_dict())
                        
                        # Add position control events to survivability_control_events
                        if position_control_events:
                            if 'survivability_control_events' not in locals():
                                survivability_control_events = []
                            survivability_control_events.extend(position_control_events)
                
                # Create a minimal execution engine with these positions for validation
                # We only need it for validate_execution, so create it with positions pre-loaded
                # Use FixedClock and DeterministicIDProvider in LIVE/LIVE_DRY mode for determinism
                from ..execution.clock import FixedClock
                from ..execution.id_provider import DeterministicIDProvider
                base_engine = execution_engine_factory()
                if _is_live_mode(execution_mode):
                    base_engine.clock = FixedClock(cycle_timestamp)
                    id_seed = cycle_id if cycle_id else cycle_timestamp.isoformat()
                    base_engine.id_provider = DeterministicIDProvider(seed=id_seed)
                execution_engine = base_engine
                if hasattr(execution_engine, 'positions'):
                    execution_engine.positions = positions
                
                # Create a dummy execution result for validation (no actual execution occurred)
                # validate_execution needs execution_result.execution_timestamp
                from ..rebalance.executor import RebalanceExecutionResult
                dummy_execution_result = RebalanceExecutionResult(
                    execution_id=f"hold_qty_{cycle_id}",
                    execution_timestamp=cycle_timestamp,
                    plan_id="hold_qty_no_plan",
                    intent_results=[],
                    execution_summary={"successful_intents": 0, "failed_intents": 0, "total_intents": 0},
                    mapping={}
                )
                
                # Create day boundary for validation (use config if available)
                from ..rules.day_boundary import TradingDayBoundary
                day_boundary = TradingDayBoundary.from_config(config.day_boundary_config)
                
                # validate_execution expects day_boundary parameter for Topstep ruleset
                # Phase 15: In hold-quantity mode, skip equity recalculation to preserve precomputed equity
                import inspect
                sig = inspect.signature(ruleset.validate_execution)
                if 'skip_equity_recalculation' in sig.parameters:
                    exec_violations = ruleset.validate_execution(
                        dummy_execution_result, current_state, execution_engine=execution_engine, 
                        current_prices=current_prices, day_boundary=day_boundary,
                        skip_equity_recalculation=True  # Phase 15: use precomputed equity from tracker
                    )
                elif 'day_boundary' in sig.parameters:
                    exec_violations = ruleset.validate_execution(
                        dummy_execution_result, current_state, execution_engine=execution_engine, 
                        current_prices=current_prices, day_boundary=day_boundary
                    )
                else:
                    exec_violations = ruleset.validate_execution(
                        dummy_execution_result, current_state, execution_engine=execution_engine, 
                        current_prices=current_prices
                    )
                rules_violations.extend(exec_violations)
            
            # Check for HALT violations
            halt_violations = [v for v in exec_violations if v.severity == RulesViolationSeverity.HALT]
            if halt_violations:
                result = CycleResult(
                    cycle_id=cycle_id,
                    cycle_timestamp=cycle_timestamp,
                    portfolio_id=config.portfolio_id,
                    evaluation_id=evaluation_id,
                    allocation_id=allocation_id,
                    rebalance_plan_id=rebalance_plan_id,
                    rebalance_execution_id=rebalance_execution_id,
                    state_before_id=state_before_id,
                    state_after_id=None,  # Don't update state if halted
                    summary={
                        "evaluation_summary": evaluation.summary,
                        "allocation_summary": {
                            "total_capital": allocation_result.total_capital,
                            "allocated_capital": allocation_result.allocated_capital,
                            "num_strategies": len(allocation_result.allocations),
                        },
                        "rebalance_summary": rebalance_plan.metrics,
                        "execution_summary": execution_result.execution_summary if execution_result else {},
                    },
                    status="halted",
                    skip_reason=f"Ruleset violation: {halt_violations[0].message}",
                    rules_violations=[v.to_dict() for v in rules_violations],
                    ruleset_type=config.ruleset_type,
                    ruleset_config=config.ruleset_config,
                    survivability_control_events=[],
                )
                if _is_live_mode(execution_mode):
                    # Write halt flag before raising exception
                    halt_store = HaltFlagStore(artifact_store)
                    halt_store.write_halt_flag(
                        portfolio_id=config.portfolio_id,
                        cycle_id=cycle_id,
                        reason=result.skip_reason,
                        halted_at=cycle_timestamp,
                        violations_summary=result.rules_violations
                    )
                    raise CycleHaltError(
                        f"Cycle halted in LIVE mode: {result.skip_reason}. "
                        "Manual intervention required before continuing.",
                        result=result
                    )
                return result
        
        # Step 5: Update portfolio state
        # Note: computed_equity is set in hold-quantity mode block above, and used here for state persistence
        if state_store:
            if use_normal_cycle:
                # Normal mode: Compute new state from target allocations (since execution succeeded)
                # Use the allocation_result as the source of truth for target allocations
                new_allocations = {}
                for alloc in allocation_result.allocations:
                    strategy_id = alloc.strategy_id
                    new_allocations[strategy_id] = alloc.allocated_capital
                
                # Get updated drawdown tracker from current_state
                # The tracker was updated during validate_execution if Topstep ruleset was used
                drawdown_tracker = None
                if ruleset and hasattr(current_state, 'drawdown_tracker'):
                    drawdown_tracker = current_state.drawdown_tracker
                
                # Extract positions from execution engine for persistence
                positions_by_instrument = None
                if execution_engine and hasattr(execution_engine, 'positions'):
                    positions_by_instrument = {
                        instrument: pos.to_dict() 
                        for instrument, pos in execution_engine.positions.items()
                    }
                
                # Create new state with target allocations, drawdown tracker, and positions
                new_state = CurrentPortfolioState(
                    strategy_allocations=new_allocations,
                    total_capital=allocation_result.total_capital,
                    timestamp=cycle_timestamp,
                    drawdown_tracker=drawdown_tracker,
                    positions_by_instrument=positions_by_instrument
                )
            else:
                # Hold-quantity mode: Preserve positions, update drawdown tracker, persist computed equity
                # Get updated drawdown tracker from current_state (already updated with computed equity)
                drawdown_tracker = None
                if ruleset and hasattr(current_state, 'drawdown_tracker'):
                    drawdown_tracker = current_state.drawdown_tracker
                
                # Use computed equity as total_capital (so equity moves in persisted state)
                # computed_equity was set in the hold-quantity validation block above
                # Fallback to current_state.total_capital if somehow not set (should not happen)
                try:
                    computed_equity_for_state = computed_equity if computed_equity is not None else current_state.total_capital
                except NameError:
                    # Should not happen - computed_equity should always be set in hold-quantity mode
                    computed_equity_for_state = current_state.total_capital
                
                # Create new state with unchanged allocations and positions, updated tracker, computed equity as total_capital
                new_state = CurrentPortfolioState(
                    strategy_allocations=current_state.strategy_allocations,
                    total_capital=computed_equity_for_state,  # Phase 15: persist computed equity
                    timestamp=cycle_timestamp,
                    drawdown_tracker=drawdown_tracker,
                    positions_by_instrument=current_state.positions_by_instrument  # Preserve positions
                )
            
            state_after_id = state_store.save_state(
                config.portfolio_id,
                new_state,
                state_id=f"{cycle_id}_after"  # Use cycle_id prefix for unique ID
            )
        
        # Step 6: Compute cycle summary
        if use_normal_cycle:
            summary = {
                "evaluation_summary": evaluation.summary if evaluation else {},
                "allocation_summary": {
                    "total_capital": allocation_result.total_capital,
                    "allocated_capital": allocation_result.allocated_capital,
                    "num_strategies": len(allocation_result.allocations),
                    "top_strategy_id": allocation_result.allocations[0].strategy_id if allocation_result.allocations else None,
                },
                "rebalance_summary": rebalance_plan.metrics if rebalance_plan else {},
                "execution_summary": execution_result.execution_summary if execution_result else {},
            }
        else:
            # Hold-quantity mode: minimal summary
            summary = {
                "mode": "hold_quantity",
                "validation_summary": {
                    "positions_count": len(current_state.positions_by_instrument) if current_state.positions_by_instrument else 0,
                }
            }
        
        
        return CycleResult(
            cycle_id=cycle_id,
            cycle_timestamp=cycle_timestamp,
            portfolio_id=config.portfolio_id,
            evaluation_id=evaluation_id,
            allocation_id=allocation_id,
            rebalance_plan_id=rebalance_plan_id,
            rebalance_execution_id=rebalance_execution_id,
            state_before_id=state_before_id,
            state_after_id=state_after_id,
            summary=summary,
            status="completed",
            skip_reason=None,
            rules_violations=[v.to_dict() for v in rules_violations],
            ruleset_type=config.ruleset_type,
            ruleset_config=config.ruleset_config,
            survivability_control_events=survivability_control_events,
        )
        
    except Exception as e:
        raise CycleError(f"Failed to run portfolio cycle: {e}") from e


def persist_cycle_result(
    result: CycleResult,
    artifact_store: ArtifactStore
) -> str:
    """Persist cycle result to artifact store.
    
    Args:
        result: CycleResult to persist
        artifact_store: ArtifactStore instance
        
    Returns:
        Cycle identifier
        
    Raises:
        CycleError: If persistence fails
    """
    try:
        result_json = json.dumps(result.to_dict(), indent=2).encode('utf-8')
        artifact_store.store(result.cycle_id, "cycle_result.json", result_json)
        return result.cycle_id
    except Exception as e:
        raise CycleError(f"Failed to persist cycle result: {e}") from e


def main():
    """CLI entrypoint for portfolio cycle execution.
    
    Usage:
        python -m src.lifecycle.runner --config <config_path>
    """
    parser = argparse.ArgumentParser(
        description="Run portfolio lifecycle cycle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example cycle_config.json:
{
  "evaluation_config": {
    "strategies": [...],
    "parameter_grid": {...},
    "evaluation_criteria": {...},
    "price_series": [...]
  },
  "allocation_config": {
    "total_capital": 1000000,
    "top_n_strategies": 5,
    "allocation_method": "robustness_weighted"
  },
  "rebalance_config": {
    "rebalance_threshold_pct": 0.05,
    "max_turnover_pct": 0.5
  },
  "execution_config": {
    "price_by_strategy_or_instrument": {
      "strat_1": 150.0,
      "AAPL": 150.0
    },
    "rounding_method": "floor",
    "min_quantity": 1.0
  },
  "current_state": {
    "strategy_allocations": {},
    "total_capital": 1000000,
    "timestamp": "2024-01-01T00:00:00"
  }
}
        """
    )
    
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to JSON config file"
    )
    
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("./artifacts"),
        help="Directory for artifacts (default: ./artifacts)"
    )
    
    args = parser.parse_args()
    
    try:
        # Load config
        config = PortfolioCycleConfig.from_json_file(args.config)
        
        # Create artifact store
        artifact_store = LocalArtifactStore(args.artifacts_dir)
        
        # Create research engine
        research_engine = SimpleResearchEngine(artifact_store=artifact_store)
        
        # Create execution engine factory
        # Extract instrument from first strategy (assumes single instrument cycle)
        if not config.evaluation_config.strategies:
            raise CycleError("Evaluation config must contain at least one strategy")
        
        first_strategy = config.evaluation_config.strategies[0]
        instrument = first_strategy.inputs.get("instrument", "UNKNOWN")
        
        def create_engine():
            return PaperExecutionEngine(
                instrument=instrument,
                artifact_store=artifact_store
            )
        
        # Create state store
        state_store = LocalPortfolioStateStore(artifact_store)
        
        # Run cycle
        result = run_portfolio_cycle(
            config=config,
            research_engine=research_engine,
            artifact_store=artifact_store,
            execution_engine_factory=create_engine,
            state_store=state_store
        )
        
        # Persist cycle result
        cycle_id = persist_cycle_result(result, artifact_store)
        
        # Print summary
        print(f"Portfolio cycle complete: {cycle_id}")
        print(f"Status: {result.status}")
        if result.status != "completed":
            print(f"Reason: {result.skip_reason}")
        if result.evaluation_id:
            print(f"Evaluation ID: {result.evaluation_id}")
        if result.allocation_id:
            print(f"Allocation ID: {result.allocation_id}")
        if result.rebalance_plan_id:
            print(f"Rebalance Plan ID: {result.rebalance_plan_id}")
        if result.rebalance_execution_id:
            print(f"Rebalance Execution ID: {result.rebalance_execution_id}")
        if result.state_before_id:
            print(f"State before ID: {result.state_before_id}")
        if result.state_after_id:
            print(f"State after ID: {result.state_after_id}")
        if result.status == "completed":
            print(f"Top strategy: {result.summary['allocation_summary']['top_strategy_id']}")
            print(f"Strategies allocated: {result.summary['allocation_summary']['num_strategies']}")
            print(f"Execution success rate: {result.summary['execution_summary']['success_rate']:.1%}")
        
        sys.exit(0)
        
    except CycleError as e:
        print(f"Cycle error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

