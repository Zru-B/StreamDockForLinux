"""
Single-instance guard.

Only one process can hold the device's HID handle usefully. The GUI and the
headless runner therefore take the same advisory lock, so a second launch
fails with a clear message instead of fighting over the hardware.

Deliberately outside ui/: the headless entry point has no Qt, so a Qt-based
guard could not see it.
"""

import errno
import fcntl
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

LOCK_NAME = "streamdock.lock"


def default_lock_path() -> str:
    """
    Where the lock file lives.

    Returns:
        A path under XDG_RUNTIME_DIR when available (cleaned up at logout),
        otherwise a per-user file in /tmp.
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir and os.path.isdir(runtime_dir):
        return os.path.join(runtime_dir, LOCK_NAME)
    return os.path.join("/tmp", f"streamdock-{os.getuid()}.lock")


class InstanceLock:
    """
    An advisory whole-process lock held for the lifetime of the process.

    Uses flock, so the kernel releases it even if the process is killed - no
    stale lock files to clean up by hand.
    """

    def __init__(self, path: Optional[str] = None):
        """
        Args:
            path: Lock file to use. Defaults to default_lock_path().
        """
        self._path = path or default_lock_path()
        self._fd: Optional[int] = None

    @property
    def path(self) -> str:
        """The lock file backing this lock."""
        return self._path

    def acquire(self) -> bool:
        """
        Take the lock.

        Returns:
            True if this process now holds it, False if another process does.
            Also True if locking is unsupported on this filesystem - refusing
            to start would be worse than the race it prevents.
        """
        if self._fd is not None:
            return True

        try:
            fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError as e:
            logger.warning("Could not open lock file %s: %s", self._path, e)
            return True

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            if e.errno in (errno.EACCES, errno.EAGAIN):
                logger.debug("Lock %s is held by another process", self._path)
                return False
            logger.warning("Could not lock %s: %s", self._path, e)
            return True

        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        self._fd = fd
        logger.debug("Acquired instance lock %s", self._path)
        return True

    def owner_pid(self) -> Optional[int]:
        """
        The pid recorded in the lock file.

        Returns:
            The pid, or None if it cannot be read. Only meaningful when
            acquire() returned False.
        """
        try:
            with open(self._path, 'r') as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def release(self) -> None:
        """Release the lock. Safe to call when not held."""
        if self._fd is None:
            return

        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        except OSError as e:
            logger.debug("Error unlocking %s: %s", self._path, e)
        finally:
            os.close(self._fd)
            self._fd = None
            logger.debug("Released instance lock %s", self._path)

    def __enter__(self) -> "InstanceLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info) -> None:
        self.release()
