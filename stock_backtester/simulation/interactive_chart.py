import pandas as pd

import plotly.graph_objects as go
import plotly.io as pio
import logging
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from data.yfinance_provider import YFinanceProvider
# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s - %(message)s', datefmt='%H:%M:%S')

# 1. Fetch data
symbol = 'AAPL'
start_date = '2024-01-01'
end_date = '2025-09-28'  # Adjusted to avoid future dates
yfp= YFinanceProvider(symbol, start_date, end_date)
logging.info(f"Fetching data for {symbol} from {start_date} to {end_date}...")
data = yfp.get_all_data()



# 2. Create candlestick chart
logging.info("Creating Plotly candlestick chart...")
fig = go.Figure(data=[go.Candlestick(
    x=data.index,
    open=data['open'],
    high=data['high'],
    low=data['low'],
    close=data['close'],
    name=symbol
)])

# 3. Customize layout
logging.info("Applying chart layout...")
fig.update_layout(
    title=f'{symbol} Interactive Candlestick Chart',
    yaxis_title='Price (USD)',
    xaxis_title='Date',
    xaxis_rangeslider_visible=True
)

# 4. Render chart
logging.info("Rendering chart...")
pio.renderers.default = 'browser'  # Use browser renderer
fig.show()
fig.write_html("candlestick_chart.html")  # Save for debugging
logging.info("Chart saved as candlestick_chart.html")
logging.info("Script finished.")