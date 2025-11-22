import pandas as pd
from strategy.strategy import Strategy

class SmaCross(Strategy):
    """
    A simple moving average crossover strategy.

    This strategy generates a buy signal when a short-term moving average
    crosses above a long-term moving average (a "golden cross") and a sell
    signal when it crosses below (a "death cross").
    """
    # User-defined parameters for the strategy
    short_window = 20
    long_window = 50

    def initialize(self):
        """Called once at the start of the backtest."""
        print(f"Strategy Initialized: Short MA={self.short_window}, Long MA={self.long_window}")

    def on_bar(self):
        """Called on every new bar of data."""
        symbol = self.data.symbol
        
        history = self.data.get_history(symbol, bars=self.long_window + 1)
        
        if history is None or len(history) < self.long_window + 1:
            return

        sma_short = history['close'].rolling(window=self.short_window).mean()
        sma_long = history['close'].rolling(window=self.long_window).mean()

        if pd.isna(sma_long.iloc[-2]):
            return

        is_in_position = self.portfolio.positions.get(symbol, 0) > 0

        # Golden Cross: short MA crosses above long MA -> Buy Signal
        if sma_short.iloc[-1] > sma_long.iloc[-1] and sma_short.iloc[-2] <= sma_long.iloc[-2]:
            if not is_in_position:
                # --- FIX: Add a check to ensure the latest bar is not None ---
                latest_bar = self.data.get_latest_bar(symbol)
                if latest_bar is not None:
                    latest_price = latest_bar['close']
                    quantity_to_buy = self.portfolio.cash * 0.95 / latest_price
                    self.broker.buy(symbol=symbol, quantity=int(quantity_to_buy))
                    print(f"{history.index[-1].date()}: BUY signal. Price: {latest_price:.2f}")

        # Death Cross: short MA crosses below long MA -> Sell Signal
        elif sma_short.iloc[-1] < sma_long.iloc[-1] and sma_short.iloc[-2] >= sma_long.iloc[-2]:
            if is_in_position:
                # --- FIX: Add a similar check for the sell signal ---
                latest_bar = self.data.get_latest_bar(symbol)
                if latest_bar is not None:
                    latest_price = latest_bar['close']
                    self.broker.close(symbol=symbol)
                    print(f"{history.index[-1].date()}: SELL signal. Price: {latest_price:.2f}")

