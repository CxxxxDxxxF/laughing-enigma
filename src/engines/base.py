"""Base research engine interface for backtest execution.

Research engines are pluggable components that execute backtests.
This module defines the abstract interface that all engines must implement.
"""

from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

from ..core.run import Run
from ..core.metrics import Metrics
from ..core.experiment import Experiment


class BaseResearchEngine(ABC):
    """Abstract base class for research engines.
    
    Research engines execute backtests deterministically based on
    experiment configuration. Engines are isolated and swappable -
    you can run the same experiment with different engines and
    compare results.
    
    Key requirements:
    - Deterministic: Same inputs must produce same outputs
    - Isolated: No shared state between runs
    - Reproducible: Can replay any run from stored inputs
    """
    
    @abstractmethod
    def run_backtest(
        self,
        experiment: Experiment,
        run_id: str,
        inputs: Dict[str, Any]
    ) -> 'BacktestResult':
        """Execute a backtest run.
        
        Args:
            experiment: Experiment configuration to run
            run_id: Unique identifier for this run
            inputs: Hashable input parameters (e.g., date range, universe)
            
        Returns:
            BacktestResult containing metrics and artifacts
            
        Raises:
            BacktestError: If backtest execution fails
            
        Note:
            This method must be deterministic. Given the same experiment,
            run_id, and inputs, it must produce identical results.
        """
        raise NotImplementedError
    
    @abstractmethod
    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs are acceptable for this engine.
        
        Args:
            inputs: Input parameters to validate
            
        Returns:
            True if inputs are valid, False otherwise
        """
        raise NotImplementedError
    
    @abstractmethod
    def compute_inputs_hash(self, inputs: Dict[str, Any]) -> str:
        """Compute deterministic hash of inputs.
        
        Args:
            inputs: Input parameters to hash
            
        Returns:
            Deterministic hash string (e.g., SHA256 hex digest)
            
        Note:
            Hash must be deterministic and reproducible. Same inputs
            must always produce same hash.
        """
        raise NotImplementedError


class BacktestResult:
    """Result container for completed backtest runs.
    
    This is returned by research engines after backtest execution.
    It contains all outputs: metrics and artifact references.
    
    Attributes:
        run_id: ID of the run that produced this result
        metrics: Computed metrics from the backtest
        artifact_paths: Dict mapping artifact names to storage paths/URIs
        raw_returns: Optional RawReturns object (in-memory, for --light-artifacts mode)
            If provided, evaluator should use this instead of loading from artifacts.
    """
    
    def __init__(
        self,
        run_id: str,
        metrics: Metrics,
        artifact_paths: Dict[str, str],
        raw_returns: Optional[Any] = None  # RawReturns type, but avoid circular import
    ):
        self.run_id = run_id
        self.metrics = metrics
        self.artifact_paths = artifact_paths
        self.raw_returns = raw_returns  # In-memory raw returns for determinism verification


class BacktestError(Exception):
    """Base exception for backtest execution errors."""
    pass

