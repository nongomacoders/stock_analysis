import unittest
import os
import sys
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gui.components.technical_analysis_window import TechnicalAnalysisWindow


class TechAnalysisNavigationTests(unittest.TestCase):
    def setUp(self):
        # Create a minimal tk root for widget parenting
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_next_prev_navigation(self):
        # stub out load_chart/load_existing_data to avoid DB interactions
        with patch.object(TechnicalAnalysisWindow, 'load_chart', lambda self, *_: None), \
             patch.object(TechnicalAnalysisWindow, 'load_existing_data', lambda self: None):
            win = TechnicalAnalysisWindow(self.root, 'AAA', async_run_bg=lambda coro, callback=None: None)
            # Set a fake master (watchlist) with get_adjacent_ticker
            # Test case when parent doesn't implement get_adjacent_ticker directly
            fake_parent = SimpleNamespace()
            fake_watchlist = SimpleNamespace()
            def adj_w(ticker, direction=1):
                if direction == 1:
                    return 'BBB'
                return 'ZZZ'
            fake_watchlist.get_adjacent_ticker = adj_w
            fake_watchlist.get_ordered_tickers = lambda: ['AAA','BBB','CCC']
            selected = {}
            fake_watchlist.on_select = lambda t: selected.update({'t': t})
            fake_parent.watchlist = fake_watchlist
            win.master = fake_parent

            # Test next
            win._on_next_ticker()
            self.assertEqual(win.ticker, 'BBB')
            # Ensure watchlist on_select was called
            self.assertEqual(selected.get('t'), 'BBB')
            # Test prev
            win._on_prev_ticker()
            self.assertEqual(win.ticker, 'ZZZ')
            # Ensure watchlist on_select was called for prev
            self.assertEqual(selected.get('t'), 'ZZZ')

    def test_prev_next_buttons_state(self):
        # Verify prev/next buttons are disabled when watchlist has 0 or 1 items
        with patch.object(TechnicalAnalysisWindow, 'load_chart', lambda self, *_: None), \
             patch.object(TechnicalAnalysisWindow, 'load_existing_data', lambda self: None):
            win = TechnicalAnalysisWindow(self.root, 'AAA', async_run_bg=lambda coro, callback=None: None)
            # Simulate parent watchlist with single ticker
            fake_parent = SimpleNamespace()
            fake_watchlist = SimpleNamespace()
            fake_watchlist.get_ordered_tickers = lambda: ['AAA']
            fake_parent.watchlist = fake_watchlist
            win.master = fake_parent

            # Force update state
            win._update_navigation_state()
            self.assertEqual(str(win.prev_btn['state']), 'disabled')
            self.assertEqual(str(win.next_btn['state']), 'disabled')

            # Now simulate multiple tickers
            fake_watchlist.get_ordered_tickers = lambda: ['AAA', 'BBB', 'CCC']
            win._update_navigation_state()
            self.assertEqual(str(win.prev_btn['state']), 'normal')
            self.assertEqual(str(win.next_btn['state']), 'normal')


if __name__ == '__main__':
    unittest.main()
