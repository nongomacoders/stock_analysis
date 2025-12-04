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


if __name__ == "__main__":
    unittest.main()
