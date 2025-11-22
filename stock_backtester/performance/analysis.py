import numpy as np
import pandas as pd
from portfolio.portfolio import Portfolio

class PerformanceAnalyzer:
    """
    Transforms the raw output from a backtest into a standardized set of
    quantitative metrics and visualizations to evaluate a strategy's viability.
    """
    def __init__(self, equity_curve: pd.DataFrame, portfolio: Portfolio):
        """
        Initializes the analyzer with the results from a completed backtest.

        Args:
            equity_curve: A DataFrame with a DatetimeIndex and an 'equity' column.
            portfolio: The final Portfolio object from the backtest.
        """
        self.equity_curve = equity_curve
        self.portfolio = portfolio
        self.returns = self.equity_curve['equity'].pct_change().dropna()

    def calculate_sharpe_ratio(self, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
        """
        Calculates the annualized Sharpe Ratio.

        Args:
            risk_free_rate: The annual risk-free rate.
            periods_per_year: Number of trading periods in a year (e.g., 252 for daily).

        Returns:
            The annualized Sharpe Ratio. Returns -100 for strategies with no trades.
        """
        if self.returns.std() == 0:
            # If there's no volatility (i.e., no trades were made), the strategy
            # is not viable. Return a large negative number to penalize it during optimization.
            return -100.0

        excess_returns = self.returns - (risk_free_rate / periods_per_year)
        sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns)
        annualized_sharpe = sharpe_ratio * np.sqrt(periods_per_year)
        return annualized_sharpe

    def calculate_max_drawdown(self) -> float:
        """
        Calculates the Maximum Drawdown (MDD).

        Returns:
            The MDD as a negative percentage.
        """
        if self.equity_curve.empty:
            return 0.0
            
        high_water_mark = self.equity_curve['equity'].cummax()
        drawdown = (self.equity_curve['equity'] - high_water_mark) / high_water_mark
        max_drawdown = drawdown.min()
        return max_drawdown * 100

    def calculate_cagr(self) -> float:
        """
        Calculates the Compound Annual Growth Rate (CAGR).

        Returns:
            The CAGR as a percentage.
        """
        if self.equity_curve.empty:
            return 0.0

        start_value = self.portfolio.initial_cash
        end_value = self.equity_curve['equity'].iloc[-1]
        
        start_date = self.equity_curve.index[0]
        end_date = self.equity_curve.index[-1]
        
        years = (end_date - start_date).days / 365.25
        
        if years == 0:
            return 0.0

        cagr = ((end_value / start_value) ** (1 / years)) - 1
        return cagr * 100

    def calculate_trade_stats(self) -> dict:
        """
        Calculates statistics based on the trade log from the portfolio.

        Returns:
            A dictionary containing key trade-level statistics.
        """
        trades = self.portfolio.trade_log
        if not trades:
            return {
                'total_trades': 0, 'win_rate': 0.0, 'profit_factor': 0.0,
                'average_win': 0.0, 'average_loss': 0.0
            }

        # --- FIX: Changed 'pnl' to 'profit' to match the portfolio's trade log ---
        wins = [t for t in trades if t['profit'] > 0]
        losses = [t for t in trades if t['profit'] <= 0]

        total_trades = len(trades)
        win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0.0

        gross_profit = sum(t['profit'] for t in wins)
        gross_loss = abs(sum(t['profit'] for t in losses))

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        average_win = gross_profit / len(wins) if wins else 0.0
        average_loss = gross_loss / len(losses) if losses else 0.0

        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'average_win': average_win,
            'average_loss': average_loss
        }

    def generate_report(self):
        """Prints a comprehensive performance and risk analysis report."""
        print("\n--- Performance & Risk Analysis ---")
        if self.equity_curve.empty:
            print("No trades were made. Cannot generate a report.")
            return

        total_return = (self.equity_curve['equity'].iloc[-1] / self.portfolio.initial_cash - 1) * 100
        cagr = self.calculate_cagr()
        sharpe = self.calculate_sharpe_ratio()
        max_dd = self.calculate_max_drawdown()
        
        trade_stats = self.calculate_trade_stats()

        print(f"Total Return:        {total_return: .2f}%")
        print(f"CAGR:                {cagr: .2f}%")
        print(f"Sharpe Ratio:        {sharpe: .2f}")
        print(f"Max Drawdown:        {max_dd: .2f}%")
        print("-----------------------------------")
        print(f"Total Trades:        {trade_stats['total_trades']}")
        print(f"Win Rate:            {trade_stats['win_rate']: .2f}%")
        print(f"Profit Factor:       {trade_stats['profit_factor']: .2f}")
        print(f"Average Win:         $ {trade_stats['average_win']:,.2f}")
        print(f"Average Loss:        $ {trade_stats['average_loss']:,.2f}")
        print("-----------------------------------")

