"""
Compatibility runner shim for `commodity_scraper.runner`.
Delegates to `commodity_fx_scraper.runner` where the implementation now lives.
"""
from scripts_standalone.commodity_fx_scraper.runner import run

__all__ = ["run"]
