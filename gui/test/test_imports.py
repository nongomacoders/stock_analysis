import importlib
import unittest


class ImportTests(unittest.TestCase):
    def test_components_imports(self):
        # Ensure core components can be imported cleanly
        mod_taw = importlib.import_module("components.technical_analysis_window")
        self.assertTrue(hasattr(mod_taw, "TechnicalAnalysisWindow"))

        mod_bc = importlib.import_module("components.base_chart")
        self.assertTrue(hasattr(mod_bc, "BaseChart"))

        mod_cw = importlib.import_module("components.chart_window")
        self.assertTrue(hasattr(mod_cw, "ChartWindow"))

        mod_pw = importlib.import_module("components.portfolio_window")
        self.assertTrue(hasattr(mod_pw, "PortfolioWindow"))

        mod_ws = importlib.import_module("components.watchlist_sorting")
        self.assertTrue(hasattr(mod_ws, "sort_watchlist_records"))
        self.assertTrue(hasattr(mod_ws, "sort_treeview_column"))

    def test_core_utils_no_add_axhline(self):
        # The top-level package should NOT expose add_axhline
        core_utils = importlib.import_module("core.utils")
        self.assertFalse(hasattr(core_utils, "add_axhline"), "core.utils should not export add_axhline")

        # The chart_drawing_utils module should no longer expose add_axhline
        cdu = importlib.import_module("core.utils.chart_drawing_utils")
        self.assertFalse(hasattr(cdu, "add_axhline"), "add_axhline should not exist in chart_drawing_utils anymore")

    def test_core_utils_helpers_present(self):
        cdu = importlib.import_module("core.utils.chart_drawing_utils")
        self.assertTrue(hasattr(cdu, "prepare_mpf_hlines"))
        self.assertTrue(hasattr(cdu, "add_legend_for_hlines"))

    def test_watchlist_fetch_includes_peg(self):
        import inspect
        mod = importlib.import_module('modules.data.watchlist')
        src = inspect.getsource(mod.fetch_watchlist_data)
        self.assertIn('lv.peg_ratio_historical as peg_ratio', src)
        # Confirm the sorting helper supports 'PEG' column
        mod_sort = importlib.import_module('components.watchlist_sorting')
        sort_src = inspect.getsource(mod_sort.sort_treeview_column)
        self.assertIn('col == "PEG"', sort_src)

    def test_stock_price_levels_migration_updates(self):
        # Ensure the migration adds entry/target/stop_loss and is_long columns,
        # sets price_level to NULL, and copies values from watchlist.
        import inspect
        migrate_path = 'gui/core/db/migrations/drop_notes_isignored_and_uq_from_stock_price_levels.sql'
        with open(migrate_path, 'r', encoding='utf-8') as f:
            contents = f.read()
        self.assertIn('ADD COLUMN IF NOT EXISTS is_long', contents)
        self.assertIn('DROP CONSTRAINT IF EXISTS uq_ticker_price', contents)
        # Should include the UPDATE nulling price_level
        self.assertIn('UPDATE public.stock_price_levels SET price_level = NULL', contents)
        self.assertIn('INSERT INTO public.stock_price_levels (ticker, price_level, level_type', contents)
        self.assertIn('DELETE FROM public.stock_price_levels WHERE price_level IS NULL', contents)
        self.assertIn('CREATE UNIQUE INDEX IF NOT EXISTS stock_price_levels_unique_entry', contents)
        self.assertIn('CREATE UNIQUE INDEX IF NOT EXISTS stock_price_levels_unique_target', contents)
        self.assertIn('CREATE UNIQUE INDEX IF NOT EXISTS stock_price_levels_unique_stoploss', contents)

    def test_stock_price_levels_schema_changes(self):
        import inspect
        # Ensure jse.sql no longer has notes or is_ignored_on_scan for stock_price_levels
        import importlib, pkgutil
        sql_path = 'gui/architecture/jse.sql'
        with open(sql_path, 'r', encoding='utf-8') as f:
            contents = f.read()
        # Extract block for CREATE TABLE public.stock_price_levels
        start = contents.find('CREATE TABLE IF NOT EXISTS public.stock_price_levels')
        self.assertNotEqual(start, -1, 'stock_price_levels table not found in jse.sql')
        block_start = contents.find('(', start)
        block_end = contents.find(');', block_start)
        table_block = contents[block_start:block_end]
        # The specific columns should no longer be present in this table block
        self.assertNotIn('notes text', table_block)
        self.assertNotIn('is_ignored_on_scan boolean', table_block)
        # The UNIQUE constraint should not exist in this table block
        self.assertNotIn('CONSTRAINT uq_ticker_price', table_block)
        # The new price columns should NOT exist (we now use price_level + level_type)
        self.assertNotIn('entry_price numeric(12, 2)', table_block)
        self.assertNotIn('target_price numeric(12, 2)', table_block)
        self.assertNotIn('stop_loss numeric(12, 2)', table_block)
        # is_long should exist
        self.assertIn('is_long boolean', table_block)
        # Check constraint for level_type should exist
        self.assertIn('CHECK (level_type IN (', table_block)
        self.assertIn('stock_price_levels_level_type_check', table_block)
        # Schema should include unique index definitions for entry/target/stop_loss
        self.assertIn('CREATE UNIQUE INDEX IF NOT EXISTS stock_price_levels_unique_entry', contents)
        self.assertIn('CREATE UNIQUE INDEX IF NOT EXISTS stock_price_levels_unique_target', contents)
        self.assertIn('CREATE UNIQUE INDEX IF NOT EXISTS stock_price_levels_unique_stoploss', contents)


if __name__ == "__main__":
    unittest.main()
