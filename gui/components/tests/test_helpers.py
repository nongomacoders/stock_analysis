import pandas as pd
from components.navigation_helper import NavigationHelper
from components.zone_detector import ZoneDetector


def test_navigation_find_watchlist_widget_simple_chain():
    class FakeWatchlist:
        def get_adjacent_ticker(self, *a, **k):
            return None
        def get_ordered_tickers(self):
            return ['A', 'B']

    class FakeParent:
        def __init__(self, watchlist):
            self.watchlist = watchlist

    class FakeWindow:
        def __init__(self, parent):
            self.master = parent
            self.prev_btn = type('B', (), {'configure': lambda *a, **k: None})()
            self.next_btn = type('B', (), {'configure': lambda *a, **k: None})()

    watch = FakeWatchlist()
    parent = FakeParent(watch)
    win = FakeWindow(parent)
    nav = NavigationHelper(win)

    found = nav.find_watchlist_widget()
    assert found is watch
    # Should not raise
    nav.update_navigation_state()


def test_zone_detector_handles_exception(monkeypatch):
    zd = ZoneDetector()
    df = pd.DataFrame({'open':[], 'high':[], 'low':[], 'close':[]})

    def fake_detect(df_in, **kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr('core.utils.patterns.support_resistance.detect_support_resistance_zones', fake_detect)

    sup, res = zd.detect_zones(df, {})
    assert sup == [] and res == []


def test_zone_detector_filters_by_stop_and_target(monkeypatch):
    zd = ZoneDetector()
    df = pd.DataFrame({'open':[], 'high':[], 'low':[], 'close':[]})

    class FakeZone:
        def __init__(self, mid):
            self.mid = mid

    # Have the detection return several zones
    def fake_detect(df_in, **kwargs):
        return {'support': [FakeZone(10), FakeZone(20), FakeZone(30)], 'resistance': [FakeZone(15), FakeZone(25), FakeZone(35)]}

    # In trade mode pick_trade_levels will pick some zones; simulate picks outside and inside the bounds
    def fake_pick(zones, is_long, entry_price=None):
        # return support zone at 20 and resistance at 35 by default
        return FakeZone(20), FakeZone(35)

    monkeypatch.setattr('core.utils.patterns.support_resistance.detect_support_resistance_zones', fake_detect)
    monkeypatch.setattr('core.utils.patterns.support_resistance.pick_trade_levels', fake_pick)

    # Case 1: stop=12, target=30 (long) -> sup 20 is inside (kept), res 35 is > target (removed)
    sup, res = zd.detect_zones(df, {}, entry_price=15, target_price=30, stop_loss=12)
    assert sup == [(None, 20.0)]
    assert res == []

    # Case 2: stop=22, target=32 -> sup 20 is < stop (removed), res 35 > target (removed)
    # Filtering would remove everything; in this case we fall back to the original detected zones
    sup, res = zd.detect_zones(df, {}, entry_price=25, target_price=32, stop_loss=22)
    assert sup == [(None, 20.0)]
    assert res == [(None, 35.0)]

    # Case 3: pick_trade_levels doesn't find support but a support exists below entry
    # Simulate pick_trade_levels returning (None, None) but detect provides supports
    def fake_pick_none(zones, is_long, entry_price=None):
        return None, None

    monkeypatch.setattr('core.utils.patterns.support_resistance.pick_trade_levels', fake_pick_none)
    sup, res = zd.detect_zones(df, {}, entry_price=30, target_price=40, stop_loss=10)
    # Support list contained 10,20,30 -- we expect the closest below entry (20)
    assert sup == [(None, 20.0)]
    # Resistances were 15,25,35 -- closest above entry is 35
    assert res == [(None, 35.0)]
