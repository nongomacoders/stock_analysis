# tencent_nav_arb_engine.py
import argparse
import sys
from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt


# -----------------------------
# Robust yfinance close extractor
# -----------------------------
def yf_close(ticker: str, start: str) -> pd.Series:
    df = yf.download(
        ticker,
        start=start,
        auto_adjust=False,   # explicit to avoid future default changes
        progress=False,
        group_by="column"
    )

    if df is None or df.empty:
        raise RuntimeError(f"No data returned for {ticker}")

    # Some tickers return MultiIndex columns
    if isinstance(df.columns, pd.MultiIndex):
        # e.g. df["Close"] -> dataframe with one column per ticker
        close = df["Close"].iloc[:, 0]
    else:
        close = df["Close"]

    close = close.dropna()
    close.name = ticker
    return close


# -----------------------------
# Model config
# -----------------------------
@dataclass
class TencentLookthroughConfig:
    # Stakes
    prosus_tencent_stake: float = 0.228
    naspers_prosus_stake: float = 0.434

    # Shares (update when results / buybacks materially change)
    naspers_shares: int = 628_849_928

    # ADR ratio: 1 ADR equals how many local shares
    # NPSNY: 1 ADR = 0.25 NPN share (commonly used)
    npsny_adr_ratio: float = 0.25

    # If you add PROSY: set ratio; if unsure, leave None and engine will still run for NPSNY only
    pros_y_adr_ratio: Optional[float] = None  # set via CLI if you want PROSY

    # Tencent total ordinary shares outstanding (HK:0700) (update occasionally)
    tencent_shares_out: int = 9_200_000_000

    # TCEHY ADR to Tencent ordinary share factor
    # If 1 TCEHY = 1 Tencent ordinary share, keep 1.0
    # If your source indicates different, set accordingly.
    tcehy_adr_to_ord: float = 1.0

    @property
    def lookthrough(self) -> float:
        return self.prosus_tencent_stake * self.naspers_prosus_stake


# -----------------------------
# Engine
# -----------------------------
def build_nav_arb_df(
    start: str,
    tickers: Dict[str, str],
    cfg: TencentLookthroughConfig,
    z_window: int = 252,
) -> pd.DataFrame:
    """
    tickers expects keys:
      - "tencent": e.g. "TCEHY"
      - "naspers": e.g. "NPSNY"
      - optional "prosus": e.g. "PROSY"
    """
    tcehy = yf_close(tickers["tencent"], start)
    npsny = yf_close(tickers["naspers"], start)

    series = [tcehy, npsny]

    have_prosus = "prosus" in tickers and tickers["prosus"]
    if have_prosus:
        prosus = yf_close(tickers["prosus"], start)
        series.append(prosus)

    df = pd.concat(series, axis=1, join="inner").dropna()

    tencent_col = tickers["tencent"]
    naspers_col = tickers["naspers"]

    # -----------------------------------
    # Step 1: Tencent Market Cap (USD) from ADR price
    # mktcap_usd = TCEHY_price * (Tencent_shares_out / ADR_to_ord_adjustment)
    # If 1 ADR = 1 ord share: ADR_to_ord = 1.0, so shares_out_effective = shares_out
    shares_out_effective = cfg.tencent_shares_out / cfg.tcehy_adr_to_ord
    df["Tencent_MktCap_USD"] = df[tencent_col] * shares_out_effective

    # -----------------------------------
    # Step 2: Naspers lookthrough Tencent value (USD)
    df["Naspers_Lookthrough"] = cfg.lookthrough
    df["Naspers_Tencent_Value_USD"] = df["Tencent_MktCap_USD"] * df["Naspers_Lookthrough"]

    # -----------------------------------
    # Step 3: Tencent NAV per NPN share (USD)
    df["Tencent_NAV_per_NPN_USD"] = df["Naspers_Tencent_Value_USD"] / cfg.naspers_shares

    # -----------------------------------
    # Step 4: Tencent NAV per holdingco ADR (USD)
    df["Tencent_NAV_per_NPSNY_USD"] = df["Tencent_NAV_per_NPN_USD"] * cfg.npsny_adr_ratio

    # -----------------------------------
    # Step 5: Discounts
    df["Disc_NPSNY"] = 1.0 - (df[naspers_col] / df["Tencent_NAV_per_NPSNY_USD"])

    # -----------------------------------
    # Optional: Prosus ADR discount (if you provide ADR ratio + ticker)
    if have_prosus:
        prosus_col = tickers["prosus"]
        if cfg.prosy_adr_ratio is None:
            raise ValueError("You provided a prosus ticker but prosy_adr_ratio is None. Set it via CLI --prosy_adr_ratio")

        # Prosus stake in Tencent directly = prosus_tencent_stake
        df["Prosus_Tencent_Value_USD"] = df["Tencent_MktCap_USD"] * cfg.prosus_tencent_stake

        # You need Prosus shares outstanding to do true per-share NAV.
        # We avoid that dependency by converting Prosus Tencent value into a *synthetic* per-ADR NAV using a scale factor.
        # If you want true PROSY NAV, provide Prosus shares outstanding and PROSY ADR ratio.
        #
        # Practical workaround:
        # Compare NPSNY discount only (clean), and use PROSY only for relative price overlay unless shares are provided.
        #
        # So we compute a "relative discount proxy" using a fixed scale factor anchored on first date:
        # implied = alpha * Tencent_NAV_per_NPSNY where alpha fits PROSY on day0 if you want.
        # Better: supply Prosus shares outstanding and compute properly.
        #
        # For now: we compute PROSY discount PROPERLY only if user supplies prosus_shares.
        pass

    # -----------------------------------
    # Signals (NPSNY)
    df["Disc_NPSNY_MA"] = df["Disc_NPSNY"].rolling(z_window).mean()
    df["Disc_NPSNY_SD"] = df["Disc_NPSNY"].rolling(z_window).std()
    df["Z_NPSNY"] = (df["Disc_NPSNY"] - df["Disc_NPSNY_MA"]) / df["Disc_NPSNY_SD"]

    return df


def save_outputs(df: pd.DataFrame, out_prefix: str) -> None:
    # CSV
    csv_path = f"{out_prefix}_nav_arb.csv"
    df.to_csv(csv_path, index=True)

    # Plot: discount + MA
    plt.figure(figsize=(14, 6))
    plt.plot(df.index, df["Disc_NPSNY"], label="NPSNY discount")
    plt.plot(df.index, df["Disc_NPSNY_MA"], label="MA (z-window)")
    plt.title("NPSNY Tencent Look-through Discount (Market Cap Method)")
    plt.ylabel("Discount = 1 - Price / Tencent NAV")
    plt.xlabel("Date")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{out_prefix}_discount.png", dpi=150)
    plt.close()

    # Plot: z-score
    plt.figure(figsize=(14, 4))
    plt.plot(df.index, df["Z_NPSNY"], label="Z-score (discount)")
    plt.axhline(0.0, linestyle="--")
    plt.title("NPSNY Discount Z-score")
    plt.ylabel("Z")
    plt.xlabel("Date")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{out_prefix}_zscore.png", dpi=150)
    plt.close()

    print(f"Saved: {csv_path}")
    print(f"Saved: {out_prefix}_discount.png")
    print(f"Saved: {out_prefix}_zscore.png")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2023-01-01", help="Start date (YYYY-MM-DD). Use 2023-01-01 onward.")
    p.add_argument("--tencent", default="TCEHY")
    p.add_argument("--naspers", default="NPSNY")
    p.add_argument("--out", default="tencent_nav_arb_2023on")
    p.add_argument("--z_window", type=int, default=252)

    # Config overrides
    p.add_argument("--prosus_tencent_stake", type=float, default=0.228)
    p.add_argument("--naspers_prosus_stake", type=float, default=0.434)
    p.add_argument("--naspers_shares", type=int, default=628_849_928)
    p.add_argument("--npsny_adr_ratio", type=float, default=0.25)
    p.add_argument("--tencent_shares_out", type=int, default=9_200_000_000)
    p.add_argument("--tcehy_adr_to_ord", type=float, default=1.0)

    args = p.parse_args()

    cfg = TencentLookthroughConfig(
        prosus_tencent_stake=args.prosus_tencent_stake,
        naspers_prosus_stake=args.naspers_prosus_stake,
        naspers_shares=args.naspers_shares,
        npsny_adr_ratio=args.npsny_adr_ratio,
        tencent_shares_out=args.tencent_shares_out,
        tcehy_adr_to_ord=args.tcehy_adr_to_ord,
    )

    tickers = {"tencent": args.tencent, "naspers": args.naspers}

    df = build_nav_arb_df(
        start=args.start,
        tickers=tickers,
        cfg=cfg,
        z_window=args.z_window,
    )

    save_outputs(df, args.out)


if __name__ == "__main__":
    sys.exit(main())
