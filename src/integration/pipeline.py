"""Signal pipeline for connecting backtests to execution.

This module provides helper functions to wire research outputs to execution inputs.
"""

from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..engines.simple import SimpleResearchEngine, RawReturns, BacktestResult
    from ..execution import PaperExecutionEngine, ExecutionEngine
    from ..core.experiment import Experiment
from .simple_emitter import SimpleSignalEmitter
from .simple_adapter import SimpleSignalAdapter, AdapterConfig
from .simple_consumer import SimpleSignalConsumer
from .adapter import InvalidSignalError, RiskCheckError


class SignalPipeline:
    """Pipeline that connects backtest results to paper execution.
    
    This class wires together:
    - SignalEmitter (emits signals from backtest)
    - SignalAdapter (validates and adapts signals)
    - SignalConsumer (submits to execution engine)
    
    Attributes:
        emitter: SignalEmitter instance
        adapter: SignalAdapter instance
        consumer: SignalConsumer instance
    """
    
    def __init__(
        self,
        emitter: Optional[SimpleSignalEmitter] = None,
        adapter: Optional[SimpleSignalAdapter] = None,
        consumer: Optional[SimpleSignalConsumer] = None
    ):
        """Initialize signal pipeline.
        
        Args:
            emitter: SignalEmitter instance (default: SimpleSignalEmitter with defaults)
            adapter: SignalAdapter instance (default: SimpleSignalAdapter with defaults)
            consumer: SignalConsumer instance (default: SimpleSignalConsumer)
        """
        self.emitter = emitter or SimpleSignalEmitter()
        self.adapter = adapter or SimpleSignalAdapter()
        self.consumer = consumer or SimpleSignalConsumer()
    
    def process_backtest_to_execution(
        self,
        backtest_result: 'BacktestResult',
        execution_engine: 'ExecutionEngine',
        instrument: str,
        current_prices: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """Process backtest result and submit signals to execution engine.
        
        Process:
        1. Load raw returns from backtest artifacts
        2. Emit signals using emitter
        3. Adapt signals using adapter
        4. Submit signals to execution engine via consumer
        5. Execute orders at provided prices
        
        Args:
            backtest_result: BacktestResult from research engine
            execution_engine: ExecutionEngine to submit signals to
            instrument: Instrument identifier
            current_prices: Optional list of prices for execution (one per signal)
            
        Returns:
            Dictionary with processing results:
            - signals_emitted: Number of raw signals emitted
            - signals_adapted: Number of signals successfully adapted
            - signals_filtered: Number of signals filtered out
            - orders_created: Number of orders created
            - orders_executed: Number of orders executed
            - errors: List of error messages
            
        Note:
            This is a simplified implementation. In production, you would
            load raw returns from artifacts, match prices to signals, etc.
        """
        # For now, we need raw returns which we don't have in BacktestResult
        # This is a limitation we'll address - for now this is a placeholder
        # that shows the intended flow
        
        results = {
            "signals_emitted": 0,
            "signals_adapted": 0,
            "signals_filtered": 0,
            "orders_created": 0,
            "orders_executed": 0,
            "errors": []
        }
        
        # TODO: Load raw returns from artifacts using backtest_result.run_id
        # For now, this shows the structure but requires raw returns to be passed in
        
        return results


def run_backtest_and_execute(
    research_engine: 'SimpleResearchEngine',
    experiment: 'Experiment',
    run_id: str,
    inputs: Dict[str, Any],
    execution_engine: 'PaperExecutionEngine',
    instrument: str,
    price_series: Optional[List[float]] = None,
    adapter_config: Optional[AdapterConfig] = None
) -> Dict[str, Any]:
    """Run backtest and automatically execute signals in paper trading.
    
    This is a convenience function that:
    1. Runs backtest using research engine
    2. Extracts raw returns from backtest
    3. Emits signals using SimpleSignalEmitter
    4. Adapts signals using SimpleSignalAdapter
    5. Submits signals to execution engine
    6. Executes orders at provided prices
    
    Args:
        research_engine: Research engine to run backtest
        experiment: Experiment configuration
        run_id: Run identifier
        inputs: Backtest inputs
        execution_engine: Paper execution engine
        instrument: Instrument identifier (should match inputs["instrument"])
        price_series: Optional list of prices for execution (one per day)
        adapter_config: Optional adapter configuration
        
    Returns:
        Dictionary with results:
        - backtest_result: BacktestResult from research
        - signals_emitted: Number of signals emitted
        - orders_created: Number of orders created
        - orders_executed: Number of orders executed
        - errors: List of errors
        
    Raises:
        Exception: If backtest execution fails
    """
    # Run backtest
    backtest_result = research_engine.run_backtest(experiment, run_id, inputs)
    
    # Extract raw returns (we need to load from artifacts)
    # For now, we'll need to reconstruct or pass raw returns
    # This is a limitation - we should store raw returns in a way that's accessible
    
    results = {
        "backtest_result": backtest_result,
        "signals_emitted": 0,
        "orders_created": 0,
        "orders_executed": 0,
        "errors": []
    }
    
    # TODO: Load raw returns from artifacts
    # For now, this function shows the intended structure
    
    return results


def execute_signals_from_raw_returns(
    raw_returns: 'RawReturns',
    instrument: str,
    execution_engine: 'PaperExecutionEngine',
    price_series: Optional[List[float]] = None,
    emitter: Optional[SimpleSignalEmitter] = None,
    adapter_config: Optional[AdapterConfig] = None
) -> Dict[str, Any]:
    """Execute signals from raw returns data.
    
    This function processes raw returns and executes signals in paper trading.
    
    Args:
        raw_returns: RawReturns from backtest
        instrument: Instrument identifier
        execution_engine: Paper execution engine
        price_series: Optional list of prices for execution (one per signal day)
        emitter: Optional signal emitter (default: SimpleSignalEmitter)
        adapter_config: Optional adapter configuration
        
    Returns:
        Dictionary with execution results:
        - signals_emitted: Number of signals emitted
        - signals_adapted: Number of signals adapted
        - orders_created: List of created orders
        - orders_executed: List of executed orders
        - errors: List of errors
    """
    emitter = emitter or SimpleSignalEmitter()
    adapter = SimpleSignalAdapter(config=adapter_config)
    consumer = SimpleSignalConsumer()
    
    results = {
        "signals_emitted": 0,
        "signals_adapted": 0,
        "signals_filtered": 0,
        "orders_created": [],
        "orders_executed": [],
        "errors": []
    }
    
    # Emit signals
    signals = list(emitter.emit_signals(raw_returns, instrument=instrument))
    results["signals_emitted"] = len(signals)
    
    # Process each signal
    price_index = 0
    for raw_signal in signals:
        try:
            # Adapt signal
            signal = adapter.adapt(raw_signal)
            
            if signal is None:
                results["signals_filtered"] += 1
                continue
            
            results["signals_adapted"] += 1
            
            # Submit to execution engine
            order = consumer.consume_signal(signal, execution_engine)
            results["orders_created"].append(order)
            
            # Execute order if price provided
            if price_series is not None and price_index < len(price_series):
                if order.status.value == "accepted":
                    try:
                        fills = execution_engine.execute_order(
                            order,
                            price_series[price_index],
                            timestamp=signal.timestamp
                        )
                        results["orders_executed"].extend(fills)
                    except Exception as e:
                        results["errors"].append(f"Failed to execute order {order.id}: {e}")
                price_index += 1
            
        except (InvalidSignalError, RiskCheckError) as e:
            results["errors"].append(f"Signal adaptation failed: {e}")
        except Exception as e:
            results["errors"].append(f"Unexpected error processing signal: {e}")
    
    return results

