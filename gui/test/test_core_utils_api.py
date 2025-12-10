import importlib
import unittest


class CoreUtilsAPITests(unittest.TestCase):
    def test_public_api_all(self):
        core_utils = importlib.import_module("gui.core.utils")
        expected = set(["prepare_mpf_hlines", "add_legend_for_hlines", "prepare_df_source"])
        # __all__ should contain exactly the expected exported names
        self.assertEqual(set(getattr(core_utils, "__all__", [])), expected)

    def test_internal_helpers_not_exported(self):
        core_utils = importlib.import_module("gui.core.utils")
        # The previously public add_axhline must not be exported
        self.assertFalse(hasattr(core_utils, "add_axhline"))
        # calculate_days_to_event is private now (starts with underscore) and should NOT be in core.utils
        self.assertFalse(hasattr(core_utils, "calculate_days_to_event"))

    def test_private_exists_in_module(self):
        dates_mod = importlib.import_module("gui.core.utils.dates")
        # The helper exists but is private (leading underscore)
        self.assertTrue(hasattr(dates_mod, "_calculate_days_to_event"))


if __name__ == "__main__":
    unittest.main()
