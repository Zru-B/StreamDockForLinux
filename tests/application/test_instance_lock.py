"""
Unit tests for InstanceLock.

Two processes driving one device is the failure this prevents.
"""

import os
import subprocess
import sys
import tempfile

import pytest

from StreamDock.application.instance_lock import InstanceLock, default_lock_path


@pytest.fixture
def lock_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test.lock")


HOLDER = """
import sys, time
sys.path.insert(0, {src!r})
from StreamDock.application.instance_lock import InstanceLock
lock = InstanceLock({path!r})
print("ACQUIRED" if lock.acquire() else "REFUSED", flush=True)
time.sleep(30)
"""

PROBE = """
import sys
sys.path.insert(0, {src!r})
from StreamDock.application.instance_lock import InstanceLock
print("ACQUIRED" if InstanceLock({path!r}).acquire() else "REFUSED")
"""


def src_dir():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "src")


class TestInstanceLock:
    """Acquiring and releasing."""

    def test_acquire_succeeds_when_free(self, lock_path):
        assert InstanceLock(lock_path).acquire() is True

    def test_acquire_is_idempotent_within_a_process(self, lock_path):
        lock = InstanceLock(lock_path)
        assert lock.acquire() is True
        assert lock.acquire() is True

    def test_records_the_owning_pid(self, lock_path):
        lock = InstanceLock(lock_path)
        lock.acquire()
        assert lock.owner_pid() == os.getpid()

    def test_release_is_safe_when_not_held(self, lock_path):
        InstanceLock(lock_path).release()

    def test_context_manager_releases(self, lock_path):
        with InstanceLock(lock_path):
            pass
        assert InstanceLock(lock_path).acquire() is True

    def test_unwritable_location_does_not_block_startup(self):
        """Refusing to start would be worse than the race it prevents."""
        assert InstanceLock("/proc/definitely/not/writable.lock").acquire() is True


class TestCrossProcess:
    """The guarantee that actually matters."""

    def test_a_second_process_is_refused(self, lock_path):
        holder = subprocess.Popen(
            [sys.executable, "-c", HOLDER.format(src=src_dir(), path=lock_path)],
            stdout=subprocess.PIPE, text=True)
        try:
            assert holder.stdout.readline().strip() == "ACQUIRED"

            probe = subprocess.run(
                [sys.executable, "-c", PROBE.format(src=src_dir(), path=lock_path)],
                capture_output=True, text=True, timeout=30)

            assert probe.stdout.strip() == "REFUSED"
        finally:
            holder.kill()
            holder.wait(timeout=10)

    def test_the_lock_is_freed_when_the_holder_dies(self, lock_path):
        holder = subprocess.Popen(
            [sys.executable, "-c", HOLDER.format(src=src_dir(), path=lock_path)],
            stdout=subprocess.PIPE, text=True)
        assert holder.stdout.readline().strip() == "ACQUIRED"
        holder.kill()
        holder.wait(timeout=10)

        probe = subprocess.run(
            [sys.executable, "-c", PROBE.format(src=src_dir(), path=lock_path)],
            capture_output=True, text=True, timeout=30)

        assert probe.stdout.strip() == "ACQUIRED"


class TestDefaultLockPath:
    """Where the lock lives."""

    def test_prefers_the_runtime_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        assert default_lock_path() == os.path.join(str(tmp_path), "streamdock.lock")

    def test_falls_back_to_a_per_user_tmp_file(self, monkeypatch):
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        assert default_lock_path() == f"/tmp/streamdock-{os.getuid()}.lock"
