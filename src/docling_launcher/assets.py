from __future__ import annotations

from pathlib import Path
import sys


def asset_path(name: str) -> Path:
    """A file shipped inside the exe (PyInstaller unpacks to _MEIPASS) or beside the source."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "docling_launcher" / "assets" / name
    return Path(__file__).resolve().parent / "assets" / name
