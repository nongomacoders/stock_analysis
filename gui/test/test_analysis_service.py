import asyncio
import os
import sys
import unittest
from unittest.mock import patch

from gui.components.analysis_service import fetch_analysis, delete_price_level


class AnalysisServiceTests(unittest.TestCase):
    def test_fetch_analysis_with_watchlist(self):
        async def fake_fetch(query, *args):
            if 'FROM watchlist w' in query:
                return [
                    {
                        'entry_price': 10000,
                        'target_price': 20000,
                        'stop_loss': 9000,
                        'status': 'Pre-Trade',
                        'strategy': 'test strat',
                        'support_ids': [1],
                        'support_prices': [8000],
                        'resistance_ids': [2],
                        'resistance_prices': [21000],
                    }
                ]
            return []

        with patch('components.analysis_service.DBEngine.fetch', fake_fetch):
            row = asyncio.run(fetch_analysis('TICK'))
            self.assertIsNotNone(row)
            self.assertEqual(row.get('entry_price'), 10000)
            self.assertIn('support_ids', row)

    def test_fetch_analysis_fallback(self):
        async def fake_fetch(query, *args):
            if 'FROM watchlist w' in query:
                return []
            if 'FROM stock_analysis sa' in query:
                return [
                    {
                        'strategy': 'fallback strat',
                        'support_ids': [3],
                        'support_prices': [12000],
                        'resistance_ids': [4],
                        'resistance_prices': [16000],
                    }
                ]
            return []

        with patch('components.analysis_service.DBEngine.fetch', fake_fetch):
            row = asyncio.run(fetch_analysis('TICK'))
            self.assertIsNotNone(row)
            self.assertEqual(row.get('strategy'), 'fallback strat')

    def test_delete_price_level(self):
        called = {}

        async def fake_execute(query, *args):
            called['q'] = query
            called['args'] = args
            return 'DELETE 1'

        with patch('components.analysis_service.DBEngine.execute', fake_execute):
            ok = asyncio.run(delete_price_level(123))
            self.assertTrue(ok)
            self.assertIn('DELETE FROM public.stock_price_levels', called['q'])


if __name__ == '__main__':
    unittest.main()
