import sys
import os
import matplotlib.pyplot as plt

#set the path to the parent directory to import custom modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- MODIFICATION 1: Import the class, not the old function ---
from data.yfinance_provider import YFinanceProvider
from tools.fractal_levels import find_fractal_levels
from tools.kmeans_levels import find_kmeans_levels
from tools.kde_levels import find_kde_levels
from tools.pivot_points import calculate_pivot_points
from tools.zigzag_levels import find_zigzag_sr_levels

def plot_levels(title, df, levels, supports=None, resistances=None):
    """Generic plotting function."""
    plt.figure(figsize=(15, 7))
    plt.plot(df['close'], label='Close Price')
    
    if supports:
        for s in supports:
            plt.axhline(y=s, color='lime', linestyle='--', alpha=0.5)
    if resistances:
        for r in resistances:
            plt.axhline(y=r, color='red', linestyle='--', alpha=0.5)
    if levels:
        for level in levels:
            plt.axhline(y=level, color='cyan', linestyle='--', alpha=0.6)
            
    plt.title(title)
    plt.xlabel('Date')
    plt.ylabel('Price ($)')
    plt.legend()
    plt.show()

if __name__ == "__main__":
    SYMBOL = 'AAPL'
    START_DATE = '2023-01-01'
    END_DATE = '2024-01-01'
    
    plt.style.use('dark_background')
    
    # --- MODIFICATION 2: Instantiate the provider and get data from it ---
    # Create an instance of the data provider
    provider = YFinanceProvider(SYMBOL, START_DATE, END_DATE)
    # Get the full DataFrame from the provider instance
    data = provider.get_all_data()


    # 1. Fractal Levels
    supports, resistances = find_fractal_levels(data.copy())
    plot_levels(f'Fractal Levels for {SYMBOL}', data, [], supports, resistances)
    
    # 2. K-Means Clustering Levels
    kmeans_levels = find_kmeans_levels(data, n_clusters=7)
    plot_levels(f'K-Means S/R Levels for {SYMBOL}', data, kmeans_levels)
    
    # 3. Kernel Density Estimation (KDE) Levels
    avg_candle_size = (data['high'] - data['low']).mean()
    kde_levels, price_range, density = find_kde_levels(data, bandwidth=avg_candle_size)
    
    fig, ax1 = plt.subplots(figsize=(15, 7))
    ax1.plot(data.index, data['close'], label='Close Price', color='cyan')
    ax1.set_ylabel('Price ($)', color='cyan')
    for level in kde_levels:
        ax1.axhline(y=level, color='yellow', linestyle='--', alpha=0.7)
    ax2 = ax1.twiny()
    ax2.plot(density, price_range, label='Price Density (KDE)', color='magenta', alpha=0.7)
    ax2.set_xlabel('Density', color='magenta')
    plt.title(f'KDE S/R Levels for {SYMBOL}')
    plt.show()

    # 4. Pivot Points
    pivot_data = calculate_pivot_points(data.copy())
    plot_data = pivot_data.tail(90)
    
    plt.figure(figsize=(15, 7))
    plt.plot(plot_data['close'], label='Close Price', zorder=5)
    plt.plot(plot_data['pp'], linestyle='-', color='white', label='PP')
    plt.plot(plot_data['r1'], linestyle='--', color='red', label='R1')
    plt.plot(plot_data['s1'], linestyle='--', color='lime', label='S1')
    plt.plot(plot_data['r2'], linestyle='--', color='salmon', label='R2')
    plt.plot(plot_data['s2'], linestyle='--', color='lightgreen', label='S2')
    plt.title(f'Daily Pivot Points for {SYMBOL} (Last 90 Days)')
    plt.legend()
    plt.show()

    # 5. Zig-Zag Levels
    zigzag_levels, zigzag_pivots = find_zigzag_sr_levels(data, deviation=0.08, n_clusters=6)
    
    plt.figure(figsize=(15, 7))
    plt.plot(data['close'], label='Close Price', alpha=0.8)
    plt.plot(zigzag_pivots['index'], zigzag_pivots['price'], color='yellow', marker='o', linestyle='-', label='Zig-Zag (8%)')
    for level in zigzag_levels:
        plt.axhline(y=level, color='cyan', linestyle='--', alpha=0.7)
    plt.title(f'Zig-Zag S/R Levels for {SYMBOL}')
    plt.legend()
    plt.show()