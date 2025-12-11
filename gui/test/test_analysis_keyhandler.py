import os
import sys
import unittest
from types import SimpleNamespace
from gui.components.analysis_keyhandler import AnalysisKeyHandler


class DummyChart:
    def has_focus(self):
        return True

    def get_cursor_y(self):
        return 11.2222


class DummyPanel:
    def __init__(self):
        self.levels_set = False
        self.values_set = False

    def set_levels(self, support=None, resistance=None):
        self.levels_set = (support, resistance)

    def set_values(self, **kwargs):
        self.values_set = kwargs


class DummyDrawer:
    def __init__(self):
        self.last_lines = None

    def draw(self, entry, stop, target, support_levels, resistance_levels):
        self.last_lines = (entry, stop, target, support_levels, resistance_levels)


class AnalysisKeyHandlerTests(unittest.TestCase):
    def test_handle_support_key(self):
        win = SimpleNamespace()
        win.chart = DummyChart()
        win.analysis_panel = DummyPanel()
        win.support_levels = []
        win.resistance_levels = []
        win.entry_price = None
        win.stop_loss = None
        win.target_price = None
        drawer = DummyDrawer()
        handler = AnalysisKeyHandler(win, drawer)
        event = SimpleNamespace(char='f')
        handled = handler.handle_key(event)
        self.assertTrue(handled)
        # support should be appended
        self.assertEqual(len(win.support_levels), 1)
        self.assertIsNotNone(drawer.last_lines)

    def test_handle_entry_key(self):
        win = SimpleNamespace()
        win.chart = DummyChart()
        win.analysis_panel = DummyPanel()
        win.support_levels = []
        win.resistance_levels = []
        win.entry_price = None
        win.stop_loss = None
        win.target_price = None
        drawer = DummyDrawer()
        handler = AnalysisKeyHandler(win, drawer)
        event = SimpleNamespace(char='e')
        handled = handler.handle_key(event)
        self.assertTrue(handled)
        self.assertIsNotNone(win.entry_price)
        self.assertIsNotNone(drawer.last_lines)


if __name__ == '__main__':
    unittest.main()
