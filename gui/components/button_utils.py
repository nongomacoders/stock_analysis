"""Helpers to run background actions while disabling a button until completion.

Provides small helpers that UI code can use to ensure buttons are disabled
while a background coroutine is running and re-enabled when the work completes.

Usage examples:
  from components.button_utils import run_bg_with_button

  # disable btn while coro runs, re-enable when callback runs/when coro finishes
  run_bg_with_button(btn, async_run_bg, my_coro(), callback=my_callback)

The helpers are intentionally small and unopinionated so callers can still
handle confirmation dialogs and other UI flows before delegating to these
utilities.
"""
from typing import Any, Callable, Optional
import logging

logger = logging.getLogger(__name__)


def run_bg_with_button(button: Any, async_run_bg_func: Callable, coro: Any, callback: Optional[Callable] = None) -> None:
    """Run a coroutine via the provided async_run_bg_func while disabling a button.

    - button: the tkinter widget to disable/enable (any object with .configure)
    - async_run_bg_func: function like self.async_run_bg(coro, callback=...)
    - coro: coroutine object to run in background
    - callback: optional callback invoked on completion (receives coro result)

    The button is disabled immediately, then async_run_bg_func is called with
    an internal wrapper that ensures the button is re-enabled in all cases
    after the callback runs.
    """
    try:
        button.configure(state="disabled")
    except Exception:
        # best-effort; keep going if widget can't be configured
        pass

    def _wrapped(result=None):
        try:
            if callback:
                try:
                    callback(result)
                except Exception:
                    logger.exception("button callback failed")
        finally:
            try:
                button.configure(state="normal")
            except Exception:
                pass

    # kick off the background job
    try:
        async_run_bg_func(coro, callback=_wrapped)
    except Exception:
        # If async_run_bg_func raises synchronously, re-enable and re-raise
        try:
            button.configure(state="normal")
        except Exception:
            pass
        raise


def wrap_sync_button(button: Any, func: Callable, *args, **kwargs):
    """Call a synchronous function while disabling the button around the call.

    Returns whatever func returns and always re-enables the button.
    """
    try:
        button.configure(state="disabled")
    except Exception:
        pass
    try:
        return func(*args, **kwargs)
    finally:
        try:
            button.configure(state="normal")
        except Exception:
            pass
