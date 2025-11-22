import sys
import os
import matplotlib.pyplot as plt

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data.yfinance_provider import YFinanceProvider
from portfolio.portfolio import Portfolio
from broker.broker import Broker
from engine.engine import BacktestEngine
from performance.analysis import PerformanceAnalyzer
from strategy.sma_cross import SmaCross

if __name__ == '__main__':
    # --- Setup components for a single symbol ---
    data_provider = YFinanceProvider(
        symbol='NPN.JO',
        start_date='2023-01-01',
        end_date='2025-12-31'
    )
    portfolio = Portfolio(initial_cash=100000.0)
    broker = Broker(commission_percentage=1.0)
    
    # --- Instantiate the Strategy with its dependencies ---
    strategy_instance = SmaCross(data=data_provider, portfolio=portfolio, broker=broker)
    
    engine = BacktestEngine(
        data_provider=data_provider,
        strategy_instance=strategy_instance,
        portfolio=portfolio,
        broker=broker
    )
    
    equity_curve = engine.run()

    analyzer = PerformanceAnalyzer(equity_curve, portfolio)
    analyzer.generate_report()

    # --- Plotting the Equity Curve ---
    if not equity_curve.empty:
        plt.figure(figsize=(12, 8))
        plt.plot(equity_curve.index, equity_curve['equity'], label='Strategy Equity')
        plt.title('Portfolio Equity Curve')
        plt.xlabel('Date')
        plt.ylabel('Portfolio Value ($)')
        plt.legend()
        plt.grid(True)
        plt.show()

