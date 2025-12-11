import unittest
from gui.core.utils.chart_drawing_utils import build_lines_from_state


class ChartDrawingUtilsTests(unittest.TestCase):
    def test_build_lines_from_state_basic(self):
        entry = 10.0
        stop = 9.0
        target = 12.0
        support_levels = [(None, 8.5), (1, 7.0)]
        resistance_levels = [(None, 13.5), (2, 15.0)]

        lines = build_lines_from_state(entry, stop, target, support_levels, resistance_levels)
        # Ensure we have expected labels
        labels = [t[2] for t in lines]
        self.assertIn('Entry: R10.00', labels)
        self.assertIn('Stop Loss: R9.00', labels)
        self.assertIn('Target: R12.00', labels)
        self.assertIn('Support: R8.50', labels)
        self.assertIn('Support: R7.00', labels)
        self.assertIn('Resistance: R13.50', labels)
        self.assertIn('Resistance: R15.00', labels)


if __name__ == '__main__':
    unittest.main()
