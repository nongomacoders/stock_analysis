import pytest
from core.utils.patterns.support_resistance import Zone, pick_trade_levels


def mk_zone(kind, mid, score=1.0):
    return Zone(kind=kind, low=mid - 0.5, high=mid + 0.5, mid=float(mid), touches=3, tests=0, rejections=0, last_touch_idx=0, score=score)


def test_pick_trade_levels_long_with_stop_target():
    supports = [mk_zone('support', 10, 2.0), mk_zone('support', 20, 1.5), mk_zone('support', 30, 1.0)]
    resistances = [mk_zone('resistance', 15, 2.0), mk_zone('resistance', 25, 1.2), mk_zone('resistance', 35, 0.9)]

    # Long trade: entry=25, stop=12, target=32
    sup, res = pick_trade_levels({'support': supports, 'resistance': resistances}, True, entry_price=25, stop_loss=12, target_price=32)
    # Support should be between stop (12) and entry (25) -> candidates 20, support top candidate is 20 (highest mid)
    assert sup is not None and sup.mid == 20.0
    # Resistance should be between entry (25) and target (32) -> candidate 35 is outside, 25 is inside
    assert res is not None and res.mid == 25.0


def test_pick_trade_levels_short_with_stop_target():
    supports = [mk_zone('support', 10, 2.0), mk_zone('support', 20, 1.5), mk_zone('support', 30, 1.0)]
    resistances = [mk_zone('resistance', 15, 2.0), mk_zone('resistance', 25, 1.2), mk_zone('resistance', 35, 0.9)]

    # Short trade: entry=20, stop=40, target=12
    res, sup = pick_trade_levels({'support': supports, 'resistance': resistances}, False, entry_price=20, stop_loss=40, target_price=12)
    # Resistance between entry (20) and stop (40) -> candidates 25 and 35 -> pick best (highest score) which is 25
    assert res is not None and res.mid == 25.0
    # Support between target (12) and entry (20) -> candidate 10 is outside, 20 is boundary -> expect 20
    assert sup is not None and sup.mid == 20.0
