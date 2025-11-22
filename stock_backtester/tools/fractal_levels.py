import pandas as pd
import numpy as np

# --- THE FIX IS HERE (Part 1) ---
# The default merging percentage is now defined inside the module.
DEFAULT_MERGE_PERCENT = 0.03

def _merge_nearby_levels(levels: list, merge_percent: float, price_range: float) -> list:
    """
    Helper function to merge price levels that are close to each other.
    """
    if not levels:
        return []
    
    threshold = price_range * merge_percent
    
    sorted_levels = sorted(levels)
    
    merged_levels = []
    current_cluster = [sorted_levels[0]]

    for i in range(1, len(sorted_levels)):
        if sorted_levels[i] - current_cluster[-1] < threshold:
            current_cluster.append(sorted_levels[i])
        else:
            merged_levels.append(np.mean(current_cluster))
            current_cluster = [sorted_levels[i]]
    
    if current_cluster:
        merged_levels.append(np.mean(current_cluster))
        
    return merged_levels

# --- THE FIX IS HERE (Part 2) ---
# The function now uses the default merge percent unless overridden.
def find_fractal_levels(df: pd.DataFrame, n: int = 2, merge_percent: float = DEFAULT_MERGE_PERCENT):
    """
    Identifies and optionally merges fractal-based support and resistance levels.
    
    Args:
        df (pd.DataFrame): DataFrame with price data.
        n (int): The number of bars to check on each side.
        merge_percent (float): The percentage of the price range to use as a threshold
                               for merging nearby levels. If 0, no merging is done.
    Returns:
        tuple: A tuple of (support_levels, resistance_levels).
    """
    is_resistance = (df['high'] > df['high'].shift(1)) & \
                    (df['high'] > df['high'].shift(2)) & \
                    (df['high'] > df['high'].shift(-1)) & \
                    (df['high'] > df['high'].shift(-2))
                           
    is_support = (df['low'] < df['low'].shift(1)) & \
                 (df['low'] < df['low'].shift(2)) & \
                 (df['low'] < df['low'].shift(-1)) & \
                 (df['low'] < df['low'].shift(-2))

    support_levels = df.loc[is_support, 'low'].tolist()
    resistance_levels = df.loc[is_resistance, 'high'].tolist()

    if merge_percent > 0 and not df.empty:
        price_range = df['high'].max() - df['low'].min()
        if price_range > 0:
            support_levels = _merge_nearby_levels(support_levels, merge_percent, price_range)
            resistance_levels = _merge_nearby_levels(resistance_levels, merge_percent, price_range)

    return support_levels, resistance_levels