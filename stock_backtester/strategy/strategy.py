from __future__ import annotations
import abc
from typing import TYPE_CHECKING

# Use a TYPE_CHECKING block to prevent circular imports at runtime
if TYPE_CHECKING:
    from data.yfinance_provider import YFinanceProvider
    from portfolio.portfolio import Portfolio
    from broker.broker import Broker

class Strategy(abc.ABC):
    """
    An abstract base class that defines the interface for all trading strategies.
    """
    def __init__(self, data: YFinanceProvider, portfolio: Portfolio, broker: Broker):
        """
        Initializes the strategy with its required helper objects.

        This explicit dependency injection makes the class easier to test and
        provides full type-hinting support for IDEs, resolving any warnings.

        Args:
            data: The data provider instance for market data access.
            portfolio: The portfolio instance for state tracking.
            broker: The broker instance for order execution.
        """
        self.data = data
        self.portfolio = portfolio
        self.broker = broker

    @abc.abstractmethod
    def initialize(self):
        """
        Called by the engine once at the start of a simulation.
        """
        raise NotImplementedError("Should implement initialize()")

    @abc.abstractmethod
    def on_bar(self):
        """
        The heart of the strategy logic, called by the engine for each new bar of data.
        """
        raise NotImplementedError("Should implement on_bar()")