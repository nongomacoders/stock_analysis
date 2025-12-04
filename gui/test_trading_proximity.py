from core.utils.trading import get_proximity_status


def test_long_proximity():
    # stop critical (<= stop * 1.02)
    text, style = get_proximity_status(102, 110, 100, 200, is_long=True)
    assert "Hitting Stop" in text and style == "danger"

    # near entry (>= entry and <= entry*1.02)
    text, style = get_proximity_status(101, 100, 90, 200, is_long=True)
    assert "Near Entry" in text and style == "success"

    # near target (>= target * 0.98)
    text, style = get_proximity_status(198, 100, 90, 200, is_long=True)
    assert "Near Target" in text and style == "info"

    # default distance outside proximity -> should be blank
    text, style = get_proximity_status(95, 100, 90, 200, is_long=True)
    assert text == "" and style == "secondary"


def test_short_proximity():
    # stop critical (>= stop * 0.98)
    text, style = get_proximity_status(103, 100, 105, 80, is_long=False)
    assert "Hitting Stop" in text and style == "danger"

    # near entry (<= entry and >= entry * 0.98)
    text, style = get_proximity_status(99, 100, 105, 80, is_long=False)
    assert "Near Entry" in text and style == "success"

    # near target (<= target * 1.02)
    text, style = get_proximity_status(81, 100, 105, 80, is_long=False)
    assert "Near Target" in text and style == "info"


def test_target_not_near_when_out_of_range():
    # long: price far above target -> shouldn't be 'Near Target'
    text, style = get_proximity_status(210, 100, 90, 200, is_long=True)
    assert "Near Target" not in text

    # short: price far below target -> shouldn't be 'Near Target'
    text, style = get_proximity_status(70, 100, 105, 80, is_long=False)
    assert "Near Target" not in text


def test_entry_percentage_is_positive_and_relative_to_entry():
    # long: price within 2% of entry should show Entry in
    text, style = get_proximity_status(2450, 2500, 2000, 3000, is_long=True)
    assert "Entry in" in text and text.count("-") == 0

    # short: price within 2% of entry should show Entry in
    text, style = get_proximity_status(2450, 2500, 2800, 2000, is_long=False)
    assert "Entry in" in text and text.count("-") == 0

    # when much further than 2% the status should be blank
    text, style = get_proximity_status(2350, 2720, 2000, 3000, is_long=True)
    assert text == "" and style == "secondary"


if __name__ == "__main__":
    try:
        test_long_proximity()
        test_short_proximity()
        print("OK: trading proximity tests passed")
    except AssertionError:
        print("FAIL: trading proximity tests failed")
        raise
