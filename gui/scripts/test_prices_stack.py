"""Small helper to check pandas/yfinance stacking behavior locally.

This script downloads a tiny set of tickers with yfinance and runs the
same multi-index -> stacked-data logic used by
`modules.market_agent.prices._process_and_save` (with the future_stack=True
fallback) but keeps everything in-memory and prints a short verification.

Usage:
  python scripts/test_prices_stack.py --tickers AAPL MSFT --period 1mo

This avoids requiring DB configuration and is useful for manual, local
integration checks against real-world yfinance output.
"""

import argparse
import logging
import pandas as pd
import yfinance as yf


logger = logging.getLogger("test_prices_stack")


def try_stack(df: pd.DataFrame) -> pd.DataFrame:
    """Attempt stack(future_stack=True) then fall back to stack()."""
    if isinstance(df.columns, pd.MultiIndex):
        logger.info("MultiIndex detected — attempting stack with future_stack=True")
        try:
            stacked = df.stack(future_stack=True).reset_index()
            logger.info("Used future_stack=True")
        except TypeError:
            stacked = df.stack().reset_index()
            logger.info("Fallback: used legacy stack()")
        # try to find the ticker column name
        if "level_1" in stacked.columns:
            stacked = stacked.rename(columns={"level_1": "ticker"})
        elif "Ticker" in stacked.columns:
            stacked = stacked.rename(columns={"Ticker": "ticker"})
        return stacked
    else:
        # single-column downloads (when only one ticker passed and no MultiIndex)
        logger.info("Single index detected — converting to table-like format")
        out = df.reset_index()
        if "Close" in out.columns:
            out["ticker"] = "SINGLE_TICKER"
            out = out.rename(columns={"Date": "trade_date"})
        return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", default=["AAPL", "MSFT"], help="Tickers to download")
    parser.add_argument("--period", default="1mo", help="yfinance period (default: 1mo)")
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    tickers = args.tickers
    logger.info("Downloading %s for %s", args.period, tickers)

    data = yf.download(tickers, group_by='ticker' if len(tickers) == 1 else None, period=args.period, auto_adjust=True, progress=False)

    logger.info("Downloaded shape: %s", getattr(data, 'shape', None))
    if data.empty:
        logger.error("No data returned from yfinance — nothing to inspect")
        return

    print("--- HEAD OF RAW DATA ---")
    print(data.head())

    stacked = try_stack(data)

    print("\n--- HEAD OF STACKED DATA ---")
    print(stacked.head(10))

    print("\nStacked shape:", getattr(stacked, 'shape', None))


if __name__ == "__main__":
    main()
