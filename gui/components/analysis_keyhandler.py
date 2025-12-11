from typing import Any
import logging


class AnalysisKeyHandler:
    """Handle key events for technical analysis.

    The handler updates the provided window's state (entry/target/stop/supports/res) and
    updates the UI via the window.analysis_panel API, then triggers a redraw via the provided drawer.
    """

    def __init__(self, window, drawer):
        # window is expected to be a TechnicalAnalysisWindow-like object with attributes
        # - chart, analysis_panel, entry_price, stop_loss, target_price, support_levels, resistance_levels
        self.window = window
        self.drawer = drawer

    def handle_key(self, event: Any):
        try:
            # Focus checks: panel input focus and chart focus
            if hasattr(self.window, 'analysis_panel') and callable(getattr(self.window.analysis_panel, 'has_any_input_focus', None)) and self.window.analysis_panel.has_any_input_focus():
                return False
            if not hasattr(self.window, 'chart') or not callable(getattr(self.window.chart, 'has_focus', None)) or not self.window.chart.has_focus():
                return False

            key = getattr(event, 'char', '') or ''
            key = key.lower()
            if key not in ['e', 'l', 't', 'f', 'r']:
                return False

            getter = getattr(self.window.chart, 'get_cursor_y', None)
            cursor_y = getter() if callable(getter) else None
            if cursor_y is None or not isinstance(cursor_y, (int, float)):
                logging.getLogger(__name__).warning('[KeyHandler] No cursor position')
                return False

            key_map = {
                'e': ('entry_price', 'blue', 'entry'),
                'l': ('stop_loss', 'red', 'stop'),
                't': ('target_price', 'green', 'target'),
                'f': ('support', 'green', 'support'),
                'r': ('resistance', 'red', 'resistance'),
            }
            attr_name, color, panel_field = key_map[key]
            price = round(cursor_y, 2)

            # Update state on window
            if attr_name in ('support', 'resistance'):
                if panel_field == 'support':
                    self.window.support_levels.append((None, price))
                else:
                    self.window.resistance_levels.append((None, price))
                try:
                    self.window.analysis_panel.set_levels(support=self.window.support_levels, resistance=self.window.resistance_levels)
                except Exception:
                    pass
            else:
                setattr(self.window, attr_name, price)
                try:
                    self.window.analysis_panel.set_values(**{panel_field: price})
                except Exception:
                    pass

            # Trigger redraw via the drawer
            try:
                self.drawer.draw(
                    getattr(self.window, 'entry_price', None),
                    getattr(self.window, 'stop_loss', None),
                    getattr(self.window, 'target_price', None),
                    getattr(self.window, 'support_levels', None),
                    getattr(self.window, 'resistance_levels', None),
                )
            except Exception:
                try:
                    self.window._draw_all_levels()
                except Exception:
                    pass
            return True
        except Exception:
            logging.getLogger(__name__).exception("Error handling key press")
            return False
