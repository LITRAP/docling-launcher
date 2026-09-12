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
    statuses.insert(1, gpu_status())
    whisper = _module_available_current(("whisper",)) or _module_available_external(("whisper",))
    statuses.insert(2, DependencyStatus(
        "Speech (Whisper)", bool(whisper),
        "installed — sound and video are transcribed" if whisper else "not installed — sound and video are skipped",
    ))
    return statuses


def gpu_status() -> DependencyStatus:
    """Does Docling's AI library see a graphics card? Imports torch in Docling's
    environment (~2 s), so this runs only from the Check Extensions button."""
    python = resolve_python()
    if not python:
        return DependencyStatus("GPU", False, "Docling's python was not found")
    code = (
        "import torch; "
        "print(torch.__version__, '|', torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", code],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        return DependencyStatus("GPU", False, f"could not ask: {exc}")
    version, _, device = (result.stdout.strip() or "| ").partition("|")
    version, device = version.strip(), device.strip()
    if device:
        return DependencyStatus("GPU", True, f"{device} — in use (AI library {version})")
    if "+cu" in version:
        return DependencyStatus("GPU", False, f"GPU edition of the AI library ({version}) but no usable graphics card")
    return DependencyStatus("GPU", False, f"CPU-only AI library ({version or 'not found'}) — everything runs on the processor")


def speech_available() -> bool:
    """Docling sends sound and video through Whisper; without it every such file fails
    after a 5-second start-up. Ask once per batch instead."""
    return bool(_module_available_current(("whisper",)) or _module_available_external(("whisper",)))
