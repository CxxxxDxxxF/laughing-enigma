"""API layer for backtest control plane.

This module defines the API endpoints for experiment management,
run execution, and metrics/artifact retrieval.
"""

import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, status, Query
from pydantic import BaseModel, Field

from ..core import Experiment, Run, RunStatus, Metrics, LocalArtifactStore, MetricsError
from ..engines import SimpleResearchEngine, BacktestError
from ..execution import (
    PaperExecutionEngine, Signal, SignalType, Order, Fill, Position,
    RiskLimits, ExecutionEngineError, OrderRejectionError
)


# Request/Response Models
class CreateExperimentRequest(BaseModel):
    """Request model for creating an experiment."""
    name: str = Field(..., description="Unique experiment identifier")
    version: str = Field(..., description="Version string for this experiment")
    config: Dict[str, Any] = Field(..., description="Experiment configuration")
    description: Optional[str] = Field(None, description="Optional description")


class ExperimentResponse(BaseModel):
    """Response model for experiment data."""
    name: str
    version: str
    config: Dict[str, Any]
    created_at: str
    description: Optional[str] = None

    @classmethod
    def from_experiment(cls, experiment: Experiment) -> 'ExperimentResponse':
        """Create response from Experiment domain object."""
        return cls(
            name=experiment.name,
            version=experiment.version,
            config=experiment.config,
            created_at=experiment.created_at.isoformat(),
            description=experiment.description,
        )


class RunBacktestRequest(BaseModel):
    """Request model for running a backtest."""
    experiment_name: str = Field(..., description="Experiment name")
    experiment_version: str = Field(..., description="Experiment version")
    inputs: Dict[str, Any] = Field(..., description="Backtest inputs (start_date, end_date, etc.)")


class RunResponse(BaseModel):
    """Response model for run data."""
    id: str
    experiment_name: str
    experiment_version: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class MetricsResponse(BaseModel):
    """Response model for metrics data."""
    run_id: str
    computed_at: str
    equity_curve: List[float]
    final_value: float
    max_drawdown: float
    max_drawdown_duration: int
    monthly_returns: List[float]
    total_return: float
    sharpe_ratio: float
    volatility: float
    turnover: float

    @classmethod
    def from_metrics(cls, metrics: Metrics) -> 'MetricsResponse':
        """Create response from Metrics domain object."""
        return cls(
            run_id=metrics.run_id,
            computed_at=metrics.computed_at.isoformat(),
            equity_curve=metrics.equity_curve,
            final_value=metrics.final_value,
            max_drawdown=metrics.max_drawdown,
            max_drawdown_duration=metrics.max_drawdown_duration,
            monthly_returns=metrics.monthly_returns,
            total_return=metrics.total_return,
            sharpe_ratio=metrics.sharpe_ratio,
            volatility=metrics.volatility,
            turnover=metrics.turnover,
        )


# Global application state (simple in-memory store for Phase 1)
# In production, this would be replaced with a database
_experiment_registry: Dict[tuple[str, str], Experiment] = {}
_artifact_store: Optional[LocalArtifactStore] = None
_engine: Optional[SimpleResearchEngine] = None

# Paper trading sessions (session_id -> PaperExecutionEngine)
_paper_sessions: Dict[str, PaperExecutionEngine] = {}


def get_artifact_store() -> LocalArtifactStore:
    """Get or create artifact store."""
    global _artifact_store
    if _artifact_store is None:
        # Default to ./artifacts directory
        base_path = Path("./artifacts")
        _artifact_store = LocalArtifactStore(base_path)
    return _artifact_store


def get_engine() -> SimpleResearchEngine:
    """Get or create research engine."""
    global _engine
    if _engine is None:
        _engine = SimpleResearchEngine(artifact_store=get_artifact_store())
    return _engine


# FastAPI app
app = FastAPI(
    title="Backtest Control Plane API",
    description="Phase 1 API for quant research and backtesting",
    version="1.0.0"
)


@app.post("/experiments", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
def create_experiment(request: CreateExperimentRequest) -> ExperimentResponse:
    """Create a new experiment.
    
    Args:
        request: Experiment creation request
        
    Returns:
        Created experiment data
        
    Raises:
        HTTPException: If experiment already exists
    """
    key = (request.name, request.version)
    
    if key in _experiment_registry:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Experiment {request.name} version {request.version} already exists"
        )
    
    experiment = Experiment(
        name=request.name,
        version=request.version,
        config=request.config,
        created_at=datetime.now(),
        description=request.description,
    )
    
    _experiment_registry[key] = experiment
    
    return ExperimentResponse.from_experiment(experiment)


@app.get("/experiments", response_model=List[ExperimentResponse])
def list_experiments() -> List[ExperimentResponse]:
    """List all experiments.
    
    Returns:
        List of all experiments
    """
    return [
        ExperimentResponse.from_experiment(exp)
        for exp in _experiment_registry.values()
    ]


@app.get("/experiments/{name}/{version}", response_model=ExperimentResponse)
def get_experiment(name: str, version: str) -> ExperimentResponse:
    """Get a specific experiment.
    
    Args:
        name: Experiment name
        version: Experiment version
        
    Returns:
        Experiment data
        
    Raises:
        HTTPException: If experiment not found
    """
    key = (name, version)
    experiment = _experiment_registry.get(key)
    
    if experiment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {name} version {version} not found"
        )
    
    return ExperimentResponse.from_experiment(experiment)


@app.post("/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
def run_backtest(request: RunBacktestRequest) -> RunResponse:
    """Run a backtest.
    
    Args:
        request: Backtest run request
        
    Returns:
        Run data with status
        
    Raises:
        HTTPException: If experiment not found or backtest fails
    """
    # Get experiment
    key = (request.experiment_name, request.experiment_version)
    experiment = _experiment_registry.get(key)
    
    if experiment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {request.experiment_name} version {request.experiment_version} not found"
        )
    
    # Generate run ID
    run_id = str(uuid.uuid4())
    started_at = datetime.now()
    
    try:
        # Execute backtest (synchronous, no async)
        engine = get_engine()
        result = engine.run_backtest(experiment, run_id, request.inputs)
        
        # Create run record
        run = Run(
            id=run_id,
            experiment=experiment,
            status=RunStatus.SUCCESS,
            started_at=started_at,
            completed_at=datetime.now(),
            inputs_hash=engine.compute_inputs_hash(request.inputs),
        )
        
        return RunResponse(
            id=run.id,
            experiment_name=run.experiment.name,
            experiment_version=run.experiment.version,
            status=run.status.value,
            started_at=run.started_at.isoformat(),
            completed_at=run.completed_at.isoformat() if run.completed_at else None,
            error_message=run.error_message,
        )
        
    except BacktestError as e:
        # Backtest execution failed
        run = Run(
            id=run_id,
            experiment=experiment,
            status=RunStatus.FAILED,
            started_at=started_at,
            completed_at=datetime.now(),
            error_message=str(e),
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Backtest failed: {e}"
        )
    except Exception as e:
        # Unexpected error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {e}"
        )


@app.get("/runs", response_model=List[RunResponse])
def list_runs() -> List[RunResponse]:
    """List all runs.
    
    Scans artifact store for run directories and loads run metadata.
    
    Returns:
        List of all runs with their status
    """
    artifact_store = get_artifact_store()
    runs = []
    
    # Scan artifact store for run directories
    runs_dir = artifact_store.base_path / "runs"
    
    if not runs_dir.exists():
        return []
    
    try:
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            
            run_id = run_dir.name
            
            # Try to load run metadata
            metadata_data = artifact_store.retrieve(run_id, "run_metadata.json")
            if metadata_data is None:
                # Skip runs without metadata
                continue
            
            try:
                metadata = json.loads(metadata_data.decode('utf-8'))
                
                # Try to determine status from metrics existence
                metrics_data = artifact_store.retrieve(run_id, "metrics.json")
                if metrics_data:
                    status = RunStatus.SUCCESS.value
                else:
                    status = RunStatus.FAILED.value
                
                # Try to get start/completion times from metadata or use defaults
                started_at = datetime.now().isoformat()  # Default if not available
                
                runs.append(RunResponse(
                    id=run_id,
                    experiment_name=metadata.get("experiment", {}).get("name", "unknown"),
                    experiment_version=metadata.get("experiment", {}).get("version", "unknown"),
                    status=status,
                    started_at=started_at,
                    completed_at=None,
                    error_message=None,
                ))
            except (json.JSONDecodeError, KeyError):
                # Skip runs with invalid metadata
                continue
                
    except Exception as e:
        # If listing fails, return empty list (don't fail the endpoint)
        pass
    
    return runs


@app.get("/runs/{run_id}/metrics", response_model=MetricsResponse)
def get_metrics(run_id: str) -> MetricsResponse:
    """Get metrics for a completed run.
    
    Args:
        run_id: Run identifier
        
    Returns:
        Metrics data
        
    Raises:
        HTTPException: If run not found or metrics cannot be loaded
    """
    artifact_store = get_artifact_store()
    
    # Try to load metrics from artifacts
    metrics_data = artifact_store.retrieve(run_id, "metrics.json")
    
    if metrics_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metrics for run {run_id} not found. Run may not exist or may not have completed successfully."
        )
    
    try:
        # Deserialize metrics from JSON
        metrics_dict = json.loads(metrics_data.decode('utf-8'))
        metrics = Metrics.from_dict(metrics_dict)
        
        return MetricsResponse.from_metrics(metrics)
        
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse metrics for run {run_id}: {e}"
        )
    except MetricsError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid metrics data for run {run_id}: {e}"
        )


@app.get("/runs/{run_id}/artifacts")
def list_artifacts(run_id: str) -> Dict[str, List[str]]:
    """List artifacts for a run.
    
    Args:
        run_id: Run identifier
        
    Returns:
        List of artifact names
        
    Raises:
        HTTPException: If artifacts cannot be listed
    """
    artifact_store = get_artifact_store()
    
    try:
        artifacts = artifact_store.list_artifacts(run_id)
        return {"artifacts": artifacts}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list artifacts for run {run_id}: {e}"
        )


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


# Paper Trading API Models
class CreatePaperSessionRequest(BaseModel):
    """Request model for creating a paper trading session."""
    instrument: str = Field(..., description="Instrument to trade")
    max_position_size: Optional[float] = Field(None, description="Max position size")
    max_daily_loss: Optional[float] = Field(None, description="Max daily loss (negative number)")
    max_leverage: float = Field(1.0, description="Max leverage")
    allowed_instruments: Optional[List[str]] = Field(None, description="Allowed instruments")
    fixed_fee: float = Field(0.0, description="Fixed fee per fill")


class PaperSessionResponse(BaseModel):
    """Response model for paper trading session."""
    session_id: str
    instrument: str
    fixed_fee: float


class SubmitSignalRequest(BaseModel):
    """Request model for submitting a signal."""
    session_id: str = Field(..., description="Paper trading session ID")
    instrument: str = Field(..., description="Instrument identifier")
    signal_type: str = Field(..., description="Signal type: buy, sell, or hold")
    quantity: float = Field(..., description="Quantity")
    timestamp: Optional[str] = Field(None, description="Signal timestamp (ISO format)")


class OrderResponse(BaseModel):
    """Response model for order data."""
    id: str
    signal_id: Optional[str]
    instrument: str
    order_type: str
    side: str
    quantity: float
    price_limit: Optional[float]
    status: str
    created_at: str
    accepted_at: Optional[str]
    filled_at: Optional[str]
    canceled_at: Optional[str]
    rejection_reason: Optional[str]


class ExecuteOrderRequest(BaseModel):
    """Request model for executing an order."""
    session_id: str = Field(..., description="Paper trading session ID")
    current_price: float = Field(..., description="Current market price")
    timestamp: Optional[str] = Field(None, description="Execution timestamp (ISO format)")


class FillResponse(BaseModel):
    """Response model for fill data."""
    id: str
    order_id: str
    instrument: str
    side: str
    quantity: float
    price: float
    fee: float
    filled_at: str
    execution_id: Optional[str]


class PositionResponse(BaseModel):
    """Response model for position data."""
    instrument: str
    quantity: float
    cost_basis: float
    realized_pnl: float
    updated_at: str


# Paper Trading API Endpoints
@app.post("/paper/sessions", response_model=PaperSessionResponse, status_code=status.HTTP_201_CREATED)
def create_paper_session(request: CreatePaperSessionRequest) -> PaperSessionResponse:
    """Create a new paper trading session.
    
    Args:
        request: Session creation request
        
    Returns:
        Created session data
        
    Raises:
        HTTPException: If session creation fails
    """
    try:
        # Create risk limits
        risk_limits = RiskLimits(
            max_position_size=request.max_position_size,
            max_daily_loss=request.max_daily_loss,
            max_leverage=request.max_leverage,
            allowed_instruments=request.allowed_instruments
        )
        
        # Create engine
        artifact_store = get_artifact_store()
        engine = PaperExecutionEngine(
            instrument=request.instrument,
            risk_limits=risk_limits,
            fixed_fee=request.fixed_fee,
            artifact_store=artifact_store
        )
        
        # Persist session
        engine.persist_session()
        
        # Store in memory
        _paper_sessions[engine.session_id] = engine
        
        return PaperSessionResponse(
            session_id=engine.session_id,
            instrument=engine.instrument,
            fixed_fee=engine.fixed_fee
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create paper session: {e}"
        )


@app.post("/paper/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def submit_paper_order(request: SubmitSignalRequest) -> OrderResponse:
    """Submit a signal as an order in a paper trading session.
    
    Args:
        request: Signal submission request
        
    Returns:
        Created order data
        
    Raises:
        HTTPException: If session not found or order submission fails
    """
    # Get or load session
    engine = _paper_sessions.get(request.session_id)
    if engine is None:
        # Try to load from artifacts
        try:
            artifact_store = get_artifact_store()
            engine = PaperExecutionEngine.load_session(request.session_id, artifact_store)
            _paper_sessions[request.session_id] = engine
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Paper session {request.session_id} not found: {e}"
            )
    
    try:
        # Create signal
        signal_type_map = {
            "buy": SignalType.BUY,
            "sell": SignalType.SELL,
            "hold": SignalType.HOLD,
        }
        signal_type = signal_type_map.get(request.signal_type.lower())
        if signal_type is None:
            raise ValueError(f"Invalid signal_type: {request.signal_type}")
        
        signal_timestamp = datetime.now()
        if request.timestamp:
            signal_timestamp = datetime.fromisoformat(request.timestamp)
        
        signal = Signal(
            timestamp=signal_timestamp,
            instrument=request.instrument,
            signal_type=signal_type,
            quantity=request.quantity
        )
        
        # Submit order
        order = engine.submit_order(signal)
        
        return OrderResponse(
            id=order.id,
            signal_id=order.signal_id,
            instrument=order.instrument,
            order_type=order.order_type.value,
            side=order.side,
            quantity=order.quantity,
            price_limit=order.price_limit,
            status=order.status.value,
            created_at=order.created_at.isoformat() if order.created_at else "",
            accepted_at=order.accepted_at.isoformat() if order.accepted_at else None,
            filled_at=order.filled_at.isoformat() if order.filled_at else None,
            canceled_at=order.canceled_at.isoformat() if order.canceled_at else None,
            rejection_reason=order.rejection_reason
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to submit order: {e}"
        )


@app.post("/paper/orders/{order_id}/execute", response_model=List[FillResponse], status_code=status.HTTP_200_OK)
def execute_paper_order(
    order_id: str,
    request: ExecuteOrderRequest
) -> List[FillResponse]:
    """Execute an order at a given price and timestamp.
    
    Args:
        order_id: Order identifier
        request: Execution request with price and timestamp
        
    Returns:
        List of fills (usually single fill for immediate execution)
        
    Raises:
        HTTPException: If session not found, order not found, or execution fails
    """
    # Get or load session
    engine = _paper_sessions.get(request.session_id)
    if engine is None:
        try:
            artifact_store = get_artifact_store()
            engine = PaperExecutionEngine.load_session(request.session_id, artifact_store)
            _paper_sessions[request.session_id] = engine
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Paper session {request.session_id} not found: {e}"
            )
    
    # Get order
    order = engine.get_order(order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found in session {request.session_id}"
        )
    
    try:
        # Execute order
        execution_timestamp = None
        if request.timestamp:
            execution_timestamp = datetime.fromisoformat(request.timestamp)
        
        fills = engine.execute_order(order, request.current_price, execution_timestamp)
        
        return [
            FillResponse(
                id=fill.id,
                order_id=fill.order_id,
                instrument=fill.instrument,
                side=fill.side,
                quantity=fill.quantity,
                price=fill.price,
                fee=fill.fee,
                filled_at=fill.filled_at.isoformat() if fill.filled_at else "",
                execution_id=fill.execution_id
            )
            for fill in fills
        ]
        
    except OrderRejectionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order execution rejected: {e}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute order: {e}"
        )


@app.get("/paper/orders", response_model=List[OrderResponse])
def list_paper_orders(
    session_id: str = Query(..., description="Paper trading session ID"),
    instrument: Optional[str] = Query(None, description="Filter by instrument"),
    status: Optional[str] = Query(None, description="Filter by status")
) -> List[OrderResponse]:
    """List orders for a paper trading session.
    
    Args:
        session_id: Paper trading session ID
        instrument: Optional filter by instrument
        status: Optional filter by status
        
    Returns:
        List of orders
        
    Raises:
        HTTPException: If session not found
    """
    # Get or load session
    engine = _paper_sessions.get(session_id)
    if engine is None:
        try:
            artifact_store = get_artifact_store()
            engine = PaperExecutionEngine.load_session(session_id, artifact_store)
            _paper_sessions[session_id] = engine
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Paper session {session_id} not found: {e}"
            )
    
    orders = engine.list_orders(instrument=instrument, status=status)
    
    return [
        OrderResponse(
            id=order.id,
            signal_id=order.signal_id,
            instrument=order.instrument,
            order_type=order.order_type.value,
            side=order.side,
            quantity=order.quantity,
            price_limit=order.price_limit,
            status=order.status.value,
            created_at=order.created_at.isoformat() if order.created_at else "",
            accepted_at=order.accepted_at.isoformat() if order.accepted_at else None,
            filled_at=order.filled_at.isoformat() if order.filled_at else None,
            canceled_at=order.canceled_at.isoformat() if order.canceled_at else None,
            rejection_reason=order.rejection_reason
        )
        for order in orders
    ]


@app.get("/paper/orders/{order_id}", response_model=OrderResponse)
def get_paper_order(
    order_id: str,
    session_id: str = Query(..., description="Paper trading session ID")
) -> OrderResponse:
    """Get a specific order.
    
    Args:
        session_id: Paper trading session ID
        order_id: Order identifier
        
    Returns:
        Order data
        
    Raises:
        HTTPException: If session or order not found
    """
    # Get or load session
    engine = _paper_sessions.get(session_id)
    if engine is None:
        try:
            artifact_store = get_artifact_store()
            engine = PaperExecutionEngine.load_session(session_id, artifact_store)
            _paper_sessions[session_id] = engine
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Paper session {session_id} not found: {e}"
            )
    
    order = engine.get_order(order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found in session {session_id}"
        )
    
    return OrderResponse(
        id=order.id,
        signal_id=order.signal_id,
        instrument=order.instrument,
        order_type=order.order_type.value,
        side=order.side,
        quantity=order.quantity,
        price_limit=order.price_limit,
        status=order.status.value,
        created_at=order.created_at.isoformat() if order.created_at else "",
        accepted_at=order.accepted_at.isoformat() if order.accepted_at else None,
        filled_at=order.filled_at.isoformat() if order.filled_at else None,
        canceled_at=order.canceled_at.isoformat() if order.canceled_at else None,
        rejection_reason=order.rejection_reason
    )


@app.get("/paper/fills", response_model=List[FillResponse])
def list_paper_fills(
    session_id: str = Query(..., description="Paper trading session ID"),
    order_id: Optional[str] = Query(None, description="Filter by order ID")
) -> List[FillResponse]:
    """List fills for a paper trading session.
    
    Args:
        session_id: Paper trading session ID
        order_id: Optional filter by order ID
        
    Returns:
        List of fills
        
    Raises:
        HTTPException: If session not found
    """
    # Get or load session
    engine = _paper_sessions.get(session_id)
    if engine is None:
        try:
            artifact_store = get_artifact_store()
            engine = PaperExecutionEngine.load_session(session_id, artifact_store)
            _paper_sessions[session_id] = engine
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Paper session {session_id} not found: {e}"
            )
    
    if order_id:
        fills = engine.get_fills(order_id)
    else:
        # Get all fills
        all_fills = []
        for oid in engine.orders.keys():
            all_fills.extend(engine.get_fills(oid))
        fills = all_fills
    
    return [
        FillResponse(
            id=fill.id,
            order_id=fill.order_id,
            instrument=fill.instrument,
            side=fill.side,
            quantity=fill.quantity,
            price=fill.price,
            fee=fill.fee,
            filled_at=fill.filled_at.isoformat() if fill.filled_at else "",
            execution_id=fill.execution_id
        )
        for fill in fills
    ]


@app.get("/paper/positions", response_model=List[PositionResponse])
def list_paper_positions(
    session_id: str = Query(..., description="Paper trading session ID"),
    instrument: Optional[str] = Query(None, description="Filter by instrument")
) -> List[PositionResponse]:
    """List positions for a paper trading session.
    
    Args:
        session_id: Paper trading session ID
        instrument: Optional filter by instrument (if None, returns all positions)
        
    Returns:
        List of positions
        
    Raises:
        HTTPException: If session not found
    """
    # Get or load session
    engine = _paper_sessions.get(session_id)
    if engine is None:
        try:
            artifact_store = get_artifact_store()
            engine = PaperExecutionEngine.load_session(session_id, artifact_store)
            _paper_sessions[session_id] = engine
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Paper session {session_id} not found: {e}"
            )
    
    if instrument:
        positions = [engine.get_position(instrument)]
    else:
        # Return all positions (including flat ones)
        positions = list(engine.positions.values())
    
    return [
        PositionResponse(
            instrument=position.instrument,
            quantity=position.quantity,
            cost_basis=position.cost_basis,
            realized_pnl=position.realized_pnl,
            updated_at=position.updated_at.isoformat() if position.updated_at else ""
        )
        for position in positions
    ]
