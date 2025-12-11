import unittest
import os
import sys

from gui.components.watchlist import get_adjacent_ticker_from_list


class WatchlistNavTests(unittest.TestCase):
    def test_adjacent_ticker_next(self):
        l = ['AAA', 'BBB', 'CCC']
        self.assertEqual(get_adjacent_ticker_from_list('AAA', l, 1), 'BBB')
        self.assertEqual(get_adjacent_ticker_from_list('CCC', l, 1), 'AAA')

    def test_adjacent_ticker_prev(self):
        l = ['AAA', 'BBB', 'CCC']
        self.assertEqual(get_adjacent_ticker_from_list('AAA', l, -1), 'CCC')
        self.assertEqual(get_adjacent_ticker_from_list('BBB', l, -1), 'AAA')

    def test_empty_or_missing(self):
        self.assertIsNone(get_adjacent_ticker_from_list('X', [], 1))
        self.assertIsNone(get_adjacent_ticker_from_list('Z', ['A'], 1))


if __name__ == '__main__':
    unittest.main()
