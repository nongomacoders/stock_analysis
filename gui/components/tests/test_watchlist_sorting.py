from components.watchlist_sorting import proximity_key


def test_proximity_key_parses_numbers():
    samples = [
        ("(0.5%) Entry", 0.5),
        ("(12%) Stop", 12.0),
        ("(1.23%) Target", 1.23),
        ("No Data", float('inf')),
        ("", float('inf')),
        (None, float('inf')),
    ]

    for s, expected in samples:
        val = proximity_key((s, None))
        if expected == float('inf'):
            assert val == float('inf')
        else:
            assert abs(val - expected) < 1e-6
