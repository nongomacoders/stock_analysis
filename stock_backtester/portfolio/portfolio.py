import pandas as pd
from broker.broker import Fill

class Portfolio:
    """
    Acts as the official bookkeeper for the backtest. It tracks the
    composition and value of the simulated portfolio at every point in time.
    """
    def __init__(self, initial_cash: float):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions = {}
        self.equity_curve = [{'timestamp': None, 'equity': initial_cash}]
        
        # --- For Trade-level Statistics ---
        self.trade_log = []
        self._open_trades = {}

    def update_market_value(self, timestamp: pd.Timestamp, new_prices: dict):
        """
        Marks the portfolio to market, updating the current value of all holdings
        and recording the total equity for the current time step.
        """
        market_value = 0.0
        for symbol, quantity in self.positions.items():
            # Use the close price from the market data for the current symbol
            price = new_prices.get(symbol, {}).get('close')
            if price is not None:
                market_value += quantity * price
        
        total_equity = self.cash + market_value
        self.equity_curve.append({'timestamp': timestamp, 'equity': total_equity})
        
        # --- DEBUGGING ---
        print(f"  [Portfolio.update_market_value] Timestamp: {timestamp.date() if timestamp else 'N/A'} | Cash: ${self.cash:,.2f} | Market Value: ${market_value:,.2f} | Recorded Equity: ${total_equity:,.2f}")
        # --- END DEBUGGING ---


    def update_fill(self, fill: Fill):
        """Updates portfolio state based on a Fill event."""
        symbol = fill.symbol
        
        if fill.action == 'BUY':
            # --- DEBUGGING ---
            print(f"  [Portfolio.update_fill] --- BUY FILL ---")
            print(f"    - Cash before buy: ${self.cash:,.2f}")
            trade_value = fill.quantity * fill.price
            print(f"    - Trade value: ${trade_value:,.2f}, Commission: ${fill.commission:,.2f}")
            self.cash -= (trade_value + fill.commission)
            print(f"    - Cash after buy:  ${self.cash:,.2f}")
            # --- END DEBUGGING ---
            
            self.positions[symbol] = self.positions.get(symbol, 0) + fill.quantity
            
            if symbol not in self._open_trades:
                self._open_trades[symbol] = {'entry_price': fill.price, 'quantity': fill.quantity}

        elif fill.action == 'SELL':
            # --- DEBUGGING ---
            print(f"  [Portfolio.update_fill] --- SELL FILL ---")
            print(f"    - Cash before sell: ${self.cash:,.2f}")
            proceeds = abs(fill.quantity) * fill.price
            print(f"    - Proceeds: ${proceeds:,.2f}, Commission: ${fill.commission:,.2f}")
            self.cash += (proceeds - fill.commission)
            print(f"    - Cash after sell:  ${self.cash:,.2f}")
            # --- END DEBUGGING ---

            if symbol in self._open_trades:
                entry_price = self._open_trades[symbol]['entry_price']
                profit = (fill.price - entry_price) * abs(fill.quantity) - (fill.commission * 2)
                self.trade_log.append({
                    'symbol': symbol,
                    'profit': profit,
                    'win': profit > 0
                })
                del self._open_trades[symbol]
            
            self.positions[symbol] = self.positions.get(symbol, 0) + fill.quantity
            if self.positions[symbol] == 0:
                del self.positions[symbol]

