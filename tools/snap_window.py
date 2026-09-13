"""Pictures of the launcher's tabs, taken without ever showing the owner a window.

    .venv\\Scripts\\python.exe tools\\snap_window.py <folder> [light|dark]

Writes convert.png, settings.png, settings_no_speakers.png, updates.png, log.png into
<folder>. The window is shown at 1 % opacity, as a tool window (no taskbar button) that
Windows never activates (WS_EX_NOACTIVATE), at the bottom of the pile - so the owner's
focus never moves and nothing readable appears, yet the compositor keeps the whole surface
and PrintWindow(PW_RENDERFULLCONTENT) can print it. (A window parked entirely off-screen
has no surface to print, and Tk paints nothing into a print DC: both came out white.)

The tests' overrides apply: settings live in a throw-away APPDATA, Docling is the stand-in,
so nothing of the owner's is read or written.
"""
from __future__ import annotations

import ctypes
import os
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def print_window(hwnd: int, path: Path) -> tuple[int, int]:
    from PIL import Image
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(memory_dc, bitmap)
    user32.PrintWindow(hwnd, memory_dc, 2)  # PW_RENDERFULLCONTENT
    info = BITMAPINFOHEADER()
    info.biSize, info.biWidth, info.biHeight, info.biPlanes, info.biBitCount = ctypes.sizeof(info), width, -height, 1, 32
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer, ctypes.byref(info), 0)
    Image.frombuffer("RGB", (width, height), buffer.raw, "raw", "BGRX", 0, 1).save(path)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory_dc)
    user32.ReleaseDC(hwnd, window_dc)
    return width, height


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else Path(tempfile.mkdtemp(prefix="launcher_snaps_"))
    theme = argv[1] if len(argv) > 1 else "light"
    out.mkdir(parents=True, exist_ok=True)
    home = Path(tempfile.mkdtemp(prefix="snap_home_"))
    os.environ.update({
        "DOCLING_EXE": str(ROOT / "tests" / "fake_docling.cmd"),
        "DOCLING_CONVERT_TOOL": str(ROOT / "tests" / "fake_docling.py"),
        "APPDATA": str(home / "appdata"),
    })
    import tkinter as tk
    from docling_launcher import app as app_module

    root = tk.Tk()
    root.withdraw()
    app = app_module.DoclingLauncherApp(root)
    app._selftest = True  # never saves settings
    app.theme_var.set(theme)
    app._apply_theme()
    root.attributes("-alpha", 0.01)
    root.attributes("-toolwindow", True)
    root.update_idletasks()
    hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)
    GWL_EXSTYLE, WS_EX_NOACTIVATE = -20, 0x08000000
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)
    screen_w, screen_h = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
    root.geometry(f"1180x900+{screen_w - 1180}+{screen_h - 900}")
    root.deiconify()
    ctypes.windll.user32.SetWindowPos(hwnd, 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # HWND_BOTTOM, NOSIZE|NOMOVE|NOACTIVATE
    root.update()

    def snap(name: str) -> None:
        root.update()
        size = print_window(hwnd, out / f"{name}.png")
        print("saved", out / f"{name}.png", size)

    for index, name in enumerate(("convert", "settings", "updates", "log")):
        app.notebook.select(index)
        snap(name)
        if name == "settings":
            app.video_speakers_var.set(False)
            app._sync_speakers_state()
            snap("settings_no_speakers")
            app.video_speakers_var.set(True)
            app._sync_speakers_state()
    root.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
