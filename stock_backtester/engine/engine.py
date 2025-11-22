import pandas as pd
from data.yfinance_provider import BaseDataProvider
from strategy.strategy import Strategy
from portfolio.portfolio import Portfolio
from broker.broker import Broker

class BacktestEngine:
    """
    The central nervous system of the framework.
    It orchestrates the data provider, strategy logic, broker simulation,
    and portfolio management to run a complete backtest from start to finish.
    """
    def __init__(self, data_provider: BaseDataProvider, strategy_instance: Strategy, portfolio: Portfolio, broker: Broker):
        self.data_provider = data_provider
        self.strategy = strategy_instance 
        self.portfolio = portfolio
        self.broker = broker
        
        self.strategy.data = self.data_provider
        self.strategy.portfolio = self.portfolio
        self.strategy.broker = self.broker

    def run(self) -> pd.DataFrame:
        """
        Contains the main event loop that drives the simulation.
        """
        self.strategy.initialize()
        
        data_stream = self.data_provider.stream_next()
        
        last_market_data = {}
        for market_data in data_stream:
            current_timestamp = self.data_provider.current_bar.name
            last_market_data = market_data
            
            self.portfolio.update_market_value(current_timestamp, market_data)

            self.strategy.on_bar()

            orders_to_execute = self.broker.get_pending_orders()
            for order in orders_to_execute:
                if order.action == 'CLOSE':
                    if order.symbol in self.portfolio.positions and self.portfolio.positions[order.symbol] > 0:
                        quantity_to_close = self.portfolio.positions[order.symbol]
                        order.action = 'SELL'
                        order.quantity = -quantity_to_close
                    else:
                        continue

                fill_price = market_data.get(order.symbol, {}).get('close')
                
                if fill_price is not None:
                    fill_event = self.broker.execute_order(order, fill_price)
                    
                    if fill_event:
                        self.portfolio.update_fill(fill_event)

        # --- FIX: Liquidate any open positions at the end of the backtest ---
        if self.portfolio.positions:
            print("\n--- Backtest finished. Liquidating open positions... ---")
            for symbol, quantity in list(self.portfolio.positions.items()):
                print(f"Closing position in {symbol}: {quantity} shares.")
                last_price = last_market_data.get(symbol, {}).get('close')
                if last_price is not None:
                    close_order = self.broker.sell(symbol, quantity)
                    if close_order:
                         fill_event = self.broker.execute_order(close_order, last_price)
                         if fill_event:
                            self.portfolio.update_fill(fill_event)

        # Correct the final equity record to reflect the true cash balance
        if self.portfolio.equity_curve and len(self.portfolio.equity_curve) > 1:
            final_equity = self.portfolio.cash
            self.portfolio.equity_curve[-1]['equity'] = final_equity

        equity_df = pd.DataFrame(self.portfolio.equity_curve)
        if not equity_df.empty:
            # Drop the initial `None` timestamp row and set the index
            equity_df = equity_df.iloc[1:].set_index('timestamp')
        
        return equity_df

