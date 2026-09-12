"""Drop files and folders from Explorer onto a Tk window — through Windows itself.

Tk has no drop support of its own and the usual add-on (tkinterdnd2) is a second package
to bundle. Windows, though, tells any window about a drop with one message, WM_DROPFILES,
once the window has said it accepts files. So: say so, listen for that one message on the
window's own procedure, and hand the paths to Tk on its own thread with `after`.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
from typing import Callable

WM_DROPFILES = 0x0233
WM_COPYGLOBALDATA = 0x0049
GWLP_WNDPROC = -4
GA_ROOT = 2
MSGFLT_ALLOW = 1

_WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM
)
_keep_alive: list = []  # the callbacks Windows holds pointers to must outlive the window


def enable_drop(widget, on_drop: Callable[[list[Path]], None]) -> bool:
    """Make `widget`'s top-level window accept drops; `on_drop` gets the paths on the Tk
    thread. Returns False where this is not Windows."""
    if os.name != "nt":
        return False
    user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
    user32.SetWindowLongPtrW.restype = ctypes.c_longlong
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
    user32.CallWindowProcW.restype = ctypes.c_longlong
    user32.CallWindowProcW.argtypes = [ctypes.c_longlong, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
    shell32.DragFinish.argtypes = [wintypes.HANDLE]

    child = widget.winfo_id()
    top = user32.GetAncestor(child, GA_ROOT)
    for hwnd in {child, top}:
        shell32.DragAcceptFiles(hwnd, True)
        # An elevated launcher would otherwise be shielded from Explorer's drops.
        try:
            user32.ChangeWindowMessageFilterEx(hwnd, WM_DROPFILES, MSGFLT_ALLOW, None)
            user32.ChangeWindowMessageFilterEx(hwnd, WM_COPYGLOBALDATA, MSGFLT_ALLOW, None)
        except Exception:
            pass

    def make_proc(hwnd):
        previous = 0

        def proc(h, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                count = shell32.DragQueryFileW(wparam, 0xFFFFFFFF, None, 0)
                paths = []
                for index in range(count):
                    length = shell32.DragQueryFileW(wparam, index, None, 0)
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    shell32.DragQueryFileW(wparam, index, buffer, length + 1)
                    paths.append(Path(buffer.value))
                shell32.DragFinish(wparam)
                widget.after(0, on_drop, paths)
                return 0
            return user32.CallWindowProcW(previous, h, msg, wparam, lparam)

        callback = _WNDPROC(proc)
        previous = user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(callback, ctypes.c_void_p).value)
        _keep_alive.append(callback)

    for hwnd in {child, top}:
        make_proc(hwnd)
    return True


def simulate_drop(widget, paths: list[Path]) -> None:
    """Send the window a real WM_DROPFILES carrying `paths` (tests: the same road a drop
    from Explorer takes, without a mouse)."""
    kernel32, user32 = ctypes.windll.kernel32, ctypes.windll.user32
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    text = "\0".join(str(p) for p in paths) + "\0\0"
    payload = text.encode("utf-16-le")
    header = 20  # DROPFILES: pFiles(4) + pt(8) + fNC(4) + fWide(4)
    handle = kernel32.GlobalAlloc(0x0042, header + len(payload))  # GMEM_MOVEABLE | GMEM_ZEROINIT
    address = kernel32.GlobalLock(handle)
    ctypes.memmove(address, (ctypes.c_uint32 * 1)(header), 4)
    ctypes.memmove(address + 16, (ctypes.c_uint32 * 1)(1), 4)  # fWide = 1
    ctypes.memmove(address + header, payload, len(payload))
    kernel32.GlobalUnlock(handle)
    user32.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW(widget.winfo_id(), WM_DROPFILES, handle, 0)
