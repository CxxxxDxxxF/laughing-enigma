"""Run management for backtest executions.

A Run represents a single execution of a backtest within an Experiment.
Runs track their status, inputs, and link to computed metrics and artifacts.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .experiment import Experiment


class RunStatus(Enum):
    """Execution status of a backtest run."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True)
class Run:
    """Immutable run record.
    
    A Run represents one execution of a backtest. Each run belongs to
    exactly one Experiment and produces Metrics and Artifacts upon
    successful completion.
    
    Attributes:
        id: Unique run identifier (e.g., UUID)
        experiment: The experiment this run belongs to
        status: Current execution status
        started_at: Timestamp when run started
        completed_at: Timestamp when run completed (if finished)
        error_message: Error message if status is FAILED
        inputs_hash: Deterministic hash of run inputs for reproducibility
        
    Note:
        inputs_hash ensures that identical inputs produce identical runs,
        which is critical for reproducibility.
    """
    
    id: str
    experiment: Experiment
    status: RunStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    inputs_hash: Optional[str] = None  # TODO: Define hash format (e.g., SHA256)
    
    def is_complete(self) -> bool:
        """Check if run has finished (success or failure).
        
        Returns:
            True if status is SUCCESS or FAILED, False otherwise
        """
        return self.status in (RunStatus.SUCCESS, RunStatus.FAILED)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize run to dictionary.
        
        Returns:
            Dictionary representation suitable for storage/JSON serialization.
            datetime objects are serialized as ISO format strings.
        """
        return {
            "id": self.id,
            "experiment": self.experiment.to_dict(),
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "inputs_hash": self.inputs_hash,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Run':
        """Deserialize run from dictionary.
        
        Args:
            data: Dictionary representation of run (from to_dict)
            
        Returns:
            Run instance
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        return cls(
            id=data["id"],
            experiment=Experiment.from_dict(data["experiment"]),
            status=RunStatus(data["status"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            error_message=data.get("error_message"),
            inputs_hash=data.get("inputs_hash"),
        )

