from typing import Any, List, Optional
from core.utils.chart_drawing_utils import build_lines_from_state


class AnalysisDrawer:
    """Handles building and scheduling chart redraws from analysis state.

    The drawer coalesces multiple draw requests using the chart's `after` method
    (Tkinter), to avoid excessive redraws during rapid updates.
    """
    def __init__(self, chart, debounce_ms: int = 100):
        self.chart = chart
        self.debounce_ms = debounce_ms
        self._after_id = None

    def draw(self, entry_price: Optional[float], stop_loss: Optional[float], target_price: Optional[float], support_levels: Optional[List[tuple]] = None, resistance_levels: Optional[List[tuple]] = None):
        lines = build_lines_from_state(entry_price, stop_loss, target_price, support_levels, resistance_levels)
        # Schedule the actual draw (coalesce multiple requests)
        try:
            if self._after_id is not None and hasattr(self.chart, "after_cancel"):
                try:
                    self.chart.after_cancel(self._after_id)
                except Exception:
                    # Ignore cancellation errors
                    pass
            if self.debounce_ms and hasattr(self.chart, "after"):
                self._after_id = self.chart.after(self.debounce_ms, self._perform_draw, lines)
            else:
                self._perform_draw(lines)
        except Exception:
            # Fall back to immediate draw on error
            self._perform_draw(lines)

    def _perform_draw(self, lines: List[Any]):
        setter = getattr(self.chart, 'set_horizontal_lines', None)
        if callable(setter):
            try:
                setter(lines)
            except Exception:
                pass

    def clear(self):
        clearer = getattr(self.chart, 'clear_horizontal_lines', None)
        if callable(clearer):
            try:
                clearer()
            except Exception:
                pass
