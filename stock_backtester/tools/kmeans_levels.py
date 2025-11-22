import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from sklearn.cluster import KMeans

def find_kmeans_levels(df: pd.DataFrame, n_clusters: int = 8, order: int = 5) -> list:
    """
    Identifies S/R levels using K-Means clustering on swing highs and lows.
    """
    # Find local minima and maxima (swing points)
    high_indices = argrelextrema(df['high'].values, np.greater, order=order)[0]
    low_indices = argrelextrema(df['low'].values, np.less, order=order)[0]
    
    swing_highs = df['high'].iloc[high_indices]
    swing_lows = df['low'].iloc[low_indices]
    
    # Check if any swing points were found
    if swing_highs.empty and swing_lows.empty:
        return []

    all_swing_points = pd.concat([swing_highs, swing_lows]).values.reshape(-1, 1)

    # --- THE FIX IS HERE ---
    # Ensure n_clusters is not greater than the number of available swing points.
    num_available_points = len(all_swing_points)
    
    if num_available_points < n_clusters:
        # If we have fewer points than requested clusters, use the number of points
        # as the cluster count. This prevents the ValueError.
        n_clusters = num_available_points

    # --- END OF FIX ---

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init='auto')
    kmeans.fit(all_swing_points)
    
    levels = sorted(kmeans.cluster_centers_.flatten().tolist())
    
    return levels