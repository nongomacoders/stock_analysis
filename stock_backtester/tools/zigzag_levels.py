import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

def find_zigzag_pivots(df: pd.DataFrame, deviation_threshold: float = 0.05):
    """
    Identifies Zig-Zag reversal points based on a deviation threshold.
    """
    pivots = []
    last_pivot_price = None
    last_pivot_index = 0
    trend = 0

    for i in range(len(df)):
        if last_pivot_price is None:
            last_pivot_price = df['close'].iloc[i]
            pivots.append({'index': df.index[i], 'price': df['close'].iloc[i]})
            continue

        price = df['close'].iloc[i]
        deviation = (price - last_pivot_price) / last_pivot_price if last_pivot_price != 0 else 0

        current_trend = np.sign(deviation)
        
        if trend == 0 and abs(deviation) > deviation_threshold:
            trend = current_trend
        
        if trend == 1 and deviation < -deviation_threshold: # Downturn
            high_index = df['high'].iloc[last_pivot_index:i+1].idxmax()
            high_price = df.loc[high_index, 'high']
            pivots.append({'index': high_index, 'price': high_price})
            last_pivot_price, last_pivot_index = high_price, i
            trend = -1
        elif trend == -1 and deviation > deviation_threshold: # Upturn
            low_index = df['low'].iloc[last_pivot_index:i+1].idxmin()
            low_price = df.loc[low_index, 'low']
            pivots.append({'index': low_index, 'price': low_price})
            last_pivot_price, last_pivot_index = low_price, i
            trend = 1
            
    return pd.DataFrame(pivots)

def find_zigzag_sr_levels(df: pd.DataFrame, deviation: float = 0.05, n_clusters: int = 5) -> tuple:
    """
    Finds Zig-Zag pivots and then clusters them to find S/R levels.
    """
    zigzag_pivots = find_zigzag_pivots(df, deviation_threshold=deviation)

    # --- THE FIX IS HERE ---
    # 1. Check if any pivots were found. If not, return empty lists.
    if zigzag_pivots.empty:
        return [], zigzag_pivots

    num_pivots = len(zigzag_pivots)
    
    # 2. Dynamically adjust n_clusters if there are fewer pivots than requested.
    if num_pivots < n_clusters:
        n_clusters = num_pivots
    # --- END OF FIX ---

    pivot_prices = zigzag_pivots['price'].values.reshape(-1, 1)
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init='auto')
    kmeans.fit(pivot_prices)
    levels = sorted(kmeans.cluster_centers_.flatten().tolist())

    return levels, zigzag_pivots