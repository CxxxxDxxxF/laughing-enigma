
import unittest
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# We anticipate the new API structure
from src.analysis.regime import calculate_regime, RegimeResult, RegimeStatus

class TestRegimeHardening(unittest.TestCase):
    
    def setUp(self):
        self.dates = pd.date_range(start="2025-01-01", periods=100, freq="h")
        self.df_base = pd.DataFrame({
            'high': np.linspace(100, 200, 100) + 1,
            'low': np.linspace(100, 200, 100) - 1,
            'close': np.linspace(100, 200, 100)
        }, index=self.dates)

    def test_missing_columns(self):
        """Test missing required columns triggers DATA_INVALID."""
        df = self.df_base.drop(columns=['high'])
        result = calculate_regime(df)
        self.assertEqual(result.status, RegimeStatus.DATA_INVALID)
        self.assertTrue(result.is_chop) # Fail safe
        self.assertIn("columns", result.reason.lower())

    def test_insufficient_history(self):
        """Test len < warmup triggers INSUFFICIENT_HISTORY."""
        df = self.df_base.iloc[:20] # Less than 28 (14*2)
        result = calculate_regime(df)
        self.assertEqual(result.status, RegimeStatus.INSUFFICIENT_HISTORY)
        self.assertTrue(result.is_chop)

    def test_nan_handling(self):
        """Test NaNs in critical columns triggers DATA_INVALID."""
        df = self.df_base.copy()
        df.iloc[-1, df.columns.get_loc('close')] = np.nan
        result = calculate_regime(df)
        self.assertEqual(result.status, RegimeStatus.DATA_INVALID)
        self.assertTrue(result.is_chop)

    def test_non_monotonic_index(self):
        """Test scrambled index triggers DATA_INVALID."""
        df = self.df_base.copy()
        # Force non-monotonicity
        dates = list(df.index)
        dates[50] = dates[0] - timedelta(days=1) # Put a past date in middle
        df.index = dates
        
        result = calculate_regime(df)
        self.assertEqual(result.status, RegimeStatus.DATA_INVALID)

    def test_hysteresis_blocks_single_outlier(self):
        """Test that median logic ignores a single outlier drop."""
        from unittest.mock import patch
        
        # We mock calculate_adx to return a known series
        with patch('src.analysis.regime.calculate_adx') as mock_adx:
            # Helper to return correctly indexed series
            def side_effect(df, period):
                vals = np.full(len(df), 35.0)
                # Create dip at -2 (middle of 3-period window: -1, -2, -3)
                vals[-2] = 20.0 
                return pd.Series(vals, index=df.index)
            
            mock_adx.side_effect = side_effect
            
            # Use confirmation_window=3
            result = calculate_regime(self.df_base, confirmation_window=3, threshold=30)
            
            # Median of [35, 20, 35] is 35.0 > 30.0
            self.assertFalse(result.is_chop, "Hysteresis failed to ignore outlier dip")
            self.assertAlmostEqual(result.adx, 35.0)

    def test_flat_market_triggers_chop(self):
        """Test completely flat market returns valid CHOP (not error)."""
        df = self.df_base.copy()
        df['close'] = 100.0
        df['high'] = 100.0
        df['low'] = 100.0
        # This gives TR=0. 
        # Division by zero protection in calculate_adx should handle this.
        # Should result in ADX=0 -> Chop.
        
        result = calculate_regime(df)
        self.assertEqual(result.status, RegimeStatus.OK)
        self.assertTrue(result.is_chop)
        self.assertEqual(result.adx, 0.0) 
 

    def test_valid_trend(self):
        """Test valid trending data returns OK and TRENDING."""
        result = calculate_regime(self.df_base)
        self.assertEqual(result.status, RegimeStatus.OK)
        self.assertFalse(result.is_chop)
        self.assertGreater(result.adx, 30)

    def test_data_invalid_reason(self):
        """Ensure failure reason is populated."""
        df = pd.DataFrame()
        result = calculate_regime(df)
        self.assertEqual(result.status, RegimeStatus.DATA_INVALID)
        self.assertTrue(len(result.reason) > 0)

if __name__ == '__main__':
    unittest.main()
