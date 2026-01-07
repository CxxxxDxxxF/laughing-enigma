import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import json

from src.lifecycle.evidence import EvidenceBundle, generate_evidence_bundle, persist_evidence_bundle
from src.lifecycle.runner import CycleResult
from src.core.artifacts import LocalArtifactStore
from src.rebalance.planner import CurrentPortfolioState
from src.rules.drawdown import DrawdownTracker

class TestEvidenceBundle(unittest.TestCase):
    
    def test_bundle_serialization(self):
        """Test that EvidenceBundle serializes correctly."""
        bundle = EvidenceBundle(
            cycle_id="cycle_123",
            cycle_timestamp="2024-01-01T12:00:00",
            portfolio_id="test_port",
            allocations={"strat_A": 1000.0},
            market_data={"AAPL": 150.0},
            equity_before=10000.0,
            equity_after=10050.0
        )
        
        data = bundle.to_dict()
        self.assertEqual(data["cycle_id"], "cycle_123")
        self.assertEqual(data["allocations"]["strat_A"], 1000.0)
        self.assertEqual(data["equity_after"], 10050.0)
        
    def test_generate_evidence_bundle(self):
        """Test generation from CycleResult and Mock Store."""
        # Setup Mocks
        artifact_store = MagicMock()
        
        result = CycleResult(
            cycle_id="cycle_1",
            cycle_timestamp=datetime(2024, 1, 1),
            portfolio_id="test_p",
            evaluation_id="eval_1",
            allocation_id="alloc_1",
            rebalance_plan_id="plan_1",
            rebalance_execution_id="exec_1",
            state_before_id="state_0",
            state_after_id="state_1",
            summary={},
            status="completed",
            skip_reason=None
        )
        
        # Mock Allocation Artifact
        alloc_data = json.dumps({
            "allocations": [
                {"strategy_id": "strat_A", "allocated_capital": 5000.0}
            ]
        })
        artifact_store.retrieve.side_effect = lambda cid, name: alloc_data if name == "allocation.json" else None
        
        # Mock States
        tracker_before = DrawdownTracker(initial_balance=10000.0, trading_date=datetime(2023, 12, 31).date())
        tracker_before.high_water_mark = 10000.0
        state_before = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=10000.0,
            timestamp=datetime(2023, 12, 31),
            drawdown_tracker=tracker_before
        )
        
        tracker_after = DrawdownTracker(initial_balance=10000.0, trading_date=datetime(2024, 1, 1).date())
        tracker_after.high_water_mark = 10100.0
        state_after = CurrentPortfolioState(
            strategy_allocations={},
            total_capital=10100.0,
            timestamp=datetime(2024, 1, 1),
            drawdown_tracker=tracker_after
        )
        
        prices = {"AAPL": 155.0}
        
        bundle = generate_evidence_bundle(
            result, artifact_store, prices, state_before, state_after
        )
        
        self.assertEqual(bundle.cycle_id, "cycle_1")
        self.assertEqual(bundle.allocations["strat_A"], 5000.0)
        self.assertEqual(bundle.market_data["AAPL"], 155.0)
        self.assertEqual(bundle.equity_before, 10000.0)
        self.assertEqual(bundle.equity_after, 10100.0)
        self.assertEqual(bundle.hwm_before, 10000.0)
        self.assertEqual(bundle.hwm_after, 10100.0)
        
    @patch("src.lifecycle.evidence.json.dumps")
    def test_persist_evidence_bundle(self, mock_json_dumps):
        """Test persistence calls artifact store correctly."""
        bundle = EvidenceBundle(cycle_id="c1", cycle_timestamp="t1", portfolio_id="p1")
        mock_store = MagicMock()
        mock_json_dumps.return_value = "json_data"
        
        path = persist_evidence_bundle(bundle, mock_store)
        
        self.assertEqual(path, "c1/evidence.json")
        mock_store.store.assert_called_with("c1", "evidence.json", b"json_data")

if __name__ == '__main__':
    unittest.main()
