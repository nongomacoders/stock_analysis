from __future__ import annotations
import pandas as pd
from itertools import product
from data.yfinance_provider import YFinanceProvider
from portfolio.portfolio import Portfolio
from broker.broker import Broker
from engine.engine import BacktestEngine
from performance.analysis import PerformanceAnalyzer
from strategy.strategy import Strategy

class Optimizer:
    """
    Wraps the BacktestEngine to run multiple backtests for different
    strategy parameter combinations and find the best performing set.
    """
    def __init__(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        # --- FIX: Accept a pre-configured strategy INSTANCE ---
        strategy_instance: Strategy,
        param_grid: dict,
        initial_cash: float = 100000.0,
        commission_fee: float = 1.0
    ):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        # --- FIX: Store the instance directly ---
        self.strategy_instance = strategy_instance
        self.param_grid = param_grid
        self.initial_cash = initial_cash
        self.commission_fee = commission_fee

    def _run_single_backtest(self, params: dict) -> float:
        """
        Initializes and runs a single backtest for a given set of parameters.
        """
        # For each run, create fresh, independent components
        provider = YFinanceProvider(self.symbol, self.start_date, self.end_date)
        portfolio = Portfolio(initial_cash=self.initial_cash)
        broker = Broker(commission_percentage=self.commission_fee)
        
        # --- FIX: Use the stored strategy instance ---
        # Update its dependencies and parameters for this specific run
        self.strategy_instance.data = provider
        self.strategy_instance.portfolio = portfolio
        self.strategy_instance.broker = broker
        for key, value in params.items():
            setattr(self.strategy_instance, key, value)

        engine = BacktestEngine(provider, self.strategy_instance, portfolio, broker)
        equity_curve = engine.run()

        if equity_curve.empty:
            return -100.0

        analyzer = PerformanceAnalyzer(equity_curve, portfolio)
        return analyzer.calculate_sharpe_ratio()

    def _generate_param_combinations(self):
        """Generates all possible combinations from the parameter grid."""
        keys = self.param_grid.keys()
        values = self.param_grid.values()
        for instance in product(*values):
            yield dict(zip(keys, instance))

    def run_optimization(self) -> dict | None:
        """
        Iterates through all parameter combinations, runs backtests, and
        identifies the best performing set.
        """
        print("--- Starting Parameter Optimization ---\n")
        best_sharpe = -float('inf')
        best_params = None

        for params in self._generate_param_combinations():
            if 'short_window' in params and 'long_window' in params:
                if params['short_window'] >= params['long_window']:
                    continue
            print(f"Testing parameters: {params}")
            sharpe_ratio = self._run_single_backtest(params)
            print(f"Result -> Sharpe Ratio: {sharpe_ratio:.2f}\n")
            if sharpe_ratio > best_sharpe:
                best_sharpe = sharpe_ratio
                best_params = params

        print("\n--- Optimization Complete ---")
        print(f"Best Parameters Found: {best_params}")
        print(f"Best Sharpe Ratio:    {best_sharpe:.2f}")
        return best_params

