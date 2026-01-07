"""Simple research engine for deterministic backtesting.

This engine implements a minimal, fully deterministic backtest engine.
Purpose is truth, not performance.

Assumptions:
- Single instrument only
- Simple buy-and-hold or rule-based strategy
- Deterministic price generation from inputs
- No randomness, no ML, no external data
"""

import hashlib
import json
import numpy as np
from functools import lru_cache
@lru_cache(maxsize=128)
def _hash_to_seed(inputs_hash: str) -> int:
    """Convert a deterministic hash string to an integer seed.
    Uses the first 16 hex characters of the hash.
    Cached for performance when the same inputs are used repeatedly.
    """
    return int(inputs_hash[:16], 16)

from typing import Dict, Any, List, Tuple, Optional
# Removed duplicate import; lru_cache already imported above
from datetime import datetime, timedelta

from .base import BaseResearchEngine, BacktestResult, BacktestError
from ..core.experiment import Experiment
from ..core.metrics import Metrics
from ..core.metrics import Metrics
from ..core.artifacts import ArtifactStore
from ..strategy.factory import StrategyFactory
from ..execution.signal import SignalType


class SimpleResearchEngineError(BacktestError):
    """Error specific to SimpleResearchEngine."""
    pass


class RawReturns:
    """Container for raw return series from backtest.
    
    This is the minimal output from SimpleResearchEngine before
    Metrics computation. Contains the fundamental data needed to
    compute all metrics.
    
    Attributes:
        dates: List of date strings (YYYY-MM-DD format)
        returns: Daily returns as decimal (e.g., 0.01 = 1%)
        initial_capital: Starting capital
        final_value: Ending portfolio value
    """
    
    def __init__(
        self,
        dates: List[str],
        returns: List[float],
        initial_capital: float,
        final_value: float
    ):
        if len(dates) != len(returns):
            raise ValueError("dates and returns must have same length")
        self.dates = dates
        self.returns = returns
        self.initial_capital = initial_capital
        self.final_value = final_value
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize raw returns to dictionary."""
        return {
            "dates": self.dates,
            "returns": self.returns,
            "initial_capital": self.initial_capital,
            "final_value": self.final_value
        }


class SimpleResearchEngine(BaseResearchEngine):
    """Simple, deterministic research engine.
    
    This engine generates synthetic, deterministic return series based on
    experiment configuration and inputs. It does NOT use real market data.
    
    Strategy:
    - Single instrument (specified in inputs)
    - Buy and hold (or simple rule-based strategy)
    - Deterministic price movements generated from inputs hash
    
    Input Requirements:
    - start_date: Start date as "YYYY-MM-DD"
    - end_date: End date as "YYYY-MM-DD"
    - initial_capital: Starting capital (float)
    - instrument: Instrument identifier (str)
    - strategy_type: "buy_hold" (only supported type for now)
    
    Experiment Config:
    - May contain strategy parameters (optional)
    
    Determinism:
    - Price movements are generated deterministically from inputs hash
    - Same inputs always produce same returns
    - No randomness source
    """
    
    def __init__(self, artifact_store: Optional[ArtifactStore] = None):
        """Initialize simple research engine.
        
        Args:
            artifact_store: Optional artifact store for persisting results.
                           If None, artifacts are not persisted.
        """
        self.artifact_store = artifact_store
    
    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate inputs for SimpleResearchEngine.
        
        Required inputs:
        - start_date: "YYYY-MM-DD" format string
        - end_date: "YYYY-MM-DD" format string  
        - initial_capital: Positive float
        - instrument: Non-empty string
        - strategy_type: "buy_hold" (only supported)
        
        Args:
            inputs: Input parameters to validate
            
        Returns:
            True if inputs are valid, False otherwise
            
        Raises:
            SimpleResearchEngineError: If validation fails with details
        """
        required = {"start_date", "end_date", "initial_capital", "instrument", "strategy_type"}
        missing = required - set(inputs.keys())
        if missing:
            raise SimpleResearchEngineError(
                f"Missing required inputs: {missing}. "
                f"Received: {list(inputs.keys())}"
            )
        
        # Validate start_date format
        try:
            start_date = datetime.strptime(inputs["start_date"], "%Y-%m-%d")
        except (ValueError, TypeError) as e:
            raise SimpleResearchEngineError(
                f"Invalid start_date format: {inputs['start_date']}. "
                f"Expected YYYY-MM-DD. Error: {e}"
            )
        
        # Validate end_date format
        try:
            end_date = datetime.strptime(inputs["end_date"], "%Y-%m-%d")
        except (ValueError, TypeError) as e:
            raise SimpleResearchEngineError(
                f"Invalid end_date format: {inputs['end_date']}. "
                f"Expected YYYY-MM-DD. Error: {e}"
            )
        
        # Validate date ordering
        if end_date <= start_date:
            raise SimpleResearchEngineError(
                f"end_date ({inputs['end_date']}) must be after "
                f"start_date ({inputs['start_date']})"
            )
        
        # Validate initial_capital
        capital = inputs["initial_capital"]
        if not isinstance(capital, (int, float)) or capital <= 0:
            raise SimpleResearchEngineError(
                f"initial_capital must be positive number, got: {capital} (type: {type(capital)})"
            )
        
        # Validate instrument
        instrument = inputs["instrument"]
        if not isinstance(instrument, str) or not instrument.strip():
            raise SimpleResearchEngineError(
                f"instrument must be non-empty string, got: {instrument}"
            )
        
        # Validate strategy_type
        strategy_type = inputs["strategy_type"]
        if strategy_type != "buy_hold" and strategy_type not in StrategyFactory._registry:
             raise SimpleResearchEngineError(
                f"strategy_type must be 'buy_hold' or a registered strategy, got: {strategy_type}. "
                f"Available: {['buy_hold'] + list(StrategyFactory._registry.keys())}"
            )
        
        return True
    
    def compute_inputs_hash(self, inputs: Dict[str, Any]) -> str:
        """Compute deterministic SHA256 hash of inputs.
        
        Hash is computed by:
        1. Sorting input keys for consistency
        2. Serializing to JSON (deterministic)
        3. Computing SHA256 hex digest
        
        Args:
            inputs: Input parameters to hash
            
        Returns:
            SHA256 hex digest string (64 characters)
        """
        # Sort keys for deterministic ordering
        sorted_inputs = dict(sorted(inputs.items()))
        
        # Serialize to JSON (deterministic, no whitespace)
        json_str = json.dumps(sorted_inputs, sort_keys=True, separators=(',', ':'))
        
        # Compute SHA256 hash
        hash_obj = hashlib.sha256(json_str.encode('utf-8'))
        return hash_obj.hexdigest()
    
    def run_backtest(
        self,
        experiment: Experiment,
        run_id: str,
        inputs: Dict[str, Any]
    ) -> BacktestResult:
        """Execute deterministic backtest.
        
        Process:
        1. Validate inputs (raises on failure)
        2. Compute inputs hash for reproducibility
        3. Generate deterministic return series
        4. Compute metrics from raw returns
        5. Persist artifacts (if artifact_store is configured)
        6. Return BacktestResult with metrics and artifact paths
        
        Args:
            experiment: Experiment configuration
            run_id: Unique run identifier
            inputs: Input parameters (start_date, end_date, etc.)
            
        Returns:
            BacktestResult containing metrics and artifact paths
            
        Raises:
            SimpleResearchEngineError: If backtest execution fails
        """
        # Validate inputs (raises on failure)
        self.validate_inputs(inputs)
        
        # Parse dates
        start_date = datetime.strptime(inputs["start_date"], "%Y-%m-%d")
        end_date = datetime.strptime(inputs["end_date"], "%Y-%m-%d")
        initial_capital = float(inputs["initial_capital"])
        instrument = inputs["instrument"]
        
        # Generate deterministic return series
        raw_returns = self._generate_deterministic_returns(
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            instrument=instrument,
            inputs_hash=self.compute_inputs_hash(inputs),
            inputs=inputs, # Pass full inputs
            experiment_config=experiment.config
        )
        
        # Compute metrics from raw returns
        metrics = Metrics.compute(run_id, raw_returns)
        
        # Persist artifacts if store is available
        artifact_paths = {}
        if self.artifact_store is not None:
            artifact_paths = self._persist_artifacts(run_id, raw_returns, metrics, experiment, inputs)
        
        return BacktestResult(
            run_id=run_id,
            metrics=metrics,
            artifact_paths=artifact_paths
        )
    
    def _generate_deterministic_returns(
        self,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        instrument: str,
        inputs_hash: str,
        inputs: Dict[str, Any], # Add inputs arg
        experiment_config: Dict[str, Any]
    ) -> RawReturns:
        """Generate deterministic return series.
        
        Strategy: Simple buy-and-hold with deterministic price movements.
        
        Price generation:
        - Use inputs_hash as seed for deterministic pseudo-random walk
        - Convert hash to integer seed
        - Generate daily returns using deterministic function
        - Returns are bounded and smooth to be realistic
        
        Assumptions:
        - Trading every calendar day (no market closures)
        - No transaction costs
        - Perfect execution
        
        Args:
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Starting capital
            instrument: Instrument identifier
            inputs_hash: Deterministic hash of inputs
            experiment_config: Experiment configuration
            
        Returns:
            RawReturns containing dates and return series
        """
        # Generate list of dates (inclusive)
        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)
        
        num_days = len(dates)
        
        # Generate list of dates (inclusive)
        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)

        num_days = len(dates)

        
        # 2. Simulate Strategy Execution
        # ---------------------------------------------------------------------
        strategy_type = inputs.get("strategy_type", "buy_hold")
        
        # Determine strategy instance
        strategy = None
        if strategy_type != "buy_hold":
            # Assume we can create it with default config or config from inputs
            # For this simple engine, we pass the inputs as config
            try:
            # Add instrument to config
                config = inputs.copy()
                # Compat: Ensure single-instrument optimization sets the strategy tickers
                if "tickers" not in config and "instrument" in config:
                    config["tickers"] = [config["instrument"]]
                
                strategy = StrategyFactory.create(strategy_type, config)
            except Exception as e:
                # If creation fails, we might fall back or error. 
                # Ideally validation caught this, but factory might have runtime reqs.
                pass 

        final_returns = []
        portfolio_value = initial_capital
        
        # Price reconstruction for strategy
        # Market Price starts at 100.0 (arbitrary)
        market_price = 100.0
        price_history = [market_price] 
        
        # Current Position (0.0 to 1.0)
        # BuyHold = 1.0 always
        # Strategies start at 0.0 (Cash) or 1.0? 
        # Let's assume start with 0.0 and wait for signal.
        current_position = 1.0 if strategy_type == "buy_hold" else 0.0
        
        # Generate deterministic daily returns
        # Use hash as seed to ensure determinism
        seed = int(inputs_hash[:16], 16)

        for i in range(num_days):
            # 1. Get Market Return for Today
            # Deterministic pseudo-random value from seed and day index
            pseudo_random = ((seed + i * 7919) % 10000) / 10000.0
            market_daily_return = 0.0001 * (2 * pseudo_random - 1)  # -0.01% to +0.01%
            
            # Add trend
            trend = experiment_config.get("daily_trend", 0.0001)
            market_daily_return += trend
            
            # 2. Update Market Price
            market_price *= (1 + market_daily_return)
            
            # 3. Strategy Decision (if applicable)
            if strategy:
                # Feed history including TODAY's price (Close) or Yesterday's?
                # In backtesting, typically we run signal on CLOSE of T, execute on OPEN of T+1?
                # Or Signal on Close T-1, Execute Close T?
                # For simplicity in this engine: 
                #   We use history up to T-1 to generate signal for T?
                #   Or we use history up to T (today) to determine allocation for T? (Requires lookahead if using Close)
                #   Standard: Calculate signal using Prices[...T-1]. Execute at Price[T] (assuming Market on Open).
                #   Let's do: Signal based on History[...T-1]. (If i==0, history is empty/just init).
                
                # Mock data provider dict for strategy
                # Strategy expects {instrument: [prices]}
                data_snapshot = {instrument: price_history.copy()}
                
                signals = strategy.generate_signals(data_snapshot)
                
                # Handle single signal or list of signals
                signal = None
                if isinstance(signals, list):
                    # Filter for our instrument
                    inst_signals = [s for s in signals if s.instrument == instrument]
                    if inst_signals:
                        signal = inst_signals[0]
                else:
                    signal = signals
                
                if signal:
                    # print(f"DEBUG: Day {i} Signal: {signal.signal_type} Momentum: {signal.metadata.get('momentum')}")
                    if signal.signal_type == SignalType.BUY:
                        current_position = 1.0
                    elif signal.signal_type == SignalType.SELL:
                        current_position = 0.0
                # else:
                #    print(f"DEBUG: Day {i} No Signal. Hist len: {len(price_history)}")
                        
            # 4. Calculate Portfolio Return considering Position
            # Portfolio Return = MarketReturn * Position
            portfolio_daily_return = market_daily_return * current_position
            # if current_position > 0:
            #    print(f"DEBUG: Day {i} Return: {portfolio_daily_return:.6f} Pos: {current_position}")
            
            final_returns.append(portfolio_daily_return)
            portfolio_value *= (1 + portfolio_daily_return)
            
            # Append today's price to history for NEXT day's decision
            price_history.append(market_price)

        return RawReturns(
            dates=dates,
            returns=final_returns,
            initial_capital=initial_capital,
            final_value=portfolio_value
        )
    
    def _persist_artifacts(
        self,
        run_id: str,
        raw_returns: RawReturns,
        metrics: Metrics,
        experiment: Experiment,
        inputs: Dict[str, Any]
    ) -> Dict[str, str]:
        """Persist artifacts to artifact store.
        
        Stores:
        - raw_returns.json: Raw returns data
        - metrics.json: Computed metrics
        - run_metadata.json: Run metadata (experiment, inputs, etc.)
        
        Args:
            run_id: Run identifier
            raw_returns: Raw returns to persist
            metrics: Metrics to persist
            experiment: Experiment configuration
            inputs: Input parameters
            
        Returns:
            Dictionary mapping artifact names to storage paths
            
        Raises:
            SimpleResearchEngineError: If persistence fails
        """
        if self.artifact_store is None:
            return {}
        
        artifact_paths = {}
        
        try:
            # Store raw returns as JSON
            raw_returns_json = json.dumps(raw_returns.to_dict(), indent=2).encode('utf-8')
            artifact_paths["raw_returns"] = self.artifact_store.store(
                run_id, "raw_returns.json", raw_returns_json
            )
            
            # Store metrics as JSON
            metrics_json = json.dumps(metrics.to_dict(), indent=2).encode('utf-8')
            artifact_paths["metrics"] = self.artifact_store.store(
                run_id, "metrics.json", metrics_json
            )
            
            # Store run metadata as JSON
            # Serialize experiment (convert datetime to ISO string)
            experiment_dict = {
                "name": experiment.name,
                "version": experiment.version,
                "config": experiment.config,
                "created_at": experiment.created_at.isoformat(),
                "description": experiment.description,
            }
            run_metadata = {
                "run_id": run_id,
                "experiment": experiment_dict,
                "inputs": inputs,
                "inputs_hash": self.compute_inputs_hash(inputs),
            }
            metadata_json = json.dumps(run_metadata, indent=2).encode('utf-8')
            artifact_paths["run_metadata"] = self.artifact_store.store(
                run_id, "run_metadata.json", metadata_json
            )
            
        except Exception as e:
            raise SimpleResearchEngineError(
                f"Failed to persist artifacts for run {run_id}: {e}"
            ) from e
        
        return artifact_paths

