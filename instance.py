"""Single-instance lock shared by the app and the settings window.

The running app holds an exclusive byte-range lock on ``LOCK_PATH`` for its whole
life. The settings window never takes the lock for good; ``app_running`` only
probes it, so the "Start app" button can be enabled or disabled.
"""

import msvcrt
import os
from pathlib import Path

ROOT = Path(__file__).parent
LOCK_PATH = ROOT / ".app.lock"


class AppLock:
    """An exclusive lock on byte 0 of the lock file, held until ``release``."""

    def __init__(self, fd: int):
        self._fd: int | None = fd

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)


def hold_app_lock(path: Path) -> AppLock:
    """Take the lock, or raise ``OSError`` if another holder already has it."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT)
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        os.close(fd)
        raise
    return AppLock(fd)


def app_running(path: Path) -> bool:
    """True while some handle (this process or another) holds the lock."""
    try:
        fd = os.open(path, os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return True
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return False
    finally:
        os.close(fd)
