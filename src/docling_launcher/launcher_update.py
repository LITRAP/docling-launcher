"""The launcher updating itself from its GitHub releases.

A release is a tag "v<version>" with DoclingLauncher.exe attached. At start the launcher
asks GitHub once for the latest release; if its version is newer than APP_VERSION, the
header offers it. Installing downloads the exe beside the running one as
DoclingLauncher.new.exe, then a tiny batch script waits for the launcher to exit, keeps the
old exe as DoclingLauncher.old.exe, puts the new one in place and starts it. On its first
start the new launcher removes the old copy - if it never starts, the old copy is still
there to run by hand.

The repository is private, so GitHub wants a key: a fine-grained personal access token
with read access to this one repository's contents, pasted once into the launcher's
settings ("update key"). Without it the check reports that it needs one.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
from typing import Callable

from .constants import APP_VERSION, LAUNCHER_REPO
from .updates import version_key

API_LATEST = f"https://api.github.com/repos/{LAUNCHER_REPO}/releases/latest"
EXE_NAME = "DoclingLauncher.exe"


@dataclass(frozen=True)
class LauncherRelease:
    version: str
    published: str | None
    notes: str
    asset_url: str | None   # API URL of the exe (works for private repos with a key)
    asset_size: int

    @property
    def newer(self) -> bool:
        return version_key(self.version) > version_key(APP_VERSION)


def _headers(key: str | None, binary: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "application/octet-stream" if binary else "application/vnd.github+json",
        "User-Agent": "DoclingLauncher",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def check(key: str | None, timeout: float = 8.0) -> LauncherRelease | str:
    """The latest release, or a short sentence saying why it could not be read."""
    request = urllib.request.Request(API_LATEST, headers=_headers(key))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            return "needs the update key" if not key else "the update key was refused"
        return f"GitHub answered {exc.code}"
    except Exception:
        return "could not reach GitHub"
    tag = str(data.get("tag_name", "")).lstrip("vV")
    asset = next((a for a in data.get("assets", []) if a.get("name") == EXE_NAME), None)
    return LauncherRelease(
        version=tag,
        published=(data.get("published_at") or "")[:10] or None,
        notes=data.get("body") or "",
        asset_url=asset.get("url") if asset else None,
        asset_size=int(asset.get("size", 0)) if asset else 0,
    )


def running_exe() -> Path | None:
    return Path(sys.executable) if getattr(sys, "frozen", False) else None


def download(release: LauncherRelease, key: str | None, log: Callable[[str], None]) -> Path | None:
    exe = running_exe()
    if not exe or not release.asset_url:
        log("The launcher can only update itself when it runs as the built exe.")
        return None
    target = exe.with_name("DoclingLauncher.new.exe")
    request = urllib.request.Request(release.asset_url, headers=_headers(key, binary=True))
    try:
        with urllib.request.urlopen(request, timeout=30) as response, target.open("wb") as out:
            done = 0
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
        if release.asset_size and target.stat().st_size != release.asset_size:
            log("The downloaded launcher is not the size GitHub announced; not installing it.")
            target.unlink(missing_ok=True)
            return None
    except Exception as exc:
        log(f"Could not download the new launcher: {exc}")
        target.unlink(missing_ok=True)
        return None
    log(f"Downloaded launcher {release.version} ({done / 1e6:.1f} MB).")
    return target


def install(new_exe: Path) -> subprocess.Popen | None:
    """Start the swap script; the caller then closes the launcher. Returns the script's
    process, or None when not running as the exe."""
    exe = running_exe()
    if not exe:
        return None
    script = exe.with_name("update_launcher.cmd")
    old = exe.with_name("DoclingLauncher.old.exe")
    lines = [
        "@echo off",
        f"set PID={os.getpid()}",
        ":wait",
        'tasklist /FI "PID eq %PID%" 2>NUL | find "%PID%" >NUL',
        "if not errorlevel 1 (timeout /t 1 /nobreak >NUL & goto wait)",
        f'if exist "{old}" del /f /q "{old}"',
        f'move /y "{exe}" "{old}" >NUL',
        f'move /y "{new_exe}" "{exe}" >NUL',
        f'start "" "{exe}"',
        'del /f /q "%~f0"',
    ]
    script.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0),
        close_fds=True,
    )


def cleanup_after_update() -> str | None:
    """On a normal start: the previous exe left by a swap is no longer needed."""
    exe = running_exe()
    if not exe:
        return None
    old = exe.with_name("DoclingLauncher.old.exe")
    if old.exists():
        try:
            old.unlink()
            return f"Launcher updated to {APP_VERSION}; the previous copy was removed."
        except OSError:
            return None
    return None
