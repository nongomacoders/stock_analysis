import os
import sys
import unittest
from types import SimpleNamespace
from gui.components.analysis_drawer import AnalysisDrawer


class DummyChart:
    def __init__(self):
        self._lines = None
        self._after = None
        self.after_calls = []

    def set_horizontal_lines(self, lines):
        self._lines = list(lines)

    def get_last_lines(self):
        return self._lines

    # Simple after implementation: call immediately and store the call
    def after(self, ms, func, *args):
        self.after_calls.append((ms, func, args))
        func(*args)
        return 'id'

    def after_cancel(self, _id):
        # no-op
        return None
    def clear_horizontal_lines(self):
        self._lines = None


class AnalysisDrawerTests(unittest.TestCase):
    def test_draw_and_clear(self):
        chart = DummyChart()
        drawer = AnalysisDrawer(chart, debounce_ms=0)
        # Simple state
        drawer.draw(10.0, 9.0, 12.0, [(None, 8.5)], [(None, 13.5)])
        lines = chart.get_last_lines()
        self.assertTrue(any(l[2].startswith('Entry') for l in lines))
        # Clear
        drawer.clear()
        self.assertIsNone(chart.get_last_lines())


if __name__ == '__main__':
    unittest.main()
