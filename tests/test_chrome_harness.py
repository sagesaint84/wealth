"""Deterministic startup tests; fake time never sleeps or launches Chrome."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import subprocess

import pytest

from tests import chrome_harness as harness


VALID = '12345\n/devtools/browser/abc-123\n'


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def wait(monkeypatch, values, process=None, **kwargs):
    reader = Mock(side_effect=values)
    monkeypatch.setattr(Path, 'read_text', reader)
    clock = Clock()
    result = harness.wait_for_active_port(process or SimpleNamespace(poll=lambda: None),
        'synthetic-profile', timeout=0.3, interval=0.1, clock=clock, sleep=clock.sleep,
        diagnostics=lambda: 'stdout=synthetic-out; stderr=synthetic-error', **kwargs)
    return result, reader, clock


@pytest.mark.parametrize('pending', [
    [FileNotFoundError('pending')],
    [PermissionError('locked')] * 3,
    ['', '12345', '12345\n/devtools/browser/'],
    ['bad\n/devtools/browser/abc', '0\n/devtools/browser/abc', '65536\n/devtools/browser/abc'],
])
def test_pending_read_then_complete(monkeypatch, pending):
    port, reader, clock = wait(monkeypatch, [*pending, VALID])
    assert port == 12345
    assert reader.call_count == len(pending) + 1
    assert clock.now <= 0.3


@pytest.mark.parametrize('contents', ['', '12345', 'abc\n/devtools/browser/x',
    '-1\n/devtools/browser/x', '0\n/devtools/browser/x', '65536\n/devtools/browser/x',
    '12345\nwrong', '12345\n/devtools/browser/', '12345\n/devtools/browser/x\nextra'])
def test_invalid_contents_rejected(contents):
    with pytest.raises(ValueError):
        harness.parse_active_port(contents)


@pytest.mark.parametrize('port', [1, 65535])
def test_port_boundaries(port):
    assert harness.parse_active_port(f'{port}\n/devtools/browser/abc-123') == port


@pytest.mark.parametrize('condition', [PermissionError('locked'), FileNotFoundError('missing'),
                                      '', 'not-a-port\n/devtools/browser/abc'])
def test_deadline_diagnostics(monkeypatch, condition):
    with pytest.raises(RuntimeError, match='startup timeout') as error:
        wait(monkeypatch, [condition] * 10)
    message = str(error.value)
    for field in ('process=None', 'profile=synthetic-profile', 'last=', 'stdout=', 'stderr='):
        assert field in message


def test_early_exit_precedes_file_read(monkeypatch):
    reader = Mock()
    monkeypatch.setattr(Path, 'read_text', reader)
    with pytest.raises(RuntimeError, match='exit=23'):
        harness.wait_for_active_port(SimpleNamespace(poll=lambda: 23), 'synthetic-profile')
    reader.assert_not_called()


def test_exit_during_poll_does_not_wait_for_timeout(monkeypatch):
    process = SimpleNamespace(poll=Mock(side_effect=[None, 9]))
    with pytest.raises(RuntimeError, match='exit=9'):
        wait(monkeypatch, [FileNotFoundError()], process=process)
    assert process.poll.call_count == 2


def test_stale_profile_rejected(tmp_path):
    (tmp_path / 'DevToolsActivePort').write_text(VALID)
    with pytest.raises(RuntimeError, match='stale'):
        harness.ensure_fresh_profile(tmp_path)


def test_profiles_unique_and_cleaned():
    with harness.chrome_profile('wealth-unit-') as first:
        with harness.chrome_profile('wealth-unit-') as second:
            assert first != second
            assert not (Path(first) / 'DevToolsActivePort').exists()
        assert not Path(second).exists()
    assert not Path(first).exists()


def test_unsafe_ports_closed_safe_socket_retained():
    servers = [SimpleNamespace(server_port=p, server_close=Mock()) for p in (6666, 6669, 12345)]
    factory = Mock(side_effect=servers)
    assert harness.safe_preview_server(factory, object()) is servers[-1]
    for server in servers[:2]:
        server.server_close.assert_called_once()
    servers[-1].server_close.assert_not_called()
    assert all(call.args[0] == ('127.0.0.1', 0) for call in factory.call_args_list)


def test_unsafe_allocator_bounded():
    factory = Mock(side_effect=lambda *args: SimpleNamespace(server_port=6666, server_close=Mock()))
    with pytest.raises(RuntimeError, match='after 3 binds'):
        harness.safe_preview_server(factory, object(), attempts=3)
    assert factory.call_count == 3


def test_stop_kill_fallback():
    process = Mock()
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired('chrome', 5), 0]
    harness.stop_chrome(process)
    assert [call[0] for call in process.method_calls] == ['poll', 'terminate', 'wait', 'kill', 'wait']


def test_exited_process_needs_no_termination():
    process = Mock()
    process.poll.return_value = 0
    harness.stop_chrome(process)
    process.terminate.assert_not_called()


def test_cleanup_transient_lock(monkeypatch):
    remove = Mock(side_effect=[PermissionError('locked'), None])
    monkeypatch.setattr(harness.shutil, 'rmtree', remove)
    clock = Clock()
    harness.cleanup_profile('synthetic-profile', clock=clock, sleep=clock.sleep)
    assert remove.call_count == 2


def test_cleanup_lock_deadline(monkeypatch):
    monkeypatch.setattr(harness.shutil, 'rmtree', Mock(side_effect=PermissionError('locked')))
    clock = Clock()
    with pytest.raises(RuntimeError, match='cleanup timeout.*synthetic-profile'):
        harness.cleanup_profile('synthetic-profile', timeout=0.3, clock=clock, sleep=clock.sleep)


def test_session_stops_before_cleanup(monkeypatch, tmp_path):
    events = []
    process = SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(harness.tempfile, 'mkdtemp', lambda **kwargs: str(tmp_path))
    monkeypatch.setattr(harness.subprocess, 'Popen', lambda *args, **kwargs: process)
    monkeypatch.setattr(harness, 'wait_for_active_port', lambda *args, **kwargs: 12345)
    def stop(proc):
        events.append('stop')
        proc.poll = lambda: 0
    monkeypatch.setattr(harness, 'stop_chrome', stop)
    monkeypatch.setattr(harness, 'cleanup_profile', lambda path: events.append('cleanup'))
    with harness.chrome_session('synthetic-chrome', 'wealth-unit-'):
        events.append('use')
    assert events == ['use', 'stop', 'cleanup']


def test_failed_stop_preserves_running_profile(monkeypatch, tmp_path):
    process = SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(harness.tempfile, 'mkdtemp', lambda **kwargs: str(tmp_path))
    monkeypatch.setattr(harness.subprocess, 'Popen', lambda *args, **kwargs: process)
    monkeypatch.setattr(harness, 'wait_for_active_port', lambda *args, **kwargs: 12345)
    monkeypatch.setattr(harness, 'stop_chrome', Mock(side_effect=RuntimeError('kill failed')))
    cleanup = Mock()
    monkeypatch.setattr(harness, 'cleanup_profile', cleanup)
    with pytest.raises(RuntimeError, match='kill failed'):
        with harness.chrome_session('synthetic-chrome', 'wealth-unit-'):
            pass
    cleanup.assert_not_called()


def test_session_native_port_and_early_exit_diagnostics(monkeypatch, tmp_path):
    process = SimpleNamespace(poll=lambda: 17)
    monkeypatch.setattr(harness.tempfile, 'mkdtemp', lambda **kwargs: str(tmp_path))
    def launch(args, **kwargs):
        assert '--remote-debugging-port=0' in args
        assert f'--user-data-dir={tmp_path}' in args
        kwargs['stdout'].write(b'synthetic stdout')
        kwargs['stderr'].write(b'synthetic startup failure')
        kwargs['stdout'].flush()
        kwargs['stderr'].flush()
        return process
    monkeypatch.setattr(harness.subprocess, 'Popen', launch)
    with pytest.raises(RuntimeError, match='exit=17') as error:
        with harness.chrome_session('synthetic-chrome', 'wealth-unit-'):
            pytest.fail('exited browser accepted')
    assert 'synthetic stdout' in str(error.value)
    assert 'synthetic startup failure' in str(error.value)
    assert not tmp_path.exists()
