"""Artifact storage and retrieval for backtest outputs.

Artifacts are stored outputs from backtest runs (e.g., charts, data files).
The ArtifactStore provides a unified interface for storing and retrieving
these artifacts regardless of underlying storage mechanism.
"""

import os
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
from pathlib import Path


class ArtifactStoreError(Exception):
    """Error raised when artifact storage operations fail."""
    pass


class ArtifactStore(ABC):
    """Abstract interface for artifact storage.
    
    Artifacts are files or binary data produced by backtest runs.
    Examples: equity curve plots, trade logs, performance charts.
    
    The store is engine-agnostic and provides simple get/put semantics.
    """
    
    @abstractmethod
    def store(self, run_id: str, artifact_name: str, data: bytes) -> str:
        """Store an artifact for a given run.
        
        Args:
            run_id: ID of the run this artifact belongs to
            artifact_name: Name/identifier for the artifact (e.g., "equity_curve.png")
            data: Binary data to store
            
        Returns:
            Storage path or URI for the artifact
            
        Note:
            Storage path should be deterministic based on run_id and
            artifact_name to ensure reproducibility.
        """
        raise NotImplementedError
    
    @abstractmethod
    def retrieve(self, run_id: str, artifact_name: str) -> Optional[bytes]:
        """Retrieve an artifact for a given run.
        
        Args:
            run_id: ID of the run this artifact belongs to
            artifact_name: Name/identifier for the artifact
            
        Returns:
            Binary data if artifact exists, None otherwise
        """
        raise NotImplementedError
    
    @abstractmethod
    def list_artifacts(self, run_id: str) -> list[str]:
        """List all artifacts for a given run.
        
        Args:
            run_id: ID of the run to list artifacts for
            
        Returns:
            List of artifact names for this run
        """
        raise NotImplementedError
    
    @abstractmethod
    def delete(self, run_id: str, artifact_name: str) -> bool:
        """Delete an artifact.
        
        Args:
            run_id: ID of the run this artifact belongs to
            artifact_name: Name/identifier for the artifact
            
        Returns:
            True if artifact was deleted, False if it didn't exist
        """
        raise NotImplementedError
    
    def get_path(self, run_id: str, artifact_name: str) -> Path:
        """Get the storage path for an artifact (without storing).
        
        This is useful for deterministic path generation before storage.
        
        Args:
            run_id: ID of the run this artifact belongs to
            artifact_name: Name/identifier for the artifact
            
        Returns:
            Path where artifact would be stored
            
        Note:
            Path should be deterministic based on run_id and artifact_name.
        """
        # Default implementation: subclasses should override
        raise NotImplementedError


class LocalArtifactStore(ArtifactStore):
    """Filesystem-based artifact store.
    
    Stores artifacts in a deterministic directory structure:
        base_path/runs/{run_id}/{artifact_name}
    
    All paths are deterministic based on run_id and artifact_name.
    Directories are created as needed.
    
    Attributes:
        base_path: Base directory for artifact storage
    """
    
    def __init__(self, base_path: Path):
        """Initialize local artifact store.
        
        Args:
            base_path: Base directory path for storing artifacts
            
        Raises:
            ArtifactStoreError: If base_path cannot be created or accessed
        """
        self.base_path = Path(base_path)
        
        # Create base directory if it doesn't exist
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ArtifactStoreError(
                f"Failed to create base directory {base_path}: {e}"
            ) from e
    
    def get_path(self, run_id: str, artifact_name: str) -> Path:
        """Get deterministic storage path for an artifact.
        
        Path structure: base_path/runs/{run_id}/{artifact_name}
        
        Args:
            run_id: ID of the run this artifact belongs to
            artifact_name: Name/identifier for the artifact
            
        Returns:
            Path where artifact would be stored
        """
        return self.base_path / "runs" / run_id / artifact_name
    
    def store(self, run_id: str, artifact_name: str, data: bytes) -> str:
        """Store an artifact to the filesystem.
        
        Creates directories as needed. Fails loudly on I/O errors.
        
        Args:
            run_id: ID of the run this artifact belongs to
            artifact_name: Name/identifier for the artifact
            data: Binary data to store
            
        Returns:
            String representation of storage path (absolute)
            
        Raises:
            ArtifactStoreError: If storage fails (I/O errors, permission issues)
        """
        artifact_path = self.get_path(run_id, artifact_name)
        
        # Create parent directory if it doesn't exist
        try:
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ArtifactStoreError(
                f"Failed to create directory {artifact_path.parent}: {e}"
            ) from e
        
        # Write data to file
        try:
            artifact_path.write_bytes(data)
        except OSError as e:
            raise ArtifactStoreError(
                f"Failed to write artifact {artifact_name} to {artifact_path}: {e}"
            ) from e
        
        # Return absolute path as string
        return str(artifact_path.resolve())
    
    def retrieve(self, run_id: str, artifact_name: str) -> Optional[bytes]:
        """Retrieve an artifact from the filesystem.
        
        Args:
            run_id: ID of the run this artifact belongs to
            artifact_name: Name/identifier for the artifact
            
        Returns:
            Binary data if artifact exists, None otherwise
            
        Raises:
            ArtifactStoreError: If retrieval fails (permission issues, etc.)
        """
        artifact_path = self.get_path(run_id, artifact_name)
        
        if not artifact_path.exists():
            return None
        
        try:
            return artifact_path.read_bytes()
        except OSError as e:
            raise ArtifactStoreError(
                f"Failed to read artifact {artifact_name} from {artifact_path}: {e}"
            ) from e
    
    def list_artifacts(self, run_id: str) -> list[str]:
        """List all artifacts for a given run.
        
        Args:
            run_id: ID of the run to list artifacts for
            
        Returns:
            List of artifact names (files only, not directories)
            
        Raises:
            ArtifactStoreError: If listing fails
        """
        run_dir = self.base_path / "runs" / run_id
        
        if not run_dir.exists():
            return []
        
        try:
            # List only files, not directories
            return [
                item.name
                for item in run_dir.iterdir()
                if item.is_file()
            ]
        except OSError as e:
            raise ArtifactStoreError(
                f"Failed to list artifacts in {run_dir}: {e}"
            ) from e
    
    def delete(self, run_id: str, artifact_name: str) -> bool:
        """Delete an artifact from the filesystem.
        
        Args:
            run_id: ID of the run this artifact belongs to
            artifact_name: Name/identifier for the artifact
            
        Returns:
            True if artifact was deleted, False if it didn't exist
            
        Raises:
            ArtifactStoreError: If deletion fails
        """
        artifact_path = self.get_path(run_id, artifact_name)
        
        if not artifact_path.exists():
            return False
        
        try:
            artifact_path.unlink()
            return True
        except OSError as e:
            raise ArtifactStoreError(
                f"Failed to delete artifact {artifact_name} from {artifact_path}: {e}"
            ) from e

