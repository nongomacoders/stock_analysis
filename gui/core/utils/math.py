import pandas as pd


def convert_yf_price_to_cents(price_value):
    """
    Converts a yfinance price value to an integer representing cents.
    """
    try:
        if pd.isna(price_value) or price_value is None:
            return None
        return int(float(price_value))
    except Exception:
        return None
