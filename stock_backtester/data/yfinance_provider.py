# Refactored yfinance_provider.py

from __future__ import annotations
import abc
import pandas as pd
import yfinance as yf
from typing import Dict, Generator

class BaseDataProvider(abc.ABC):
    """
    An abstract base class that defines the interface for all data providers.
    """
    @abc.abstractmethod
    def get_history(self, symbol: str, bars: int) -> pd.DataFrame | None:
        raise NotImplementedError("Should implement get_history()")

    @abc.abstractmethod
    def get_latest_bar(self, symbol: str) -> pd.Series | None:
        raise NotImplementedError("Should implement get_latest_bar()")

    @abc.abstractmethod
    def stream_next(self) -> Generator[Dict[str, pd.Series], None, None]:
        raise NotImplementedError("Should implement stream_next()")

class YFinanceProvider(BaseDataProvider):
    """
    A concrete implementation of BaseDataProvider that sources data for a single
    ticker from Yahoo Finance.
    """
    def __init__(self, symbol: str, start_date: str, end_date: str):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self._data = self._get_data() 
        self.current_bar = None
        self.current_bar_dict = {}

    def _get_data(self) -> pd.DataFrame:
        """
        Fetches and standardizes historical stock data from Yahoo Finance.
        This is an internal helper method.
        """
        print(f"Downloading data for {self.symbol} from {self.start_date} to {self.end_date}...")
        try:
            df = yf.download(
                tickers=self.symbol,
                start=self.start_date,
                end=self.end_date,
                auto_adjust=False,
                progress=False,
                multi_level_index=False
            )
            if df is None or df.empty:
                raise ValueError(f"No data downloaded for symbol '{self.symbol}'. It may be delisted or invalid.")
            
            df.columns = [col.lower().replace(' ', '_') for col in df.columns]
            df['symbol'] = self.symbol
            df = df[['symbol', 'open', 'high', 'low', 'close', 'adj_close', 'volume']]
            df.sort_index(inplace=True)
            print(f"Data for {self.symbol} downloaded and standardized successfully.")
            return df
        except Exception as e:
            print(f"Error downloading or processing data for {self.symbol}: {e}")
            raise
    
    # --- NEW METHOD ADDED HERE ---
    def get_all_data(self) -> pd.DataFrame:
        """
        Returns the complete historical DataFrame.
        """
        return self._data

    def get_history(self, symbol: str, bars: int) -> pd.DataFrame | None:
        """
        Returns a historical window of data for the symbol up to the current time.
        """
        if self.current_bar is None:
            return None
        symbol_data = self._data[self._data['symbol'] == symbol]
        current_timestamp = self.current_bar.name
        relevant_data = symbol_data.loc[:current_timestamp]
        return relevant_data.tail(bars)

    def get_latest_bar(self, symbol: str) -> pd.Series | None:
        """Retrieves the most recent data bar available for the symbol."""
        return self.current_bar_dict.get(symbol, None)

    def stream_next(self) -> Generator[Dict[str, pd.Series], None, None]:
        """
        Yields the next chronological bar of data.
        """
        for timestamp, row in self._data.iterrows():
            self.current_bar = row
            self.current_bar.name = timestamp
            self.current_bar_dict = {row['symbol']: row}
            yield self.current_bar_dict