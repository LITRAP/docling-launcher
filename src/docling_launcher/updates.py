"""Keeping Docling current, from inside the launcher.

Three facts shape this module, all measured on 2026-09-12:

* ``pip list --outdated`` asks the package index about every one of the ~130 packages in
  Docling's environment and takes 19 s. Asking about the handful we care about takes 1 s.
* The installed version of a package is written in its metadata folder; reading it costs
  nothing and needs no process. ``docling --version`` imports the whole AI stack: 5 s.
* An upgrade is a ``pip install --upgrade`` inside Docling's own environment. pip keeps
  what already matches, so only the changed packages are downloaded (8 of them, no
  gigabyte libraries, in the rehearsal). Before it runs, ``pip freeze`` is saved as a
  restore point so "Go back" is one ``pip install -r`` away.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable
import urllib.request

from .constants import PYPI_JSON_URL, UPDATE_PACKAGES
from .docling_cli import CREATE_NO_WINDOW, ProcessJob, resolve_python, stream_process


def normalize(name: str) -> str:
    """The package index treats Foo_Bar, foo-bar and foo.bar as one name; so do we."""
    return re.sub(r"[-_.]+", "-", name).lower()


def version_key(text: str) -> tuple:
    """Order versions the way people read them: 2.126.0 comes after 2.99.0.

    The package index's own rules (``packaging``) when that library is present — it knows
    that 1.0rc1 comes before 1.0. Otherwise numeric parts compare as numbers and anything
    else as text after them, which is right for every plain X.Y.Z release."""
    try:
        from packaging.version import InvalidVersion, Version
        try:
            return (0, Version(text))
        except InvalidVersion:
            pass
    except ImportError:
        pass
    parts: list[tuple[int, object]] = []
    for piece in re.split(r"[.\-+]", text.strip()):
        if piece.isdigit():
            parts.append((0, int(piece)))
        else:
            match = re.match(r"(\d+)(.*)", piece)
            if match:
                parts.append((0, int(match.group(1))))
                parts.append((1, match.group(2)))
            else:
                parts.append((1, piece))
    return (1, tuple(parts))


@dataclass(frozen=True)
class PackageStatus:
    label: str
    name: str
    installed: str | None
    latest: str | None

    @property
    def update_available(self) -> bool:
        return bool(
            self.installed and self.latest and version_key(self.latest) > version_key(self.installed)
        )

    @property
    def state(self) -> str:
        if not self.installed:
            return "Not installed"
        if not self.latest:
            return "Could not check"
        return "Update available" if self.update_available else "Up to date"


def site_packages() -> Path | None:
    python = resolve_python()
    if not python:
        return None
    candidate = python.parent.parent / "Lib" / "site-packages"
    return candidate if candidate.is_dir() else None


def installed_versions(names: list[str]) -> dict[str, str | None]:
    """Read the version of each package straight from Docling's environment. No process."""
    wanted = {normalize(name) for name in names}
    found: dict[str, str | None] = {name: None for name in wanted}
    site = site_packages()
    if site is None:
        return found
    for dist in importlib.metadata.distributions(path=[str(site)]):
        raw = dist.metadata["Name"] if dist.metadata else None
        if not raw:
            continue
        name = normalize(raw)
        if name in wanted and found[name] is None:
            found[name] = dist.version
    return found


def _latest_version(name: str, timeout: float) -> str | None:
    try:
        with urllib.request.urlopen(PYPI_JSON_URL.format(name=name), timeout=timeout) as response:
            return json.load(response)["info"]["version"]
    except Exception:
        return None


def latest_versions(names: list[str], timeout: float = 6.0) -> dict[str, str | None]:
    """One small request per package, all at once. About a second in total."""
    names = list(dict.fromkeys(normalize(name) for name in names))
    if not names:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(names))) as pool:
        results = pool.map(lambda name: _latest_version(name, timeout), names)
    return dict(zip(names, results))


def check_updates(online: bool = True) -> list[PackageStatus]:
    """Status of every update-able package that is actually installed, in table order.

    Packages that are not installed are left out: nothing can be done about them here, and
    a row that cannot act is a row the owner has to read for nothing."""
    installed = installed_versions([name for _, name in UPDATE_PACKAGES])
    present = [(label, normalize(name)) for label, name in UPDATE_PACKAGES if installed.get(normalize(name))]
    latest = latest_versions([name for _, name in present]) if online and present else {}
    return [
        PackageStatus(label, name, installed[name], latest.get(name))
        for label, name in present
    ]


def upgrade_targets(statuses: list[PackageStatus]) -> list[str]:
    return [status.name for status in statuses if status.update_available]


# ----------------------------------------------------------------------------- restore points

def snapshot_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "DoclingLauncher" / "snapshots"


def take_snapshot() -> Path | None:
    """Write ``pip freeze`` of Docling's environment to a dated file. ~1 s."""
    python = resolve_python()
    if not python:
        return None
    try:
        result = subprocess.run(
            [str(python), "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    folder = snapshot_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now():%Y-%m-%d_%H%M%S}.txt"
    path.write_text(result.stdout, encoding="utf-8")
    return path


def snapshot_label(path: Path) -> str:
    """'2026-09-12 at 10:15' from a restore point's file name."""
    try:
        stamp = datetime.strptime(path.stem, "%Y-%m-%d_%H%M%S")
    except ValueError:
        return path.stem
    return f"{stamp:%Y-%m-%d} at {stamp:%H:%M}"


def snapshot_version(path: Path, name: str = "docling") -> str | None:
    """The version of `name` pinned inside a restore point."""
    wanted = normalize(name)
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "==" in line:
                pinned, version = line.split("==", 1)
                if normalize(pinned.strip()) == wanted:
                    return version.strip()
    except OSError:
        return None
    return None


def restore_point() -> tuple[Path, str] | None:
    """The newest restore point whose Docling differs from the installed one — the thing
    "Go back" would return to. None when there is nothing to go back to."""
    folder = snapshot_dir()
    if not folder.is_dir():
        return None
    current = installed_versions(["docling"]).get("docling")
    for path in sorted(folder.glob("*.txt"), reverse=True):
        pinned = snapshot_version(path)
        if pinned and pinned != current:
            return path, pinned
    return None


# ----------------------------------------------------------------------------- pip runs

def _pip(args: list[str], log: Callable[[str], None], job: ProcessJob | None) -> int:
    python = resolve_python()
    if not python:
        log("Python for the Docling environment was not found.")
        return 1
    command = [str(python), "-m", "pip", *args, "--progress-bar", "off"]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return stream_process(command, env, log, job=job)


def run_upgrade(names: list[str], log: Callable[[str], None], job: ProcessJob | None = None) -> int:
    return _pip(["install", "--upgrade", *names], log, job)


def run_restore(snapshot: Path, log: Callable[[str], None], job: ProcessJob | None = None) -> int:
    return _pip(["install", "-r", str(snapshot)], log, job)
