from decimal import Decimal
from gui.core.utils.technical_utils import price_from_db, build_saved_levels_from_row


def test_price_from_db_none():
    assert price_from_db(None) is None


def test_price_from_db_int():
    assert price_from_db(12345) == 123.45


def test_price_from_db_decimal():
    assert price_from_db(Decimal('100')) == 1.0


def test_build_saved_levels_from_row():
    row = {'entry_price': 100, 'stop_loss': 50, 'target_price': 200}
    levels = build_saved_levels_from_row(row)
    assert isinstance(levels, list)
    assert len(levels) == 3
    assert levels[0][0] == 1.0  # entry
    assert levels[1][0] == 0.5  # stop
    assert levels[2][0] == 2.0  # target


def test_build_saved_levels_skips_none():
    row = {'entry_price': None, 'stop_loss': 250, 'target_price': None}
    levels = build_saved_levels_from_row(row)
    assert len(levels) == 1
    assert levels[0][0] == 2.5
