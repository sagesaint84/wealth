"""Bounded native Chrome startup and loopback HTTP preview infrastructure."""

from contextlib import contextmanager
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import time


# Chromium net/base/port_util.cc kRestrictedPorts (2026-10-09).
# https://chromium.googlesource.com/chromium/src/+/refs/heads/main/net/base/port_util.cc
UNSAFE_PORTS = frozenset({
    0, 1, 7, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23, 25, 37, 42, 43,
    53, 69, 77, 79, 87, 95, 101, 102, 103, 104, 109, 110, 111, 113,
    115, 117, 119, 123, 135, 137, 139, 143, 161, 179, 389, 427, 465,
    512, 513, 514, 515, 526, 530, 531, 532, 540, 548, 554, 556, 563,
    587, 601, 636, 989, 990, 993, 995, 1719, 1720, 1723, 2049, 3659,
    4045, 5060, 5061, 6000, 6566, 6665, 6666, 6667, 6668, 6669, 6697, 10080,
})


def safe_preview_server(server_type, handler, attempts=32):
    """Keep the accepted listening socket bound; never reserve/close/rebind."""
    rejected = []
    for _ in range(attempts):
        server = server_type(('127.0.0.1', 0), handler)
        if 1 <= server.server_port <= 65535 and server.server_port not in UNSAFE_PORTS:
            return server
        rejected.append(server.server_port)
        server.server_close()
    raise RuntimeError(f'No Chrome-safe preview port after {attempts} binds: {rejected}')


def parse_active_port(contents):
    lines = contents.splitlines()
    if len(lines) != 2 or not re.fullmatch(r'[0-9]{1,5}', lines[0]):
        raise ValueError('incomplete/malformed DevToolsActivePort contents')
    port = int(lines[0])
    if not 1 <= port <= 65535:
        raise ValueError(f'invalid debugging port: {port}')
    if not re.fullmatch(r'/devtools/browser/[A-Za-z0-9-]+', lines[1]):
        raise ValueError('incomplete/malformed browser websocket path')
    return port


def wait_for_active_port(process, profile, *, timeout=10, interval=0.1,
                         clock=time.monotonic, sleep=time.sleep, diagnostics=lambda: ''):
    deadline = clock() + timeout
    active_port = Path(profile) / 'DevToolsActivePort'
    last = 'file not observed'
    while True:
        code = process.poll()
        if code is not None:
            raise RuntimeError(f'Chrome exited during startup: exit={code}; profile={profile}; '
                               f'last={last}; {diagnostics()}')
        try:
            return parse_active_port(active_port.read_text(encoding='utf-8'))
        except (FileNotFoundError, PermissionError, ValueError, UnicodeError) as error:
            last = f'{type(error).__name__}: {error}'
        remaining = deadline - clock()
        if remaining <= 0:
            raise RuntimeError(f'Chrome startup timeout ({timeout}s): process={process.poll()}; '
                               f'profile={profile}; last={last}; {diagnostics()}')
        sleep(min(interval, remaining))


def stop_chrome(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def cleanup_profile(path, *, timeout=4, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout
    while True:
        try:
            shutil.rmtree(path)
            return
        except PermissionError as error:
            remaining = deadline - clock()
            if remaining <= 0:
                raise RuntimeError(f'Chrome profile cleanup timeout: profile={path}; last={error}') from error
            sleep(min(0.2, remaining))


@contextmanager
def chrome_profile(prefix, *, cleanup_if=lambda: True):
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield str(path)
    finally:
        if cleanup_if():
            cleanup_profile(path)


def ensure_fresh_profile(profile):
    if (Path(profile) / 'DevToolsActivePort').exists():
        raise RuntimeError(f'Refusing stale DevToolsActivePort: profile={profile}')


@contextmanager
def chrome_session(chrome, prefix):
    process = None
    with chrome_profile(prefix, cleanup_if=lambda: process is None or process.poll() is not None) as profile:
        ensure_fresh_profile(profile)
        # File-backed output avoids PIPE buffer deadlocks. Keep logs outside the
        # profile: Windows Chrome helpers can retain inherited output handles
        # briefly after the browser exits. TemporaryFile uses delete-on-close
        # sharing on Windows, so those handles cannot block profile cleanup.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(
                [chrome, '--headless=new', '--no-first-run', '--no-default-browser-check',
                 '--disable-gpu', '--remote-allow-origins=*', '--remote-debugging-port=0',
                 f'--user-data-dir={profile}', 'about:blank'],
                stdout=stdout, stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )

            def diagnostics():
                parts = []
                for name, stream in (('stdout', stdout), ('stderr', stderr)):
                    try:
                        stream.seek(0, 2)
                        stream.seek(max(0, stream.tell() - 8192))
                        parts.append(f'{name}={stream.read().decode("utf-8", errors="replace")}')
                    except OSError as error:
                        parts.append(f'{name}=unreadable: {error}')
                return '; '.join(parts)

            try:
                port = wait_for_active_port(process, profile, diagnostics=diagnostics)
                yield process, port, profile
            finally:
                stop_chrome(process)
