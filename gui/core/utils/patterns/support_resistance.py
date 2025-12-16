from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Literal, Optional, List

try:
    from scipy.signal import find_peaks
except ImportError as e:
    raise ImportError("scipy is required: pip install scipy") from e


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


@dataclass
class Zone:
    kind: Literal["support", "resistance"]
    low: float
    high: float
    mid: float
    touches: int
    tests: int
    rejections: int
    last_touch_idx: int
    score: float


def _cluster_levels(levels: np.ndarray, tol: float) -> List[tuple[float, float, float, int]]:
    """
    Cluster 1D prices into zones using a simple greedy merge.
    Returns list of (low, high, mid, count).
    """
    if len(levels) == 0:
        return []

    levels = np.sort(levels)
    clusters = []
    cur = [levels[0]]

    for x in levels[1:]:
        if abs(x - np.mean(cur)) <= tol:
            cur.append(x)
        else:
            low, high = float(np.min(cur)), float(np.max(cur))
            mid = float(np.mean(cur))
            clusters.append((low, high, mid, len(cur)))
            cur = [x]

    low, high = float(np.min(cur)), float(np.max(cur))
    mid = float(np.mean(cur))
    clusters.append((low, high, mid, len(cur)))
    return clusters


def count_tests_and_rejections(d: pd.DataFrame, zlow: float, zhigh: float, kind: str):
    """
    Returns (tests, rejections)
    - test: candle range overlaps zone
    - rejection: test + close decisively away from zone
    """
    high = d["high"].astype(float).values
    low = d["low"].astype(float).values
    close = d["close"].astype(float).values

    tests_mask = (high >= zlow) & (low <= zhigh)

    if kind == "resistance":
        rej_mask = tests_mask & (close < zlow)
    elif kind == "support":
        rej_mask = tests_mask & (close > zhigh)
    else:
        raise ValueError("kind must be 'support' or 'resistance'")

    return int(np.sum(tests_mask)), int(np.sum(rej_mask))


def detect_support_resistance_zones(
    df: pd.DataFrame,
    *,
    lookback: int = 100,
    peak_distance: int = 4,
    peak_prominence: Optional[float] = None,
    atr_period: int = 14,
    zone_atr_mult: float = 0.8,
    min_touches: int = 2,
    max_zones_each: int = 1,
    recency_weight: float = 0.35,
    rejection_weight: float = 0.75,
    test_lookback: int = 120,
) -> dict[str, list[Zone]]:
    """
    Support/resistance zones using swing highs/lows + ATR-based clustering.

    Parameters:
    - lookback: bars to consider from the end.
    - peak_distance: minimum separation between swing points (in bars).
    - peak_prominence: optional price prominence filter for peaks.
    - zone_atr_mult: tolerance = ATR * zone_atr_mult (controls zone width/merging).
    - min_touches: minimum swing points inside a zone to keep it.
    - max_zones_each: return top N supports and resistances.
    - recency_weight: how much to boost zones touched recently (0..1).
    - rejection_weight: how much rejections matter vs swing touches.
    - test_lookback: how many most-recent bars to count rejections on.

    Returns:
    { "support": [Zone...], "resistance": [Zone...] }
    """
    required = {"high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"df missing columns: {missing}")

    d = df.copy()
    d = d.tail(lookback).reset_index(drop=True)

    a = atr(d, period=atr_period)
    tol_series = (a * zone_atr_mult).fillna(method="bfill").fillna(method="ffill")
    # Use a single tolerance representative of the window
    tol = float(np.nanmedian(tol_series.values))
    if not np.isfinite(tol) or tol <= 0:
        # fallback: small fraction of price
        tol = float(np.nanmedian(d["close"].values) * 0.005)

    highs = d["high"].astype(float).values
    lows = d["low"].astype(float).values

    peak_kwargs = {"distance": peak_distance}
    if peak_prominence is not None:
        peak_kwargs["prominence"] = peak_prominence

    high_idx, _ = find_peaks(highs, **peak_kwargs)
    low_idx, _ = find_peaks(-lows, **peak_kwargs)

    swing_high_prices = highs[high_idx]
    swing_low_prices = lows[low_idx]

    res_clusters = _cluster_levels(swing_high_prices, tol=tol)
    sup_clusters = _cluster_levels(swing_low_prices, tol=tol)

    # Build zones + score
    def build_zones(kind: Literal["support", "resistance"], clusters, swing_idx, swing_prices):
        zones: list[Zone] = []
        last_i = len(d) - 1
        for (zlow, zhigh, zmid, count) in clusters:
            if count < min_touches:
                continue

            # Last touch = most recent swing within zone bounds
            within = np.where((swing_prices >= zlow - 1e-12) & (swing_prices <= zhigh + 1e-12))[0]
            if len(within) == 0:
                continue
            touch_positions = swing_idx[within]
            last_touch = int(np.max(touch_positions))
            # Recency boost: 1 when touched on last bar, ~0 when far away
            recency = 1.0 - (last_i - last_touch) / max(1, last_i)
            recency = float(np.clip(recency, 0.0, 1.0))

            # Measure interaction with the zone on actual candles (not just swing points)
            window = d.tail(min(test_lookback, len(d)))
            tests, rejections = count_tests_and_rejections(window, zlow, zhigh, kind)

            # Score: swing touches are "structure", rejections are "confirmation"
            score = float(count) * (1.0 + recency_weight * recency) + rejection_weight * float(rejections)

            zones.append(
                Zone(
                    kind=kind,
                    low=float(zlow),
                    high=float(zhigh),
                    mid=float(zmid),
                    touches=int(count),
                    tests=tests,
                    rejections=rejections,
                    last_touch_idx=last_touch,
                    score=score,
                )
            )

        zones.sort(key=lambda z: z.score, reverse=True)
        return zones[:max_zones_each]

    resistance = build_zones("resistance", res_clusters, high_idx, swing_high_prices)
    support = build_zones("support", sup_clusters, low_idx, swing_low_prices)

    return {"support": support, "resistance": resistance}


def pick_trade_levels(zones: dict, is_long: bool, entry_price: Optional[float] = None):
    """
    Pick the best support/resistance levels that make logical sense for a trade.
    
    For long trades:
      - Support must be BELOW entry_price
      - Resistance must be ABOVE entry_price
    For short trades:
      - Resistance must be ABOVE entry_price
      - Support must be BELOW entry_price (and below resistance)
    
    Returns (support_zone, resistance_zone) or (None, None) if not available.
    """
    supports = zones.get("support", [])
    resistances = zones.get("resistance", [])

    if not supports and not resistances:
        return None, None

    if is_long:
        # For long: support below entry, resistance above entry
        if entry_price is not None:
            sup = next((s for s in supports if s.mid < entry_price), None)
            res = next((r for r in resistances if r.mid > entry_price), None)
        else:
            # Fallback: just ensure resistance > support
            sup = supports[0] if supports else None
            res = next((r for r in resistances if sup and r.mid > sup.mid), None) if resistances else None
        return sup, res
    else:
        # For short: resistance above entry, support below entry (and below resistance)
        if entry_price is not None:
            res = next((r for r in resistances if r.mid > entry_price), None)
            sup = next((s for s in supports if s.mid < entry_price), None)
        else:
            res = resistances[0] if resistances else None
            sup = next((s for s in supports if res and s.mid < res.mid), None) if supports else None
        return sup, res


def zones_to_dataframe(zones: dict[str, list[Zone]]) -> pd.DataFrame:
    rows = []
    for side, zs in zones.items():
        for z in zs:
            rows.append(
                {
                    "type": side,
                    "low": z.low,
                    "high": z.high,
                    "mid": z.mid,
                    "touches": z.touches,
                    "tests": z.tests,
                    "rejections": z.rejections,
                    "last_touch_idx": z.last_touch_idx,
                    "score": z.score,
                }
            )
    return pd.DataFrame(rows).sort_values(["type", "score"], ascending=[True, False]).reset_index(drop=True)
