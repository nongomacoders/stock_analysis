import numpy as np
import pandas as pd
from scipy.signal import argrelextrema, find_peaks
from sklearn.neighbors import KernelDensity

def find_kde_levels(df: pd.DataFrame, bandwidth: float = 1.0, order: int = 5) -> tuple:
    """
    Identifies S/R levels using Kernel Density Estimation on swing points.

    Args:
        df (pd.DataFrame): DataFrame with 'high' and 'low' columns.
        bandwidth (float): The bandwidth of the kernel. Controls smoothness.
        order (int): The number of points on each side to define a local max/min.

    Returns:
        tuple: A tuple containing (levels, price_range, density) for plotting.
    """
    high_indices = argrelextrema(df['high'].values, np.greater, order=order)[0]
    low_indices = argrelextrema(df['low'].values, np.less, order=order)[0]
    
    swing_points = np.concatenate([
        df['high'].iloc[high_indices].values,
        df['low'].iloc[low_indices].values
    ]).reshape(-1, 1)

    if len(swing_points) < 1:
        return [], np.array([]), np.array([])
    
    kde = KernelDensity(kernel='gaussian', bandwidth=bandwidth).fit(swing_points)
    
    price_min = df['low'].min()
    price_max = df['high'].max()
    price_range = np.linspace(price_min, price_max, 1000).reshape(-1, 1)
    
    log_density = kde.score_samples(price_range)
    density = np.exp(log_density)
    
    peaks, _ = find_peaks(density, prominence=density.max() * 0.1)
    levels = sorted(price_range[peaks].flatten().tolist())
    
    return levels, price_range.flatten(), density