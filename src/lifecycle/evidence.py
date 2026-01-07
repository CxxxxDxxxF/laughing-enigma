from __future__ import annotations
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from pathlib import Path

from ..core.artifacts import ArtifactStore

if TYPE_CHECKING:
    from ..lifecycle.runner import CycleResult
    from ..rebalance.planner import CurrentPortfolioState

# Remove direct import of CurrentPortfolioState to avoid potential issues if it imports runner
# But CurrentPortfolioState is in rebalance.planner, which imports from allocation, etc.
# likely fine but safer to put in TYPE_CHECKING if used only for typing.


@dataclass
class EvidenceBundle:
    """Comprehensive evidence record for a single portfolio cycle.
    
    This bundle aggregates:
    - Cycle metadata (ID, timestamp)
    - Inputs (Signals/Allocations)
    - Context (Market Data)
    - Controls (Guardrails, Rules)
    - Output (Execution, State Transition)
    """
    
    # Metadata
    cycle_id: str
    cycle_timestamp: str
    portfolio_id: str
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Inputs
    allocations: Dict[str, float] = field(default_factory=dict)
    
    # Context
    market_data: Dict[str, float] = field(default_factory=dict)  # Snapshot of prices used
    
    # Controls
    rules_violations: List[Dict[str, Any]] = field(default_factory=list)
    survivability_events: List[Dict[str, Any]] = field(default_factory=list)
    
    # Execution
    trades: List[Dict[str, Any]] = field(default_factory=list)
    
    # State Transition
    state_before_id: Optional[str] = None
    state_after_id: Optional[str] = None
    equity_before: float = 0.0
    equity_after: float = 0.0
    hwm_before: float = 0.0
    hwm_after: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return asdict(self)


def generate_evidence_bundle(
    cycle_result: CycleResult,
    artifact_store: ArtifactStore,
    prices_snapshot: Dict[str, float],
    state_before: Optional[CurrentPortfolioState] = None,
    state_after: Optional[CurrentPortfolioState] = None
) -> EvidenceBundle:
    """Generate the evidence bundle for a completed cycle.
    
    Args:
        cycle_result: The result of the cycle execution
        artifact_store: Store to retrieve referenced artifacts
        prices_snapshot: Dictionary of prices used during the cycle
        state_before: Portfolio state object before cycle
        state_after: Portfolio state object after cycle
        
    Returns:
        Populated EvidenceBundle
    """
    # 1. Load Allocations (if available)
    allocations = {}
    if cycle_result.allocation_id:
        try:
            alloc_data = artifact_store.retrieve(cycle_result.allocation_id, "allocation.json")
            if alloc_data:
                alloc_json = json.loads(alloc_data)
                # Extract target allocations map
                for alloc in alloc_json.get("allocations", []):
                    allocations[alloc.get("strategy_id")] = alloc.get("allocated_capital", 0.0)
        except Exception:
            # Fallback or log warning (non-critical for bundle existence, but bad for audit)
            pass

    # 2. Load Execution/Trades (if available)
    trades = []
    if cycle_result.rebalance_execution_id:
        try:
            exec_data = artifact_store.retrieve(cycle_result.rebalance_execution_id, "rebalance_execution.json")
            if exec_data:
                exec_json = json.loads(exec_data)
                for intent in exec_json.get("intent_results", []):
                    for fill in intent.get("fills", []):
                        trades.append(fill)
        except Exception:
            pass
            
    # 3. Extract Metrics from States
    equity_before = state_before.total_capital if state_before else 0.0
    equity_after = state_after.total_capital if state_after else 0.0
    
    hwm_before = 0.0
    if state_before and state_before.drawdown_tracker:
        hwm_before = state_before.drawdown_tracker.high_water_mark
        
    hwm_after = 0.0
    if state_after and state_after.drawdown_tracker:
        hwm_after = state_after.drawdown_tracker.high_water_mark
    
    return EvidenceBundle(
        cycle_id=cycle_result.cycle_id,
        cycle_timestamp=cycle_result.cycle_timestamp.isoformat(),
        portfolio_id=cycle_result.portfolio_id,
        allocations=allocations,
        market_data=prices_snapshot,
        rules_violations=[v for v in (cycle_result.rules_violations or [])],
        survivability_events=[e for e in (cycle_result.survivability_control_events or [])],
        trades=trades,
        state_before_id=cycle_result.state_before_id,
        state_after_id=cycle_result.state_after_id,
        equity_before=equity_before,
        equity_after=equity_after,
        hwm_before=hwm_before,
        hwm_after=hwm_after
    )


def persist_evidence_bundle(
    bundle: EvidenceBundle,
    artifact_store: ArtifactStore
) -> str:
    """Persist the evidence bundle to the artifact store.
    
    Args:
        bundle: The evidence bundle to save
        artifact_store: Store to save to
        
    Returns:
        The filename/ID of the saved bundle
    """
    try:
        data = json.dumps(bundle.to_dict(), indent=2).encode('utf-8')
        # Save as "evidence_{cycle_id}.json" in the root or run folder?
        # ArtifactStore.store takes (run_id, filename).
        # We can use cycle_id as run_id to keep it grouped with other cycle artifacts if that's the convention.
        # Or store it in a dedicated "evidence" pseudo-run.
        # Let's check runner.py convention.
        # runner.py uses `cycle_id` as the container for `cycle_result.json`.
        # So we should store it in `cycle_id` as well.
        
        artifact_store.store(bundle.cycle_id, "evidence.json", data)
        return f"{bundle.cycle_id}/evidence.json"
    except Exception as e:
        # Raise generic exception which runner will catch and wrap
        raise Exception(f"Failed to persist evidence bundle: {e}") from e
