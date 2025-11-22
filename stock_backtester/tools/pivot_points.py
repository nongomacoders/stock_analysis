import pandas as pd

def calculate_pivot_points(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates classic daily pivot points and S/R levels.
    Assumes the input DataFrame has a daily frequency.
    """
    df_pivots = df.copy()
    prev_high = df_pivots['high'].shift(1)
    prev_low = df_pivots['low'].shift(1)
    prev_close = df_pivots['close'].shift(1)

    df_pivots['pp'] = (prev_high + prev_low + prev_close) / 3
    df_pivots['r1'] = (2 * df_pivots['pp']) - prev_low
    df_pivots['s1'] = (2 * df_pivots['pp']) - prev_high
    df_pivots['r2'] = df_pivots['pp'] + (prev_high - prev_low)
    df_pivots['s2'] = df_pivots['pp'] - (prev_high - prev_low)
    df_pivots['r3'] = prev_high + 2 * (df_pivots['pp'] - prev_low)
    df_pivots['s3'] = prev_low - 2 * (prev_high - df_pivots['pp'])
    
    return df_pivots