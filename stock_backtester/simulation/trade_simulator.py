import sys
import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from dataclasses import dataclass
from typing import List

import dash
from dash import dcc, html, Input, Output, callback_context

# --- Assuming yfinance_provider is in a 'data' subfolder ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from data.yfinance_provider import YFinanceProvider

# --- CORE MODULES ---

@dataclass
class Order:
    symbol: str; quantity: float; action: str

@dataclass
class Fill:
    symbol: str; quantity: float; price: float; commission: float; action: str

class Broker:
    def __init__(self, commission_fee: float = 0.0):
        self.commission_fee = commission_fee
        self.order_queue: List[Order] = []

    def buy(self, symbol: str, quantity: float):
        if quantity > 0: self.order_queue.append(Order(symbol, quantity, 'BUY'))

    def sell(self, symbol: str, quantity: float):
        if quantity > 0: self.order_queue.append(Order(symbol, -quantity, 'SELL'))

    def close(self, symbol: str):
        self.order_queue.append(Order(symbol, 0, 'CLOSE'))

    def get_pending_orders(self) -> List[Order]:
        orders_to_process, self.order_queue = self.order_queue, []
        return orders_to_process

    def execute_order(self, order: Order, fill_price: float) -> Fill:
        return Fill(order.symbol, order.quantity, fill_price, self.commission_fee, order.action)

class Portfolio:
    def __init__(self, initial_cash: float):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions = {}
        self.equity_curve = pd.DataFrame(columns=['timestamp', 'equity', 'cash', 'market_value', 'unrealized_pnl'])

    def _get_market_value_and_pnl(self, prices: dict):
        market_value, cost_basis = 0.0, 0.0
        for symbol, pos in self.positions.items():
            price = prices.get(symbol, {}).get('close', 0)
            market_value += pos['quantity'] * price
            cost_basis += pos['cost_basis']
        unrealized_pnl = market_value - cost_basis
        return market_value, unrealized_pnl

    def update_market_value(self, timestamp: pd.Timestamp, new_prices: dict):
        market_value, unrealized_pnl = self._get_market_value_and_pnl(new_prices)
        total_equity = self.cash + market_value
        new_row = pd.DataFrame([{'timestamp': timestamp, 'equity': total_equity, 'cash': self.cash, 'market_value': market_value, 'unrealized_pnl': unrealized_pnl}])
        if not new_row.empty:
            self.equity_curve = pd.concat([self.equity_curve, new_row], ignore_index=True)

    # --- METHOD FIXED ---
    def update_fill(self, fill: Fill):
        symbol = fill.symbol
        if symbol not in self.positions:
            self.positions[symbol] = {'quantity': 0, 'cost_basis': 0.0}
        
        # Use signed quantity to correctly calculate trade value
        trade_value = fill.quantity * fill.price
        
        # Update cash based on action
        if fill.action == 'BUY':
            self.cash -= (abs(trade_value) + fill.commission)
        elif fill.action == 'SELL':
            self.cash += (abs(trade_value) - fill.commission)
            
        # Update position's cost basis and quantity
        # For shorts, trade_value is negative, correctly creating a negative cost_basis
        self.positions[symbol]['cost_basis'] += trade_value
        self.positions[symbol]['quantity'] += fill.quantity

        # Remove position if quantity is zero
        if self.positions[symbol]['quantity'] == 0:
            del self.positions[symbol]


# --- S/R LEVEL TOOLS ---
from scipy.signal import argrelextrema, find_peaks; from sklearn.cluster import KMeans; from sklearn.neighbors import KernelDensity

def find_fractal_levels(df: pd.DataFrame):
    is_r=(df['high'] > df['high'].shift(1))&(df['high'] > df['high'].shift(2))&(df['high'] > df['high'].shift(-1))&(df['high'] > df['high'].shift(-2))
    is_s=(df['low'] < df['low'].shift(1))&(df['low'] < df['low'].shift(2))&(df['low'] < df['low'].shift(-1))&(df['low'] < df['low'].shift(-2))
    return df.loc[is_s, 'low'].tolist(), df.loc[is_r, 'high'].tolist()

def find_kmeans_levels(df: pd.DataFrame, n_clusters: int=8, order: int=5) -> list:
    high_indices=argrelextrema(df['high'].values, np.greater, order=order)[0]
    low_indices=argrelextrema(df['low'].values, np.less, order=order)[0]
    swing_highs, swing_lows = df['high'].iloc[high_indices], df['low'].iloc[low_indices]
    if swing_highs.empty and swing_lows.empty: return []
    all_swing_points=pd.concat([swing_highs, swing_lows]).values.reshape(-1, 1)
    num_points=len(all_swing_points)
    if num_points < n_clusters: n_clusters=num_points
    if n_clusters == 0: return []
    kmeans=KMeans(n_clusters=n_clusters, random_state=42, n_init='auto').fit(all_swing_points)
    return sorted(kmeans.cluster_centers_.flatten().tolist())

def find_zigzag_sr_levels(df: pd.DataFrame, deviation: float=0.05, n_clusters: int=5) -> tuple:
    pivots, last_pivot_price, trend = [], None, 0
    for i in range(len(df)):
        price=df['close'].iloc[i]
        if last_pivot_price is None: last_pivot_price=price; pivots.append({'price': price}); continue
        deviation_val=(price - last_pivot_price) / last_pivot_price if last_pivot_price != 0 else 0
        current_trend=np.sign(deviation_val)
        if trend == 0 and abs(deviation_val) > deviation: trend=current_trend
        if(trend == 1 and deviation_val < -deviation)or(trend == -1 and deviation_val > deviation):
            pivots.append({'price': price}); last_pivot_price, trend = price, -trend
    pivot_df=pd.DataFrame(pivots)
    if pivot_df.empty or len(pivot_df) < n_clusters: return [], pivot_df
    pivot_prices=pivot_df['price'].values.reshape(-1, 1)
    kmeans=KMeans(n_clusters=n_clusters, random_state=42, n_init='auto').fit(pivot_prices)
    return sorted(kmeans.cluster_centers_.flatten().tolist()), pivot_df

def find_kde_levels(df: pd.DataFrame, bandwidth: float=1.0, order: int=5) -> tuple:
    high_indices=argrelextrema(df['high'].values, np.greater, order=order)[0]
    low_indices=argrelextrema(df['low'].values, np.less, order=order)[0]
    swing_points=np.concatenate([df['high'].iloc[high_indices].values, df['low'].iloc[low_indices].values]).reshape(-1, 1)
    if len(swing_points) < 2: return [], np.array([]), np.array([])
    kde=KernelDensity(kernel='gaussian', bandwidth=bandwidth).fit(swing_points)
    price_range=np.linspace(df['low'].min(), df['high'].max(), 500).reshape(-1, 1)
    density=np.exp(kde.score_samples(price_range))
    peaks, _=find_peaks(density, prominence=density.max() * 0.1)
    return sorted(price_range[peaks].flatten().tolist()), price_range.flatten(), density

# --- SIMULATOR ORCHESTRATOR ---
class DashSimulator:
    def __init__(self, symbol, start_date, end_date, initial_cash=100_000_000.00):
        self.symbol, self.portfolio = symbol, Portfolio(initial_cash)
        self.broker = Broker()
        self.provider = YFinanceProvider(symbol, start_date, end_date)
        self.full_data = self.provider.get_all_data()
        self.current_step, self.trade_size = 50, 100
        self.level_type, self.sr_levels = 'Fractal', []
        self.step_forward()

    def step_forward(self):
        if self.current_step >= len(self.full_data): return
        current_data_row = self.full_data.iloc[self.current_step]
        current_price, current_timestamp = current_data_row['close'], current_data_row.name
        orders = self.broker.get_pending_orders()
        for order in orders:
            if order.action == 'CLOSE' and self.symbol in self.portfolio.positions:
                pos_qty = self.portfolio.positions[self.symbol]['quantity']
                if pos_qty != 0: order.quantity, order.action = -pos_qty, 'SELL' if pos_qty > 0 else 'BUY'
                else: continue
            fill = self.broker.execute_order(order, current_price)
            self.portfolio.update_fill(fill)
        prices = {self.symbol: {'close': current_price}}
        self.portfolio.update_market_value(current_timestamp, prices)
        self.update_sr_levels()
    
    def next_bar(self):
        if self.current_step < len(self.full_data) - 1:
            self.current_step += 1
            self.step_forward()

    def update_sr_levels(self):
        current_data=self.full_data.iloc[:self.current_step + 1]
        if self.level_type == 'Fractal': s, r=find_fractal_levels(current_data); self.sr_levels=s + r
        elif self.level_type == 'K-Means': self.sr_levels=find_kmeans_levels(current_data)
        elif self.level_type == 'Zigzag': levels, _=find_zigzag_sr_levels(current_data); self.sr_levels=levels
        elif self.level_type == 'KDE': levels, _, _=find_kde_levels(current_data); self.sr_levels=levels
        else: self.sr_levels=[]

    def get_chart_figure(self):
        current_data = self.full_data.iloc[:self.current_step + 1]
        fig = go.Figure(data=[go.Candlestick(x=current_data.index, open=current_data['open'], high=current_data['high'], low=current_data['low'], close=current_data['close'], name=self.symbol)])
        for level in self.sr_levels:
            fig.add_shape(type='line', x0=current_data.index[0], y0=level, x1=current_data.index[-1], y1=level, line=dict(color='cyan', width=1, dash='dot'))
        if self.symbol in self.portfolio.positions:
            pos = self.portfolio.positions[self.symbol]
            if pos.get('quantity', 0) != 0:
                entry_price = pos['cost_basis'] / pos['quantity']
                color = 'green' if pos['quantity'] > 0 else 'red'
                fig.add_shape(type='line', x0=current_data.index[0], y0=entry_price, x1=current_data.index[-1], y1=entry_price, line=dict(color=color, width=2, dash='dash'))
        fig.update_layout(template='plotly_dark', xaxis_rangeslider_visible=False, margin=dict(l=40, r=40, t=40, b=40))
        return fig

# --- DASH APP ---
sim = DashSimulator(symbol='TFG.JO', start_date='2025-01-01', end_date='2025-09-29')
app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])

app.layout = html.Div(style={'backgroundColor': '#121212', 'color': 'white'}, children=[
    html.Div(className='row', style={'padding': '10px'}, children=[
        html.Div(className='three columns', children=[
            html.H2('Trade Simulator'), html.Hr(),
            html.Div(id='status-bar'), html.Br(),
            html.Label("S/R Level Type:"),
            dcc.Dropdown(id='level-type-dropdown',
                options=[{'label': i, 'value': i} for i in ['Fractal', 'K-Means', 'Zigzag', 'KDE', 'None']],
                value='Fractal', clearable=False, style={'marginBottom': '20px'}
            ),
            html.Button('Buy', id='btn-buy', style={'width': '100%', 'marginBottom': '5px'}),
            html.Button('Sell', id='btn-sell', style={'width': '100%', 'marginBottom': '5px'}),
            html.Button('Close', id='btn-close', style={'width': '100%', 'marginBottom': '5px'}),
            html.Button('Next Bar ->', id='btn-next', style={'width': '100%', 'marginTop': '10px'}),
        ]),
        html.Div(className='nine columns', children=[dcc.Graph(id='trade-chart', style={'height': '90vh'})]),
    ])
])

@app.callback(
    Output('trade-chart', 'figure'),
    Output('status-bar', 'children'),
    Input('btn-buy', 'n_clicks'),
    Input('btn-sell', 'n_clicks'),
    Input('btn-close', 'n_clicks'),
    Input('btn-next', 'n_clicks'),
    Input('level-type-dropdown', 'value'),
)
def update_view(buy_clicks, sell_clicks, close_clicks, next_clicks, level_type):
    ctx = callback_context
    button_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else 'initial_load'
    if sim.level_type != level_type:
        sim.level_type = level_type
        sim.update_sr_levels()
    
    if button_id == 'btn-buy': sim.broker.buy(sim.symbol, sim.trade_size)
    elif button_id == 'btn-sell': sim.broker.sell(sim.symbol, sim.trade_size)
    elif button_id == 'btn-close': sim.broker.close(sim.symbol)
    
    if button_id == 'btn-next': sim.next_bar()
    elif button_id not in ['initial_load', 'level-type-dropdown']:
        sim.step_forward()

    if sim.portfolio.equity_curve.empty: return go.Figure(), "Loading..."
    latest_state = sim.portfolio.equity_curve.iloc[-1]
    equity, unrealized_pnl = latest_state['equity'], latest_state['unrealized_pnl']
    position_qty = sim.portfolio.positions.get(sim.symbol, {}).get('quantity', 0)
    position_str = 'None'
    if position_qty > 0: position_str = 'long'
    elif position_qty < 0: position_str = 'short'

    status_children = [
        html.H4("Account Status"),
        html.P(f"Symbol: {sim.symbol}"),
        html.P(f"Bar: {sim.current_step}/{len(sim.full_data)}"),
        html.P(f"Equity: R{(equity / 100):,.2f}"),
        html.P(f"Unrealized P&L: R{(unrealized_pnl / 100):,.2f}"),      
        html.P(f"Position: {position_str} ({position_qty} shares)")
    ]
    return sim.get_chart_figure(), status_children

if __name__ == '__main__':
    app.run(debug=False)