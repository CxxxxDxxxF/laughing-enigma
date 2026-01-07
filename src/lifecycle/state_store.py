"""Portfolio state store for persistent portfolio state management.

This module provides deterministic storage and retrieval of portfolio states
across cycles.
"""

import json
from typing import Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from abc import ABC, abstractmethod

from ..rebalance.planner import CurrentPortfolioState
from ..core.artifacts import ArtifactStore, ArtifactStoreError


class PortfolioStateStoreError(Exception):
    """Error raised when portfolio state store operations fail."""
    pass


class PortfolioStateStore(ABC):
    """Abstract interface for portfolio state storage."""
    
    @abstractmethod
    def load_latest_state(self, portfolio_id: str) -> Optional[CurrentPortfolioState]:
        """Load the latest state for a portfolio.
        
        Args:
            portfolio_id: Portfolio identifier
            
        Returns:
            Latest CurrentPortfolioState, or None if no state exists
        """
        raise NotImplementedError
    
    @abstractmethod
    def save_state(
        self,
        portfolio_id: str,
        state: CurrentPortfolioState,
        state_id: Optional[str] = None
    ) -> str:
        """Save a portfolio state.
        
        Args:
            portfolio_id: Portfolio identifier
            state: Portfolio state to save
            state_id: Optional state identifier (auto-generated if not provided)
            
        Returns:
            State identifier
        """
        raise NotImplementedError
    
    @abstractmethod
    def list_states(self, portfolio_id: str) -> List[str]:
        """List all state IDs for a portfolio (sorted, most recent first).
        
        Args:
            portfolio_id: Portfolio identifier
            
        Returns:
            List of state IDs, sorted by timestamp (most recent first)
        """
        raise NotImplementedError


class LocalPortfolioStateStore(PortfolioStateStore):
    """Local filesystem-based portfolio state store.
    
    Stores states in deterministic paths:
    artifacts/portfolio/{portfolio_id}/states/{state_id}.json
    
    Attributes:
        artifact_store: ArtifactStore instance
    """
    
    def __init__(self, artifact_store: ArtifactStore):
        """Initialize local portfolio state store.
        
        Args:
            artifact_store: ArtifactStore instance
        """
        self.artifact_store = artifact_store
    
    def _get_state_path(self, portfolio_id: str, state_id: str) -> str:
        """Get storage path for a state.
        
        Args:
            portfolio_id: Portfolio identifier
            state_id: State identifier
            
        Returns:
            Path relative to artifact store base
        """
        return f"portfolio/{portfolio_id}/states/{state_id}.json"
    
    def load_latest_state(self, portfolio_id: str) -> Optional[CurrentPortfolioState]:
        """Load the latest state for a portfolio.
        
        Args:
            portfolio_id: Portfolio identifier
            
        Returns:
            Latest CurrentPortfolioState, or None if no state exists
            
        Raises:
            PortfolioStateStoreError: If state cannot be loaded
        """
        try:
            state_ids = self.list_states(portfolio_id)
            if not state_ids:
                return None
            
            # Load most recent state
            latest_state_id = state_ids[0]
            return self._load_state(portfolio_id, latest_state_id)
            
        except Exception as e:
            raise PortfolioStateStoreError(f"Failed to load latest state for portfolio {portfolio_id}: {e}") from e
    
    def _load_state(self, portfolio_id: str, state_id: str) -> CurrentPortfolioState:
        """Load a specific state by ID.
        
        Args:
            portfolio_id: Portfolio identifier
            state_id: State identifier
            
        Returns:
            CurrentPortfolioState
            
        Raises:
            PortfolioStateStoreError: If state cannot be loaded
        """
        try:
            path = self._get_state_path(portfolio_id, state_id)
            # Get base path from artifact store
            if hasattr(self.artifact_store, 'base_path'):
                base_path = Path(self.artifact_store.base_path)
            else:
                base_path = Path("./artifacts")
            
            full_path = base_path / path
            
            if not full_path.exists():
                raise PortfolioStateStoreError(f"State file not found: {full_path}")
            
            data = json.loads(full_path.read_bytes().decode('utf-8'))
            
            # Load drawdown tracker if present
            drawdown_tracker = None
            if "drawdown_tracker" in data and data["drawdown_tracker"]:
                from ..rules.drawdown import DrawdownTracker
                drawdown_tracker = DrawdownTracker.from_dict(data["drawdown_tracker"])
            
            # Load positions if present
            positions_by_instrument = data.get("positions_by_instrument")
            
            # Default cash_balance to total_capital if not in stored data (backward compatibility)
            # This ensures old state files without cash_balance don't cause $0.00 balance errors
            cash_balance = data.get("cash_balance")
            if cash_balance is None:
                cash_balance = data["total_capital"]
            
            return CurrentPortfolioState(
                strategy_allocations=data["strategy_allocations"],
                total_capital=data["total_capital"],
                timestamp=datetime.fromisoformat(data["timestamp"]),
                drawdown_tracker=drawdown_tracker,
                positions_by_instrument=positions_by_instrument,
                cash_balance=cash_balance,
                metadata=data.get("metadata")
            )
            
        except Exception as e:
            raise PortfolioStateStoreError(f"Failed to load state {state_id}: {e}") from e
    
    def save_state(
        self,
        portfolio_id: str,
        state: CurrentPortfolioState,
        state_id: Optional[str] = None
    ) -> str:
        """Save a portfolio state.
        
        Args:
            portfolio_id: Portfolio identifier
            state: Portfolio state to save
            state_id: Optional state identifier (auto-generated if not provided)
            
        Returns:
            State identifier
            
        Raises:
            PortfolioStateStoreError: If state cannot be saved
        """
        try:
            if state_id is None:
                state_id = f"state_{state.timestamp.strftime('%Y%m%d_%H%M%S')}"
            
            # Serialize state to dict (use to_dict method if available)
            if hasattr(state, 'to_dict'):
                state_data = state.to_dict()
            else:
                state_data = {
                    "strategy_allocations": state.strategy_allocations,
                    "total_capital": state.total_capital,
                    "timestamp": state.timestamp.isoformat(),
                }
            state_json = json.dumps(state_data, indent=2).encode('utf-8')
            
            path = self._get_state_path(portfolio_id, state_id)
            # Get base path from artifact store
            if hasattr(self.artifact_store, 'base_path'):
                base_path = Path(self.artifact_store.base_path)
            else:
                # Fallback: assume artifacts directory
                base_path = Path("./artifacts")
            
            full_path = base_path / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(state_json)
            
            return state_id
            
        except Exception as e:
            raise PortfolioStateStoreError(f"Failed to save state for portfolio {portfolio_id}: {e}") from e
    
    def _is_checkpoint_state(self, state_id: str) -> bool:
        """Check if a state ID represents a valid loadable checkpoint.
        
        Contract:
        - Must end with '_after' (standard completed cycle)
        - OR match a known halted state pattern (if we migrate to metadata-based checking later)
        
        Currently enforces '_after' suffix as the single source of truth for "final state of a cycle".
        """
        return state_id.endswith('_after')

    def list_states(self, portfolio_id: str) -> List[str]:
        """List all state IDs for a portfolio (sorted, most recent first).
        
        Args:
            portfolio_id: Portfolio identifier
            
        Returns:
            List of state IDs, sorted by timestamp (most recent first)
        """
        try:
            base_path = Path(self.artifact_store.base_path)
            states_dir = base_path / "portfolio" / portfolio_id / "states"
            
            if not states_dir.exists():
                return []
            
            # Get all JSON files
            state_files = list(states_dir.glob("*.json"))
            
            # Extract state IDs and sort by filename (which contains timestamp)
            state_ids = [f.stem for f in state_files]
            
            # Filter to only checkpoint states (most recent completed/halted state)
            # This prevents loading intermediate _before snapshots or incorrectly named files
            checkpoint_state_ids = [sid for sid in state_ids if self._is_checkpoint_state(sid)]
            
            if checkpoint_state_ids:
                # Sort by filename (most recent first - assuming timestamp-based IDs)
                checkpoint_state_ids.sort(reverse=True)
                return checkpoint_state_ids
            else:
                # Fallback: if no checkpoint states found, return nothing (safer not to load partials)
                # But for backward compatibility or debugging, maybe return all?
                # User Requirement: "load_latest_state must never ignore halted states."
                # If we return partials, we risk rolling back. Better to return empty if no valid checkpoints.
                # However, original logic had a fallback.
                # To be "safer", we should strictly require compliance.
                # If no _after states exist, we assume no valid history.
                return []
            
        except Exception as e:
            raise PortfolioStateStoreError(f"Failed to list states for portfolio {portfolio_id}: {e}") from e

