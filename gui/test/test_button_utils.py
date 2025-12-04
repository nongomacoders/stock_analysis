import os
import sys
# Ensure repo root (gui/) is on the import path when running tests directly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from components.button_utils import run_bg_with_button, wrap_sync_button


class FakeButton:
    def __init__(self):
        self.state = 'normal'
        self.calls = []

    def configure(self, **kwargs):
        # record state changes
        if 'state' in kwargs:
            self.state = kwargs['state']
            self.calls.append(('configure', kwargs['state']))


def test_run_bg_with_button_success():
    btn = FakeButton()

    def fake_async_run_bg(coro, callback=None):
        # simulate async-runner calling callback synchronously
        if callback:
            callback('ok')

    result = {}

    def on_done(res):
        result['called'] = True
        result['res'] = res

    # run
    run_bg_with_button(btn, fake_async_run_bg, object(), callback=on_done)

    assert result.get('called', False) is True
    assert result.get('res') == 'ok'
    # button should have been disabled and re-enabled
    assert btn.state == 'normal'
    assert ('configure', 'disabled') in btn.calls
    assert ('configure', 'normal') in btn.calls


def test_run_bg_with_button_runner_raises():
    btn = FakeButton()

    def fake_async_run_bg_raises(coro, callback=None):
        raise RuntimeError('boom')

    try:
        run_bg_with_button(btn, fake_async_run_bg_raises, object())
    except RuntimeError:
        pass
    else:
        raise AssertionError('Expected RuntimeError')

    # Ensure button was re-enabled after synchronous exception
    assert btn.state == 'normal'


def test_wrap_sync_button():
    btn = FakeButton()
    def do_work(x, y):
        return x + y
    out = wrap_sync_button(btn, do_work, 2, 3)
    assert out == 5
    assert btn.state == 'normal'
    assert ('configure', 'disabled') in btn.calls and ('configure', 'normal') in btn.calls


if __name__ == '__main__':
    test_run_bg_with_button_success()
    test_run_bg_with_button_runner_raises()
    test_wrap_sync_button()
    print('OK')
