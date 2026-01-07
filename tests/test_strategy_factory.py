"""Test for Strategy Factory."""
from unittest import TestCase
from src.strategy.factory import StrategyFactory, Strategy

class MockStrategy(Strategy):
    def __init__(self, param1):
        self.param1 = param1
        
    def generate_signals(self, market_data):
        return "signal"

class TestStrategyFactory(TestCase):
    def test_register_and_create(self):
        """Test registration and creation of strategy."""
        StrategyFactory.register("mock", MockStrategy)
        
        config = {"param1": "value1"}
        strategy = StrategyFactory.create("mock", config)
        
        self.assertIsInstance(strategy, MockStrategy)
        self.assertEqual(strategy.param1, "value1")
        
    def test_create_unknown_strategy(self):
        """Test error when creating unknown strategy."""
        with self.assertRaises(ValueError):
            StrategyFactory.create("unknown", {})
