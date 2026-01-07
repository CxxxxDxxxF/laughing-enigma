import sys
import shutil
import json
import subprocess
from pathlib import Path
from datetime import datetime, date

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.artifacts import LocalArtifactStore
from src.lifecycle.state_store import LocalPortfolioStateStore
from src.lifecycle.runner import HaltFlagStore
from src.rebalance.planner import CurrentPortfolioState
from src.rules.drawdown import DrawdownTracker

def setup_test_env(portfolio_id: str):
    """Setup a temporary test environment with artifacts."""
    artifacts_dir = Path(f"./artifacts_test_dashboard_{portfolio_id}")
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    artifact_store = LocalArtifactStore(artifacts_dir)
    state_store = LocalPortfolioStateStore(artifact_store)
    
    # Create a state
    ts = datetime(2024, 1, 1, 12, 0, 0)
    tracker = DrawdownTracker(initial_balance=100000.0, trading_date=date(2024, 1, 1))
    tracker.update(equity=105000.0, realized_pnl=5000.0, unrealized_pnl=0.0, timestamp=ts)
    
    state = CurrentPortfolioState(
        strategy_allocations={"strat1": 50000.0},
        total_capital=105000.0,
        timestamp=ts,
        drawdown_tracker=tracker,
        positions_by_instrument={
            "AAPL": {"quantity": 10.0, "cost_basis": 150.0}
        },
        metadata={"test": "true"}
    )
    
    state_store.save_state(portfolio_id, state, state_id="state_1_after")
    
    return artifacts_dir

def run_dashboard(command: str, portfolio_id: str, artifacts_dir: Path):
    """Run dashboard CLI command and return output."""
    cmd = [
        sys.executable,
        "scripts/dashboard.py",
        "--portfolio", portfolio_id,
        "--artifacts", str(artifacts_dir),
        command
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout, result.stderr, result.returncode

def test_dashboard_status():
    """Test 'status' command."""
    pid = "test_status"
    artifacts_dir = setup_test_env(pid)
    
    # 1. Normal status
    stdout, stderr, code = run_dashboard("status", pid, artifacts_dir)
    assert code == 0
    assert "System Running" in stdout
    assert "Total Capital: $105,000.00" in stdout
    
    # 2. Halted status
    halt_store = HaltFlagStore(LocalArtifactStore(artifacts_dir))
    halt_store.write_halt_flag(pid, "test_cycle", "Test Halt", datetime.now(), [])
    
    stdout, stderr, code = run_dashboard("status", pid, artifacts_dir)
    assert code == 0
    assert "SYSTEM HALTED" in stdout
    assert "Reason: Test Halt" in stdout
    
    shutil.rmtree(artifacts_dir)

def test_dashboard_metrics():
    """Test 'metrics' command."""
    pid = "test_metrics"
    artifacts_dir = setup_test_env(pid)
    
    stdout, stderr, code = run_dashboard("metrics", pid, artifacts_dir)
    assert code == 0
    assert "Equity: $105,000.00" in stdout
    # Daily PnL = Equity(105k) - Initial(100k) = 5000
    assert "Daily PnL: $5,000.00" in stdout
    assert "Realized PnL: $5,000.00" in stdout
    
    shutil.rmtree(artifacts_dir)

def test_dashboard_positions():
    """Test 'positions' command."""
    pid = "test_positions"
    artifacts_dir = setup_test_env(pid)
    
    stdout, stderr, code = run_dashboard("positions", pid, artifacts_dir)
    assert code == 0
    assert "AAPL" in stdout
    assert "10.00" in stdout # Qty
    assert "$150.00" in stdout # Cost
    
    shutil.rmtree(artifacts_dir)

if __name__ == "__main__":
    print("Running Dashboard CLI Tests...")
    try:
        test_dashboard_status()
        print("  [x] Status Command Passed")
        test_dashboard_metrics()
        print("  [x] Metrics Command Passed")
        test_dashboard_positions()
        print("  [x] Positions Command Passed")
        print("\nAll tests passed!")
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
