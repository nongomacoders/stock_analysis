import logging
from typing import Any, Dict, Tuple, List, Optional

from core.utils.patterns.support_resistance import (
    detect_support_resistance_zones,
    pick_trade_levels,
)

logger = logging.getLogger(__name__)


class ZoneDetector:
    """
    Encapsulate zone detection logic for TechnicalAnalysisWindow.

    Returns:
      detected_support:    List[Tuple[None, float]]  -> (handle, price)
      detected_resistance: List[Tuple[None, float]]  -> (handle, price)

    Notes:
    - We do NOT mutate the UI settings dict.
    - Fix 1: When entry_price is present, we increase max_zones_each internally
      to avoid "no valid resistance above entry" situations.
    """

    def __init__(self):
        pass

    def detect_zones(
        self,
        df,
        settings: Dict[str, Any],
        entry_price: Optional[float] = None,
        target_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
    ) -> Tuple[List[Tuple[None, float]], List[Tuple[None, float]]]:
        try:
            # Copy settings so UI state is not mutated
            local_settings = dict(settings or {})

            # FIX 1: enlarge candidate pool when in trade context
            if entry_price is not None:
                # Tune max_zones_each: 8 is a good practical default.
                base = int(local_settings.get("max_zones_each", 2) or 2)
                local_settings["max_zones_each"] = max(base, 8)
                # Ensure we examine more history for long-term supports
                base_lb = int(local_settings.get("lookback", 100) or 100)
                local_settings["lookback"] = max(base_lb, 300)

            zones = detect_support_resistance_zones(df, **local_settings)

            # Determine is_long if entry/target provided
            is_long = True
            if entry_price is not None and target_price is not None:
                is_long = float(target_price) >= float(entry_price)

            # If we have an entry price, select trade-logical levels
            if entry_price is not None:
                sup_zone, res_zone = pick_trade_levels(
                    zones,
                    is_long=is_long,
                    entry_price=float(entry_price),
                    stop_loss=float(stop_loss) if stop_loss is not None else None,
                    target_price=float(target_price) if target_price is not None else None,
                )

                # If pick_trade_levels couldn't find a zone, try to pick a sensible fallback
                # from the full detected lists (zones variable). This increases robustness
                # and avoids the UI ending up with no visible support/res when reasonable
                # candidates exist.
                if sup_zone is None:
                    sup_candidates = [s for s in zones.get("support", []) if s.mid < float(entry_price)]
                    if not sup_candidates and target_price is not None:
                        sup_candidates = [s for s in zones.get("support", []) if s.mid < float(target_price)]
                    if sup_candidates:
                        # pick the closest support below entry/target (highest mid)
                        sup_zone = max(sup_candidates, key=lambda s: s.mid)

                if res_zone is None:
                    res_candidates = [r for r in zones.get("resistance", []) if r.mid > float(entry_price)]
                    if not res_candidates and target_price is not None:
                        res_candidates = [r for r in zones.get("resistance", []) if r.mid > float(target_price)]
                    if res_candidates:
                        # pick the closest resistance above entry/target (lowest mid)
                        res_zone = min(res_candidates, key=lambda r: r.mid)

                detected_support = [(None, float(sup_zone.mid))] if sup_zone else []
                detected_resistance = [(None, float(res_zone.mid))] if res_zone else []

                logger.info(
                    "[ZoneDetector] Filtered zones for %s trade: sup=%s, res=%s (max_zones_each=%s)",
                    "LONG" if is_long else "SHORT",
                    f"R{sup_zone.mid:.2f}" if sup_zone else "None",
                    f"R{res_zone.mid:.2f}" if res_zone else "None",
                    local_settings.get("max_zones_each"),
                )
            else:
                # No entry context: return top zones as-is
                detected_support = [(None, float(z.mid)) for z in zones.get("support", [])]
                detected_resistance = [(None, float(z.mid)) for z in zones.get("resistance", [])]

                # If a stop+target band is supplied, filter the candidates to that band.
                try:
                    if stop_loss is not None and target_price is not None:
                        low = min(float(stop_loss), float(target_price))
                        high = max(float(stop_loss), float(target_price))

                        def in_range(item):
                            # Inclusive check to avoid losing values due to rounding
                            p = float(item[1])
                            return low <= p <= high

                        orig_sup = list(detected_support)
                        orig_res = list(detected_resistance)

                        detected_support = [it for it in detected_support if in_range(it)]
                        detected_resistance = [it for it in detected_resistance if in_range(it)]

                        logger.info(
                            "[ZoneDetector] Applied stop/target filter (no-entry context): low=%.2f high=%.2f, sup %d->%d, res %d->%d",
                            low,
                            high,
                            len(orig_sup),
                            len(detected_support),
                            len(orig_res),
                            len(detected_resistance),
                        )

                        # If filtering removed everything, fall back to the original detected zones
                        if not detected_support and not detected_resistance and (orig_sup or orig_res):
                            logger.info(
                                "[ZoneDetector] Filtering removed all zones — falling back to original detected zones (no-entry context)"
                            )
                            detected_support = orig_sup
                            detected_resistance = orig_res
                except Exception:
                    logger.exception("Failed applying stop/target filtering")

            return detected_support, detected_resistance

        except Exception:
            logger.exception("Zone detection failed")
            return [], []
