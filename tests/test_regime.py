
import unittest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.analysis.regime import calculate_adx, calculate_regime

class TestRegimeDetection(unittest.TestCase):
    def setUp(self):
        # Create 50 periods of data
        self.index = pd.date_range(start="2025-01-01", periods=50, freq="H")
        
    def test_trending_market(self):
        """Test ADX on a strong uptrend."""
        # Create a series where High/Low/Close increase consistently
        # This should result in high ADX
        close = np.linspace(100, 200, 50)
        high = close + 1
        low = close - 1
        
        df = pd.DataFrame({
            'high': high,
            'low': low,
            'close': close
        }, index=self.index)
        
        result = calculate_regime(df, threshold=30)
        adx = result.adx
        is_chop = result.is_chop
        
        print(f"\n[Trending] ADX: {adx:.2f}, Is Chop: {is_chop}")
        
        # After 50 periods of pure trend, ADX should be extremely high (near 100)
        self.assertGreater(adx, 50)
        self.assertFalse(is_chop)

    def test_choppy_market(self):
        """Test ADX on sideways chop."""
        np.random.seed(42)
        # Random noise around 100
        close = np.random.normal(100, 2, 50)
        high = close + 2
        low = close - 2
        
        df = pd.DataFrame({
            'high': high,
            'low': low,
            'close': close
        }, index=self.index)
        
        result = calculate_regime(df, threshold=30)
        adx = result.adx
        is_chop = result.is_chop
        
        print(f"\n[Chop] ADX: {adx:.2f}, Is Chop: {is_chop}")
        
        # Random noise usually results in low ADX
        self.assertLess(adx, 30)
        self.assertTrue(is_chop)

    def test_empty_dataframe(self):
        """Test gracefull handling of empty DF."""
        df = pd.DataFrame()
        result = calculate_regime(df)
        adx = result.adx
        is_chop = result.is_chop
        self.assertEqual(adx, 0.0)
        self.assertTrue(is_chop)

if __name__ == '__main__':
    unittest.main()
