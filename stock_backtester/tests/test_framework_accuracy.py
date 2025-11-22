import unittest
import pandas as pd
import sys
import os
from typing import List, Dict, Generator, Optional

# --- Add the project root to the Python path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- Import all framework components ---
from data.yfinance_provider import BaseDataProvider
from strategy.strategy import Strategy
from portfolio.portfolio import Portfolio
from broker.broker import Broker
from engine.engine import BacktestEngine

# --- 1. A custom data provider for our synthetic data ---
class SyntheticDataProvider(BaseDataProvider):
    """A data provider that serves a predefined pandas DataFrame."""
    def __init__(self, data: pd.DataFrame):
        self._data = data
        self.symbols = list(data['symbol'].unique())
        self.current_bar = None
        self.current_bar_dict = {}

    def get_history(self, symbol: str, bars: int) -> Optional[pd.DataFrame]:
        if self.current_bar is None:
            return None
        symbol_data = self._data[self._data['symbol'] == symbol]
        current_timestamp = self.current_bar.name
        relevant_data = symbol_data.loc[:current_timestamp]
        return relevant_data.tail(bars)

    def get_latest_bar(self, symbol: str) -> Optional[pd.Series]:
        """Retrieves the most recent data bar available for a given symbol."""
        return self.current_bar_dict.get(symbol, None)

    def stream_next(self) -> Generator[Dict[str, pd.Series], None, None]:
        for timestamp, group in self._data.groupby(level=0):
            self.current_bar = group
            self.current_bar.name = timestamp
            self.current_bar_dict = {row['symbol']: row for _, row in group.iterrows()}
            yield self.current_bar_dict

# --- A simple strategy class for the test ---
class SmaCrossTest(Strategy):
    """Uses the same logic as the example SmaCross strategy."""
    short_window = None
    long_window = None

    def initialize(self):
        pass # No setup needed for this test

    def on_bar(self):
        symbol = self.data.symbols[0]
        history = self.data.get_history(symbol, bars=self.long_window + 1)
        
        if history is None or len(history) < self.long_window + 1:
            return

        sma_short = history['close'].rolling(window=self.short_window).mean()
        sma_long = history['close'].rolling(window=self.long_window).mean()

        if pd.isna(sma_long.iloc[-2]):
            return

        is_in_position = self.portfolio.positions.get(symbol, 0) > 0

        if sma_short.iloc[-1] > sma_long.iloc[-1] and sma_short.iloc[-2] <= sma_long.iloc[-2]:
            if not is_in_position:
                self.broker.buy(symbol=symbol, quantity=100)
        elif sma_short.iloc[-1] < sma_long.iloc[-1] and sma_short.iloc[-2] >= sma_long.iloc[-2]:
            if is_in_position:
                self.broker.close(symbol=symbol)

# --- The Main Accuracy Test Case ---
class TestFrameworkAccuracy(unittest.TestCase):
    def test_single_trade_accuracy(self):
        """
        Tests the entire framework with a synthetic dataset to verify that the
        final equity matches a manually calculated, known outcome.
        """
        # --- 2. Generate Synthetic Data ---
        # This data is now crafted to guarantee a crossover buy and sell signal.
        dates = pd.to_datetime([f'2023-01-{i:02d}' for i in range(1, 11)])
        # --- FIX: New price series to ensure a trade occurs ---
        close_prices = [100, 100, 100, 100, 95, 96, 110, 112, 100, 90] 
        data = {
            'symbol': 'TEST',
            'open': close_prices, 'high': close_prices,
            'low': close_prices, 'close': close_prices,
            'adj_close': close_prices, 'volume': [1000] * 10
        }
        synthetic_df = pd.DataFrame(data, index=dates)

        # --- 3. Manually Calculate the Expected Outcome with new prices ---
        # Initial Capital: $100,000 | Commission: $1.00 per trade
        # Buy signal on day 7 at price $110
        cash_after_buy = 100000 - (100 * 110) - 1.00  # = $88,999.00
        # Sell signal on day 10 at price $90
        cash_after_sell = cash_after_buy + (100 * 90) - 1.00 # = $97,998.00
        expected_final_equity = cash_after_sell

        # --- 4. Set up and run the backtest ---
        data_provider = SyntheticDataProvider(synthetic_df)
        strategy_instance = SmaCrossTest()
        strategy_instance.short_window = 3
        strategy_instance.long_window = 5
        
        portfolio = Portfolio(initial_cash=100000.0)
        broker = Broker(commission_percentage=1.0)
        
        engine = BacktestEngine(
            data_provider=data_provider,
            strategy_instance=strategy_instance,
            portfolio=portfolio,
            broker=broker
        )
        
        equity_curve = engine.run()
        actual_final_equity = equity_curve['equity'].iloc[-1]

        # --- 5. Assert the Result ---
        print(f"\n--- Accuracy Test ---")
        print(f"Expected Final Equity: ${expected_final_equity:,.2f}")
        print(f"Actual Final Equity:   ${actual_final_equity:,.2f}")
        self.assertAlmostEqual(
            expected_final_equity,
            actual_final_equity,
            places=2,
            msg="The final equity from the backtest does not match the pre-calculated expected value."
        )
        print("Framework accuracy test passed successfully!")

if __name__ == '__main__':
    unittest.main()

