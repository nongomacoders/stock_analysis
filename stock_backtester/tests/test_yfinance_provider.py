import unittest
import pandas as pd
import yfinance as yf
from datetime import datetime
import os
import sys

# Add the project root to the Python path to allow for correct module imports
# This makes the test script runnable from any directory
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from data.yfinance_provider import YFinanceProvider

class TestYFinanceProviderIntegration(unittest.TestCase):
    """
    Integration test suite for the YFinanceProvider class.
    These tests require an active internet connection to interact with the yfinance API.
    """

    def setUp(self):
        """Set up common variables for the tests."""
        self.start_date = '2023-01-03'
        self.end_date = '2023-01-10'

    def test_initialization_and_data_loading(self):
        """Test that the class initializes and loads real data correctly."""
        provider = YFinanceProvider(['AAPL', 'GOOG'], self.start_date, self.end_date)
        self.assertIsNotNone(provider._data)
        self.assertFalse(provider._data.empty)
        # Check that data for both symbols is present
        self.assertIn('AAPL', provider._data['symbol'].unique())
        self.assertIn('GOOG', provider._data['symbol'].unique())
        
    def test_data_standardization(self):
        """Test if the downloaded DataFrame is standardized to the expected format."""
        provider = YFinanceProvider(['AAPL', 'GOOG'], self.start_date, self.end_date)
        df = provider._data
        expected_columns = ['symbol', 'open', 'high', 'low', 'close', 'adj_close', 'volume']
        self.assertListEqual(list(df.columns), expected_columns)
        self.assertTrue(isinstance(df.index, pd.DatetimeIndex))

    def test_stream_next_yields_chronologically(self):
        """Test the stream_next generator for correct structure and real data."""
        provider = YFinanceProvider(['AAPL', 'GOOG'], self.start_date, self.end_date)
        data_stream = provider.stream_next()
        
        first_day_data = next(data_stream)
        self.assertIsInstance(first_day_data, dict)
        self.assertIn('AAPL', first_day_data)
        self.assertIn('GOOG', first_day_data)
        # Verify the date is the start date
        self.assertEqual(provider.current_bar.name.date(), datetime(2023, 1, 3).date())

    def test_get_history_prevents_lookahead_bias(self):
        """Test that get_history returns the correct window of past data."""
        provider = YFinanceProvider(['AAPL', 'GOOG'], self.start_date, self.end_date)
        data_stream = provider.stream_next()
        
        # Before starting stream, get_history should return None
        self.assertIsNone(provider.get_history('AAPL', bars=5))
        
        # Consume first bar (2023-01-03)
        next(data_stream)
        
        history1 = provider.get_history('AAPL', bars=5)
        self.assertEqual(len(history1), 1)
        self.assertEqual(history1.index[0].date(), datetime(2023, 1, 3).date())
        
        # Consume second bar (2023-01-04)
        next(data_stream) 
        
        history2 = provider.get_history('AAPL', bars=2)
        self.assertEqual(len(history2), 2)
        self.assertEqual(history2.index[-1].date(), datetime(2023, 1, 4).date())

    def test_handles_invalid_symbol_gracefully(self):
        """Test that a single invalid symbol doesn't crash the provider."""
        provider = YFinanceProvider(['MSFT', 'THISISNOTAVALIDTICKER'], self.start_date, self.end_date)
        # The internal data should only contain the valid symbol
        self.assertListEqual(list(provider._data['symbol'].unique()), ['MSFT'])
        # Data for MSFT in this range should not be empty
        self.assertFalse(provider._data.empty)

    def test_raises_error_if_all_symbols_fail(self):
        """Test that a ValueError is raised if no data can be downloaded."""
        with self.assertRaises(ValueError):
            YFinanceProvider(['INVALIDTICKER1', 'INVALIDTICKER2'], self.start_date, self.end_date)


if __name__ == '__main__':
    # Create a TestSuite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestYFinanceProviderIntegration)
    # Run the tests and get the result object
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    # Check if the tests were successful and print a confirmation message
    if result.wasSuccessful():
        print("\nAll tests passed successfully!")

