"""Watch a folder: Windows reports every change inside it (ReadDirectoryChangesW), a thread
sleeps on that report and costs nothing in between, and once the folder has been quiet for
a few seconds the launcher is told to run. No polling, no timer, and only while the
launcher is open and the tick box is on.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import threading
import time
from typing import Callable

FILE_LIST_DIRECTORY = 0x0001
FILE_SHARE_ALL = 0x0001 | 0x0002 | 0x0004
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_NOTIFY_CHANGE_FILE_NAME = 0x0001
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x0010
FILE_NOTIFY_CHANGE_SIZE = 0x0008
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value


class FolderWatcher:
    """Calls `on_settled()` (on its own thread) when files inside `folder` have changed and
    then been left alone for `settle` seconds — a copy of a large file fires many changes;
    only the last one matters."""

    def __init__(self, folder: Path, on_settled: Callable[[], None], settle: float = 5.0,
                 wanted: Callable[[Path], bool] | None = None):
        self.folder = folder
        self.on_settled = on_settled
        self.settle = settle
        self.wanted = wanted or (lambda _p: True)
        self._stop = threading.Event()
        self._handle = None
        self._thread: threading.Thread | None = None
        self._last_change = 0.0
        self._pending = False

    def start(self) -> bool:
        if os.name != "nt":
            return False
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.restype = wintypes.HANDLE
        handle = kernel32.CreateFileW(
            str(self.folder), FILE_LIST_DIRECTORY, FILE_SHARE_ALL, None, OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS, None,
        )
        if handle == INVALID_HANDLE_VALUE or not handle:
            return False
        self._handle = handle
        self._thread = threading.Thread(target=self._run, daemon=True, name="folder-watcher")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._handle:
            # Closing the handle wakes the blocked ReadDirectoryChangesW with an error.
            ctypes.windll.kernel32.CancelIoEx(self._handle, None)
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None

    def _run(self) -> None:
        kernel32 = ctypes.windll.kernel32
        buffer = ctypes.create_string_buffer(64 * 1024)
        returned = wintypes.DWORD(0)
        flags = FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_LAST_WRITE | FILE_NOTIFY_CHANGE_SIZE
        while not self._stop.is_set():
            ok = kernel32.ReadDirectoryChangesW(
                self._handle, buffer, len(buffer), True, flags, ctypes.byref(returned), None, None,
            )
            if not ok or self._stop.is_set():
                break
            if self._interesting(buffer.raw[:returned.value]):
                self._last_change = time.time()
                self._pending = True
                # Wait for quiet: another change restarts the clock (the next loop turn
                # handles it because ReadDirectoryChangesW returns at once for it).
                threading.Thread(target=self._settle_then_fire, daemon=True).start()

    def _interesting(self, raw: bytes) -> bool:
        """Any changed file the launcher would convert? FILE_NOTIFY_INFORMATION records:
        next-offset(4) action(4) name-length(4) name(utf-16)."""
        offset = 0
        while offset + 12 <= len(raw):
            next_offset = int.from_bytes(raw[offset:offset + 4], "little")
            length = int.from_bytes(raw[offset + 8:offset + 12], "little")
            name = raw[offset + 12:offset + 12 + length].decode("utf-16-le", errors="replace")
            if self.wanted(self.folder / name):
                return True
            if not next_offset:
                break
            offset += next_offset
        return False

    def _settle_then_fire(self) -> None:
        stamp = self._last_change
        time.sleep(self.settle)
        if self._stop.is_set() or self._last_change != stamp or not self._pending:
            return  # a newer change owns the clock, or it already fired
        self._pending = False
        self.on_settled()
