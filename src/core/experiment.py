"""Experiment registry for quant research backtests.

An Experiment represents a named, versioned configuration for backtesting.
Experiments are hashable and reproducible by design.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Experiment:
    """Immutable experiment definition.
    
    Experiments are the top-level organizational unit. Each experiment
    has a unique name and version, making it fully identifiable and
    reproducible.
    
    Attributes:
        name: Unique experiment identifier (e.g., "momentum_strategy_v1")
        version: Version string for this experiment config
        config: Hashable configuration dict that defines experiment parameters
        created_at: Timestamp when experiment was created
        description: Optional human-readable description
        
    Note:
        config must be hashable to ensure reproducibility. Use tuples
        instead of lists, frozensets instead of sets, etc.
    """
    
    name: str
    version: str
    config: Dict[str, Any]  # TODO: Define stricter hashable config type
    created_at: datetime
    description: Optional[str] = None
    
    # Note: frozen=True dataclass automatically implements __hash__ based on all fields
    # TODO: Ensure config is hashable (use tuples for lists, frozensets for sets)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize experiment to dictionary.
        
        Returns:
            Dictionary representation suitable for storage/JSON serialization.
            datetime is serialized as ISO format string.
        """
        return {
            "name": self.name,
            "version": self.version,
            "config": self.config,
            "created_at": self.created_at.isoformat(),
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Experiment':
        """Deserialize experiment from dictionary.
        
        Args:
            data: Dictionary representation of experiment (from to_dict)
            
        Returns:
            Experiment instance
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        return cls(
            name=data["name"],
            version=data["version"],
            config=data["config"],
            created_at=datetime.fromisoformat(data["created_at"]),
            description=data.get("description"),
        )

