from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import os
import shutil
import subprocess
from typing import Iterable

from .docling_cli import resolve_docling, resolve_python


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    ok: bool
    detail: str


DEPENDENCIES = {
    "RapidOCR": ("rapidocr_onnxruntime", "rapidocr"),
    "EasyOCR": ("easyocr",),
    "Tesseract": ("tesseract",),
    "OnnxTR": ("onnxtr",),
}


def _module_available_current(names: Iterable[str]) -> str | None:
    for name in names:
        if importlib.util.find_spec(name):
            return name
    return None


def _module_available_external(names: Iterable[str]) -> str | None:
    python = resolve_python()
    if not python:
        return None

    code = (
        "import importlib.util, sys; "
        f"names={list(names)!r}; "
        "found=next((n for n in names if importlib.util.find_spec(n)), ''); "
        "print(found); sys.exit(0 if found else 1)"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None
    found = result.stdout.strip()
    return found or None


def _tesseract_available(env: dict[str, str] | None) -> str | None:
    # Look where a run would look: on the PATH the portable-Tesseract setting builds,
    # not the launcher's own. Otherwise a working portable Tesseract reads as "Missing".
    path = (env or os.environ).get("PATH")
    return shutil.which("tesseract", path=path)


def check_dependency(
    name: str, modules: tuple[str, ...], env: dict[str, str] | None = None
) -> DependencyStatus:
    if name == "Tesseract":
        found = _tesseract_available(env)
        if found:
            return DependencyStatus(name, True, found)
        return DependencyStatus(name, False, "tesseract.exe not found on PATH")

    found = _module_available_current(modules) or _module_available_external(modules)
    if found:
        return DependencyStatus(name, True, f"Python module: {found}")
    return DependencyStatus(name, False, f"Missing module: {' or '.join(modules)}")


def check_all_dependencies(env: dict[str, str] | None = None) -> list[DependencyStatus]:
    statuses = [check_dependency(name, modules, env) for name, modules in DEPENDENCIES.items()]
    docling = resolve_docling()
    detail = str(docling) if docling else "docling.exe not found"
    statuses.insert(0, DependencyStatus("Docling CLI", bool(docling), detail))
    return statuses


def speech_available() -> bool:
    """Docling sends sound and video through Whisper; without it every such file fails
    after a 5-second start-up. Ask once per batch instead."""
    return bool(_module_available_current(("whisper",)) or _module_available_external(("whisper",)))
