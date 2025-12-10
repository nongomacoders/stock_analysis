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


def test_build_saved_levels_includes_support_and_resistance():
    row = {'entry_price': 100, 'stop_loss': 50, 'target_price': 200, 'support_price': 80, 'resistance_price': 220}
    levels = build_saved_levels_from_row(row)
    assert len(levels) == 5
    # positions: entry, stop, target, support, resistance
    assert levels[3][0] == 0.8
    assert levels[4][0] == 2.2


def test_build_saved_levels_includes_support_resistance():
    row = {
        'entry_price': 100,
        'stop_loss': 50,
        'target_price': 200,
        'support_price': 80,
        'resistance_price': 220,
    }
    levels = build_saved_levels_from_row(row)
    # entry, stop, target, support, resistance
    assert len(levels) == 5
    assert any(l[2].startswith('Support') for l in levels)
    assert any(l[2].startswith('Resistance') for l in levels)
