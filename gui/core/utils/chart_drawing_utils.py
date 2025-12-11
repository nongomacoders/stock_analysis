from typing import List, Tuple, Optional, Any
import pandas as pd
import mplfinance as mpf
from matplotlib.axes import Axes
from matplotlib.lines import Line2D


def prepare_mpf_hlines(
    stored_hlines: List[Tuple[float, str, str]],
    extra_lines: Optional[Any] = None,
) -> Optional[dict]:
    """
    Build an mplfinance-compatible 'hlines' dict from:
      - stored_hlines: list of (price, color, label)
      - extra_lines: optional external specification (dict or list)

    Returns a dict suitable for mpf.plot(..., hlines=...) or None if no lines.
    """
    prices: List[float] = []
    colors: List[str] = []
    linestyles: List[str] = []
    linewidths: List[float] = []

    # 1) From stored horizontal lines
    for price, color, label in stored_hlines or []:
        prices.append(price)
        colors.append(color)
        # Default style
        lstyle = "--"
        lw = 1.5
        if label:
            lab = str(label).lower()
            if lab.startswith("support") or lab.startswith("resistance"):
                # Support & resistance use solid thicker lines
                lstyle = "-"
                lw = 2.6
        linestyles.append(lstyle)
        linewidths.append(lw)

    # 2) Merge any extra 'lines' argument from callers (if still used anywhere)
    if extra_lines is not None:
        if isinstance(extra_lines, dict):
            extra_prices = extra_lines.get("hlines", [])
            if isinstance(extra_prices, (list, tuple)):
                prices.extend(extra_prices)
        elif isinstance(extra_lines, (list, tuple)):
            prices.extend(extra_lines)

    # Nothing to draw
    if not prices:
        return None

    # Coerce all prices to plain floats and filter out bad values
    safe_prices: List[float] = []
    safe_colors: List[str] = []

    for i, p in enumerate(prices):
        try:
            fp = float(p)
        except Exception:
            continue

        safe_prices.append(fp)
        if i < len(colors):
            safe_colors.append(colors[i])

    if not safe_prices:
        return None

    # If we have a 1-to-1 list of colors, use it; otherwise let mplfinance pick one
    if safe_colors and len(safe_colors) == len(safe_prices):
        colors_for_mpf: Any = safe_colors
    else:
        colors_for_mpf = "r"

    # Build per-line style arrays to pass to mplfinance
    lstyles = []
    lwids = []
    for i, _ in enumerate(safe_prices):
        # If we have a per-line value use it else use default
        if i < len(linestyles):
            lstyles.append(linestyles[i])
        else:
            lstyles.append("--")
        if i < len(linewidths):
            lwids.append(linewidths[i])
        else:
            lwids.append(1.5)

    return {
        "hlines": safe_prices,
        "colors": colors_for_mpf,
        "linestyle": lstyles,
        "linewidths": lwids,
        "alpha": 0.7,
    }


def add_legend_for_hlines(ax: Axes, stored_hlines: List[Tuple[float, str, str]]) -> None:
    """
    Build a legend from stored_hlines (price, color, label) using dummy Line2D handles.
    Removes any previous legend first.
    """
    legend = getattr(ax, "legend_", None)
    if legend is not None:
        try:
            legend.remove()
        except Exception:
            pass

    if not stored_hlines:
        return

    handles: List[Line2D] = []
    for price, color, label in stored_hlines:
        if not label:
            continue
        linestyle = "--"
        linewidth = 1.5
        try:
            lab = str(label).lower()
            if lab.startswith("support") or lab.startswith("resistance"):
                linestyle = "-"
                linewidth = 2.6
        except Exception:
            pass
        handles.append(
            Line2D(
                [0],
                [0],
                color=color,
                linestyle=linestyle,
                linewidth=linewidth,
                label=label,
            )
        )

    if not handles:
        return

    try:
        ax.legend(handles=handles, loc="upper left", fontsize=8)
    except Exception:
        # If legend creation fails for any reason, just suppress it
        pass


def build_lines_from_state(
    entry_price: Optional[float],
    stop_loss: Optional[float],
    target_price: Optional[float],
    support_levels: Optional[List[tuple]] = None,
    resistance_levels: Optional[List[tuple]] = None,
):
    """Build a list of (price, color, label) tuples from the provided state.

    `support_levels` and `resistance_levels` are expected to be lists of
    (id_or_None, price) tuples.
    """
    lines = []
    try:
        if entry_price is not None:
            lines.append((entry_price, "blue", f"Entry: R{entry_price:.2f}"))
        if stop_loss is not None:
            lines.append((stop_loss, "red", f"Stop Loss: R{stop_loss:.2f}"))
        if target_price is not None:
            lines.append((target_price, "green", f"Target: R{target_price:.2f}"))
        if support_levels:
            for (_id, p) in support_levels:
                if p is not None:
                    lines.append((p, "green", f"Support: R{p:.2f}"))
        if resistance_levels:
            for (_id, p) in resistance_levels:
                if p is not None:
                    lines.append((p, "red", f"Resistance: R{p:.2f}"))
    except Exception:
        # Be robust: return what we have even on partial failures
        pass
    return lines


# Public chart drawing helpers for the application


def build_ma_addplots(
    df_source: Optional[pd.DataFrame],
    df_display: Optional[pd.DataFrame],
    ax: Axes,
) -> Optional[List[Any]]:
    """
    Build 50- and 200-day simple moving-average addplots.

    - Uses the last 300 calendar days from df_source (assumed daily OHLC in rands).
    - Computes daily SMAs and reindexes them to df_display.index so that the
      MAs line up with whatever resampling is used (3M/6M daily, 1Y weekly,
      5Y monthly, etc.).
    - Returns a list of mpf.make_addplot(...) objects or None if not possible.

    IMPORTANT for external-axes mode:
    - We must pass ax=<Axes> to make_addplot(), NOT panel=0, otherwise
      mplfinance will complain that addplot 'ax' kwargs are invalid.
    """
    if df_source is None or df_source.empty:
        return None
    if df_display is None or df_display.empty:
        return None
    if "Close" not in df_source.columns:
        return None
    if not isinstance(df_source.index, pd.DatetimeIndex):
        return None

    # Restrict to last 300 calendar days of source data
    end = df_source.index.max()
    start = end - pd.Timedelta(days=300)
    df_window = df_source.loc[start:end].copy()

    if df_window.empty:
        return None

    close = df_window["Close"].astype(float)

    # 50- and 200-day SMAs on *daily* data
    ma50 = close.rolling(window=50, min_periods=1).mean()
    ma200 = close.rolling(window=200, min_periods=1).mean()

    # Align the MAs to df_display.index (which might be weekly/monthly)
    ma50_resampled = ma50.reindex(df_display.index, method="pad")
    ma200_resampled = ma200.reindex(df_display.index, method="pad")

    if ma50_resampled.isna().all() and ma200_resampled.isna().all():
        return None

    addplots: List[Any] = []

    # NOTE: we attach them to the external Axes via ax=<Axes>, not panel=0
    addplots.append(
        mpf.make_addplot(ma50_resampled, width=0.9, color="tab:blue", ax=ax)
    )
    addplots.append(
        mpf.make_addplot(ma200_resampled, width=0.9, color="tab:orange", ax=ax)
    )

    return addplots if addplots else None
