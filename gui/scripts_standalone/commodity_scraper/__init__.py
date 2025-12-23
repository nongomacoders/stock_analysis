"""
Compatibility package: `scripts_standalone.commodity_scraper`.

This package exists to preserve the historical package name `commodity_scraper`.
The actual implementation lives in `scripts_standalone/commodity_fx_scraper/`.
"""
# Intentionally minimal; the real work is done in `runner.py` below.
__all__ = ["runner"]
