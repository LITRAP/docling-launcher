from __future__ import annotations

from dataclasses import dataclass
import importlib.util
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


def _tesseract_available() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    return None


def check_dependency(name: str, modules: tuple[str, ...]) -> DependencyStatus:
    if name == "Tesseract":
        found = _tesseract_available()
        if found:
            return DependencyStatus(name, True, found)
        return DependencyStatus(name, False, "tesseract.exe not found on PATH")

    found = _module_available_current(modules) or _module_available_external(modules)
    if found:
        return DependencyStatus(name, True, f"Python module: {found}")
    return DependencyStatus(name, False, f"Missing module: {' or '.join(modules)}")


def check_all_dependencies() -> list[DependencyStatus]:
    statuses = [check_dependency(name, modules) for name, modules in DEPENDENCIES.items()]
    docling = resolve_docling()
    detail = str(docling) if docling else "docling.exe not found"
    statuses.insert(0, DependencyStatus("Docling CLI", bool(docling), detail))
    return statuses


def get_docling_version() -> str:
    docling = resolve_docling()
    if not docling:
        return "Docling CLI was not found."
    try:
        result = subprocess.run(
            [str(docling), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        return f"Unable to run docling --version: {exc}"
    output = (result.stdout or result.stderr).strip()
    return output or f"docling --version exited with code {result.returncode}"


def check_package_updates(package_names: list[str], timeout: int = 120) -> tuple[int, str]:
    python = resolve_python()
    if not python:
        return 1, "Python executable for the Docling environment was not found."
    command = [str(python), "-m", "pip", "list", "--outdated", "--format=columns"]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        return 1, f"Unable to check package updates: {exc}"

    text = (result.stdout or result.stderr).strip()
    if not text:
        text = "No outdated packages reported."

    package_set = {name.lower() for name in package_names}
    lines = text.splitlines()
    if len(lines) > 2:
        filtered = lines[:2] + [
            line
            for line in lines[2:]
            if line.split(maxsplit=1)[0].lower() in package_set
        ]
        text = "\n".join(filtered) if len(filtered) > 2 else "Selected packages appear current."
    return result.returncode, text
