class NavigationHelper:
    """Helper to encapsulate watchlist navigation logic for TechnicalAnalysisWindow."""

    def __init__(self, window):
        self.window = window

    def find_watchlist_widget(self):
        try:
            parent = getattr(self.window, 'master', None)
            # 1. If parent itself is a watchlist
            if parent and hasattr(parent, 'get_adjacent_ticker') and hasattr(parent, 'get_ordered_tickers'):
                return parent
            # 2. If parent is command center that has .watchlist attribute
            if parent and hasattr(parent, 'watchlist'):
                return getattr(parent, 'watchlist')
            # 3. Walk up the master chain looking for object with 'get_adjacent_ticker'
            cur = parent
            while cur is not None:
                try:
                    if hasattr(cur, 'get_adjacent_ticker') and hasattr(cur, 'get_ordered_tickers'):
                        return cur
                except Exception:
                    pass
                cur = getattr(cur, 'master', None)
        except Exception:
            pass
        return None

    def update_navigation_state(self):
        try:
            watchlist_obj = None
            parent = getattr(self.window, 'master', None)
            if parent and hasattr(parent, 'get_ordered_tickers'):
                watchlist_obj = parent
            elif parent and hasattr(parent, 'watchlist'):
                watchlist_obj = getattr(parent, 'watchlist')
            else:
                cur = parent
                while cur is not None:
                    try:
                        if hasattr(cur, 'get_ordered_tickers'):
                            watchlist_obj = cur
                            break
                    except Exception:
                        pass
                    cur = getattr(cur, 'master', None)

            if watchlist_obj is not None and callable(getattr(watchlist_obj, 'get_ordered_tickers', None)):
                try:
                    t = watchlist_obj.get_ordered_tickers() or []
                except Exception:
                    t = []
                if not t or len(t) <= 1:
                    try:
                        self.window.prev_btn.configure(state='disabled')
                        self.window.next_btn.configure(state='disabled')
                    except Exception:
                        pass
                    return
                else:
                    try:
                        self.window.prev_btn.configure(state='normal')
                        self.window.next_btn.configure(state='normal')
                    except Exception:
                        pass
            else:
                try:
                    self.window.prev_btn.configure(state='disabled')
                    self.window.next_btn.configure(state='disabled')
                except Exception:
                    pass
        except Exception:
            pass

    def go_prev(self):
        try:
            w = self.find_watchlist_widget()
            if w and hasattr(w, 'get_adjacent_ticker'):
                prev_t = w.get_adjacent_ticker(self.window.ticker, direction=-1)
                if prev_t:
                    try:
                        if callable(getattr(w, 'on_select', None)):
                            w.on_select(prev_t)
                    except Exception:
                        pass
                    self.window.update_ticker(prev_t)
                    self.window.after(100, self.window.lift)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('NavigationHelper failed to move to previous ticker')

    def go_next(self):
        try:
            w = self.find_watchlist_widget()
            if w and hasattr(w, 'get_adjacent_ticker'):
                nxt = w.get_adjacent_ticker(self.window.ticker, direction=1)
                if nxt:
                    try:
                        if callable(getattr(w, 'on_select', None)):
                            w.on_select(nxt)
                    except Exception:
                        pass
                    self.window.update_ticker(nxt)
                    self.window.after(100, self.window.lift)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('NavigationHelper failed to move to next ticker')