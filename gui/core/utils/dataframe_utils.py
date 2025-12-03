from typing import Optional, Tuple, Any
import pandas as pd


def prepare_df_source(data: Optional[Any], period_key: Optional[str]) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Prepare incoming data into a cleaned OHLC pandas DataFrame for plotting.

    Returns a tuple (df_source, error_message). If prepping succeeded, df_source is
    a pandas.DataFrame and error_message is None. If it failed, df_source is None
    and error_message contains a readable message for the caller.

    Behavior mirrors the original logic in BaseChart.plot:
    - If data is None/empty returns (None, 'No data available')
    - If period_key is None returns (None, 'No period key specified')
    - Accepts a pandas.DataFrame OR a list/iterable of dicts containing
      trade_date/open_price/high_price/low_price/close_price
    - If a DataFrame is passed it is copied. Otherwise it creates a DataFrame,
      converts the trade_date to datetime, sets it to index and converts price
      cents to rands (divides by 100).
    - Renames open_price/high_price/low_price/close_price to Open/High/Low/Close.
    - Drops rows missing any of Open/High/Low/Close and returns error if empty.
    """
    # Basic data/period checks
    if data is None or (isinstance(data, (list, tuple)) and not data):
        return None, "No data available"

    if period_key is None:
        return None, "No period key specified"

    # Convert incoming data to DataFrame in expected OHLC format
    try:
        if isinstance(data, pd.DataFrame):
            df_source = data.copy()
        else:
            df_source = pd.DataFrame(data)
            if "trade_date" not in df_source.columns:
                return None, "Missing 'trade_date' column in provided data"

            df_source["trade_date"] = pd.to_datetime(df_source["trade_date"])
            df_source.set_index("trade_date", inplace=True)

            # Convert prices (cents -> rands)
            for col in ["open_price", "high_price", "low_price", "close_price"]:
                if col in df_source.columns:
                    df_source[col] = pd.to_numeric(df_source[col], errors="coerce") / 100.0

            df_source = df_source.rename(
                columns={
                    "open_price": "Open",
                    "high_price": "High",
                    "low_price": "Low",
                    "close_price": "Close",
                }
            )

        # Clean: require valid OHLC
        df_source = df_source.dropna(subset=["Open", "High", "Low", "Close"])

        if df_source.empty:
            return None, "No valid OHLC data"

        return df_source, None

    except Exception as ex:
        # Catch any parsing error and report it for the caller
        return None, f"Error preparing data: {ex}"
