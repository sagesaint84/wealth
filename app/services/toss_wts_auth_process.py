"""Linux per-attempt subreaper. No process-name scans or process-group kills.

Executed as an isolated interpreter, never sets subreaper on the web server.
Only its own direct/adopted children can be signalled through pinned pidfds.
Private receipt proves ECHILD after CLI exit; leader exit alone proves nothing.
"""
from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BOUNDARY_KIND = "linux-subreaper-v1"
MAX_DIRECT_CHILDREN = 1024
AUTH_MAX_SECONDS = 300  # Same limit as Wealth and the upstream QR helper.


def boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()


def process_identity(pid: int) -> tuple[int, str]:
    # comm may contain spaces and parentheses; starttime is field 22.
    fields = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()
    return int(fields[1]), fields[19]


def receipt_path(directory: Path, attempt_id: str) -> Path:
    return directory / f"{attempt_id}.process.json"


def atomic_private_json(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def private_receipt(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        stat = os.fstat(stream.fileno())
        if stat.st_mode & 0o077 or stat.st_size > 4096:
            raise ValueError("AUTH_PROCESS_INVALID_RECEIPT")
        return json.loads(stream.read(4097))


def boundary_complete(directory: Path, attempt_id: str, owner: str,
                      boundary: dict, pid: int | None, start: str | None) -> bool:
    """Read proof without guessing from PID absence. Restart-safe and owner-bound."""
    if (not isinstance(boundary, dict) or boundary.get("kind") != BOUNDARY_KIND
            or not pid or not start or not boundary.get("token")):
        return False
    try:
        proof = private_receipt(receipt_path(directory, attempt_id))
        if not isinstance(proof, dict):
            return False
        expected = {"kind": BOUNDARY_KIND, "attempt_id": attempt_id, "owner": owner,
                    "token": boundary["token"], "boot_id": boundary["boot_id"],
                    "supervisor_pid": pid, "supervisor_start": start,
                    "cleanup_complete": True}
        if any(proof.get(key) != value for key, value in expected.items()):
            return False
        if boot_id() != boundary["boot_id"]:
            return False
        try:
            _, actual = process_identity(pid)
            return actual != start  # PID reuse does not invalidate prior proof.
        except FileNotFoundError:
            return True
    except (OSError, ValueError, KeyError, AttributeError, IndexError):
        pass
    return False


def signal_supervisor(pid: int, start: str | None, expected_boot: str) -> bool:
    """Request cleanup, never SIGKILL the owner of unreaped descendants."""
    if not start or pid <= 0:
        return False
    try:
        if boot_id() != expected_boot or process_identity(pid)[1] != start:
            return False
        fd = os.pidfd_open(pid)
        try:
            if process_identity(pid)[1] != start:
                return False
            signal.pidfd_send_signal(fd, signal.SIGTERM)
            return True
        finally:
            os.close(fd)
    except (OSError, AttributeError, IndexError, ValueError):
        return False


def enable_subreaper() -> None:
    if sys.platform != "linux" or not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise OSError("AUTH_PROCESS_BOUNDARY_UNAVAILABLE")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError("AUTH_PROCESS_BOUNDARY_UNAVAILABLE")
    value = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(value), 0, 0, 0) != 0 or value.value != 1:
        raise OSError("AUTH_PROCESS_BOUNDARY_UNAVAILABLE")
    # Probe permissions/syscalls before spawning the CLI (no authentication).
    fd = os.pidfd_open(os.getpid())
    try:
        signal.pidfd_send_signal(fd, 0)
    finally:
        os.close(fd)


def direct_children() -> list[int]:
    # This supervisor is single-threaded. Only its child list is read, bounded.
    with Path(f"/proc/self/task/{os.getpid()}/children").open() as stream:
        text = stream.read(16385)
    if len(text) > 16384:
        raise OSError("AUTH_PROCESS_CHILD_LIMIT")
    children = [int(item) for item in text.split()]
    if len(children) > MAX_DIRECT_CHILDREN:
        raise OSError("AUTH_PROCESS_CHILD_LIMIT")
    return children


def signal_owned_child(pid: int, sig: int) -> None:
    parent, start = process_identity(pid)
    if parent != os.getpid():
        return  # Never signal another attempt/user/unrelated process.
    fd = os.pidfd_open(pid)
    try:
        if process_identity(pid) != (os.getpid(), start):
            return
        signal.pidfd_send_signal(fd, sig)
    finally:
        os.close(fd)


def supervise(argv: list[str], proof: dict, path: Path) -> int:
    """Return only after kernel ECHILD, or remain alive on uncertain cleanup."""
    stopping = False
    def request_stop(_sig, _frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    cli = None
    cli_exit = None
    # Capability failure occurs before any auth process is spawned.
    try:
        enable_subreaper()
        if stopping:
            raise OSError("AUTH_PROCESS_CANCELLED_BEFORE_SPAWN")
        cli = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, ValueError):
        cli_exit = -1
    cleanup_started = None
    auth_deadline = time.monotonic() + AUTH_MAX_SECONDS
    while True:
        no_children = False
        try:
            for _ in range(MAX_DIRECT_CHILDREN):
                pid, status = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
                if cli is not None and pid == cli.pid:
                    cli_exit = os.waitstatus_to_exitcode(status)
                    cli.returncode = cli_exit
        except ChildProcessError:
            no_children = True
        except OSError:
            # Unknown kernel/process state: no receipt and no release.
            pass
        if no_children and cli_exit is not None:
            try:
                atomic_private_json(path, {**proof, "cleanup_complete": True,
                                           "cli_exit_code": cli_exit})
            except OSError:
                return 1  # Missing proof keeps the durable guard closed.
            return 0
        if time.monotonic() >= auth_deadline:
            stopping = True  # Independent deadline survives web-server restart.
        if stopping or cli_exit is not None:
            if cleanup_started is None:
                cleanup_started = time.monotonic()
            sig = signal.SIGTERM if time.monotonic() - cleanup_started < 2.0 else signal.SIGKILL
            try:
                for pid in direct_children():
                    try:
                        signal_owned_child(pid, sig)
                    except OSError:
                        pass  # Permission/exit races are resolved only by waitpid.
            except (OSError, ValueError, IndexError):
                pass
        time.sleep(0.05)


def main() -> int:
    # No raw exceptions, child output, token, QR, cookies or config in logs.
    try:
        proof = json.loads(os.environ["TOSSCTL_AUTH_PROCESS_CONTEXT"])
        path = Path(os.environ["TOSSCTL_AUTH_PROCESS_RECEIPT"])
        proof.update(supervisor_pid=os.getpid(), supervisor_start=process_identity(os.getpid())[1])
        return supervise(sys.argv[1:], proof, path)
    except Exception:
        return 1  # No completion proof: the web-service guard remains closed.


if __name__ == "__main__":
    raise SystemExit(main())
