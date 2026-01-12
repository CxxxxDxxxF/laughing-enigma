"""DuckDB-based state persistence layer.

Provides a lightweight embedded database for portfolio state management,
replacing JSON file artifacts for critical state.
"""

import duckdb
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import json


class DuckDBStateStore:
    """Persistent state store using DuckDB.
    
    Stores portfolio states in a local DuckDB database for fast queries
    and reliable persistence.
    """
    
    def __init__(self, db_path: str = "data/state.duckdb"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.db_path))
        self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_states (
                id VARCHAR PRIMARY KEY,
                portfolio_id VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                total_capital DOUBLE,
                cash_balance DOUBLE,
                positions JSON,
                metadata JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cycle_results (
                cycle_id VARCHAR PRIMARY KEY,
                portfolio_id VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                status VARCHAR,
                state_before_id VARCHAR,
                state_after_id VARCHAR,
                violations JSON,
                metadata JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for common queries
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_states_portfolio 
            ON portfolio_states(portfolio_id, timestamp DESC)
        """)
    
    def save_state(
        self,
        state_id: str,
        portfolio_id: str,
        timestamp: datetime,
        total_capital: float,
        cash_balance: float,
        positions: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Save portfolio state to database."""
        self.conn.execute("""
            INSERT OR REPLACE INTO portfolio_states 
            (id, portfolio_id, timestamp, total_capital, cash_balance, positions, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            state_id,
            portfolio_id,
            timestamp,
            total_capital,
            cash_balance,
            json.dumps(positions),
            json.dumps(metadata or {})
        ])
    
    def load_latest_state(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        """Load the most recent state for a portfolio."""
        result = self.conn.execute("""
            SELECT id, timestamp, total_capital, cash_balance, positions, metadata
            FROM portfolio_states
            WHERE portfolio_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, [portfolio_id]).fetchone()
        
        if result is None:
            return None
        
        return {
            "id": result[0],
            "timestamp": result[1],
            "total_capital": result[2],
            "cash_balance": result[3],
            "positions": json.loads(result[4]) if result[4] else {},
            "metadata": json.loads(result[5]) if result[5] else {}
        }
    
    def save_cycle_result(
        self,
        cycle_id: str,
        portfolio_id: str,
        timestamp: datetime,
        status: str,
        state_before_id: Optional[str] = None,
        state_after_id: Optional[str] = None,
        violations: Optional[list] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Save cycle execution result."""
        self.conn.execute("""
            INSERT OR REPLACE INTO cycle_results
            (cycle_id, portfolio_id, timestamp, status, state_before_id, state_after_id, violations, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            cycle_id,
            portfolio_id,
            timestamp,
            status,
            state_before_id,
            state_after_id,
            json.dumps(violations or []),
            json.dumps(metadata or {})
        ])
    
    def get_recent_cycles(self, portfolio_id: str, limit: int = 10) -> list:
        """Get recent cycle results for a portfolio."""
        results = self.conn.execute("""
            SELECT cycle_id, timestamp, status, state_before_id, state_after_id, violations
            FROM cycle_results
            WHERE portfolio_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, [portfolio_id, limit]).fetchall()
        
        return [
            {
                "cycle_id": r[0],
                "timestamp": r[1],
                "status": r[2],
                "state_before_id": r[3],
                "state_after_id": r[4],
                "violations": json.loads(r[5]) if r[5] else []
            }
            for r in results
        ]
    
    def close(self):
        """Close database connection."""
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
