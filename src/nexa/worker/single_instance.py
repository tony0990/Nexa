"""Single-instance protection: named mutex on Windows, advisory file lock elsewhere (tests/dev)."""
from __future__ import annotations

import os
import sys
import tempfile

ERROR_ALREADY_EXISTS = 183


class SingleInstanceLock:
    def __init__(self, name: str = "NexaWorker", lock_dir: str | None = None):
        self.name = name
        self.lock_dir = lock_dir or tempfile.gettempdir()
        self._handle = None
        self._fd = None

    def acquire(self) -> bool:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.restype = wintypes.HANDLE
            k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            handle = k32.CreateMutexW(None, False, f"Local\\{self.name}")
            if not handle:
                return False
            if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
                k32.CloseHandle(handle)
                return False
            self._handle = handle
            return True
        import fcntl
        path = os.path.join(self.lock_dir, f"{self.name}.lock")
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def release(self) -> None:
        if self._handle is not None:
            import ctypes
            ctypes.WinDLL("kernel32").CloseHandle(self._handle)
            self._handle = None
        if self._fd is not None:
            import fcntl
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("another NexaWorker instance is already running")
        return self

    def __exit__(self, *exc):
        self.release()
