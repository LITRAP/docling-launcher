"""The AI models behind the launcher's abilities: what is on disk, what the model hub has,
and replacing one safely.

All the real work happens in assets/models_tool.py, run with Docling's own python, because
the model library (huggingface_hub) and Whisper live there and not in the exe. This module
only builds the request, runs it, and reads the answer.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import subprocess
from typing import Callable

from .assets import asset_path
from .constants import MODELS
from .docling_cli import CREATE_NO_WINDOW, ProcessJob, resolve_python, stream_process


@dataclass(frozen=True)
class ModelStatus:
    label: str
    repo: str            # hub repo, or "whisper:<name>" for the speech model
    revision: str
    ability: str | None  # settings field that needs it; None = every conversion
    gb: float
    installed_sha: str | None
    installed_on: str | None
    latest_sha: str | None
    latest_on: str | None
    state: str           # missing | current | newer | offline | unchecked

    @property
    def update_available(self) -> bool:
        return self.state == "newer"

    @property
    def missing(self) -> bool:
        return self.state == "missing"

    @property
    def installed_text(self) -> str:
        if not self.installed_sha:
            return "—"
        return self.installed_sha if self.repo.startswith(("whisper:", "speakers:")) else self.installed_sha[:8]

    @property
    def latest_text(self) -> str:
        if not self.latest_sha:
            return "—"
        return self.latest_sha if self.repo.startswith(("whisper:", "speakers:")) else self.latest_sha[:8]

    def state_text(self, needed: bool) -> str:
        if self.state == "missing":
            size = f"{self.gb:.1f} GB" if self.gb >= 0.1 else "small"
            return f"Not downloaded ({size})" + (" — needed by a ticked ability" if needed else "")
        if self.state == "newer":
            return "Newer model available"
        if self.state == "current":
            return "Up to date"
        if self.state == "offline":
            return "Could not check"
        return "Not checked"


def _hub_env() -> dict[str, str]:
    """Same rule as every Docling run: no symbolic links in the model cache on Windows."""
    env = os.environ.copy()
    env["HF_HUB_DISABLE_SYMLINKS"] = "1"
    env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    return env


def _spec(models=MODELS) -> list:
    return [[label, repo, revision, gb] for label, repo, revision, _ability, gb in models]


def _run_tool(args: list[str], timeout: int = 60) -> list[dict]:
    python = resolve_python()
    tool = asset_path("models_tool.py")
    if not python or not tool.exists():
        return []
    try:
        result = subprocess.run(
            [str(python), str(tool), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=CREATE_NO_WINDOW, env=_hub_env(),
        )
    except Exception:
        return []
    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def check_models(speech_model: str, online: bool = True) -> list[ModelStatus]:
    """One status per model in MODELS plus the chosen speech model, in table order."""
    rows = {row["repo"]: row for row in _run_tool(["check" if online else "check-offline", json.dumps(_spec()), speech_model])}
    statuses = []
    for label, repo, revision, ability, gb in MODELS:
        row = rows.get(repo, {})
        statuses.append(ModelStatus(
            label, repo, revision, ability, gb,
            row.get("installed_sha"), row.get("installed_on"), row.get("latest_sha"), row.get("latest_on"),
            row.get("state", "unchecked"),
        ))
    row = rows.get(f"whisper:{speech_model}", {})
    statuses.append(ModelStatus(
        "Speech model", f"whisper:{speech_model}", speech_model, "speech", 0.0,
        row.get("installed_sha"), row.get("installed_on"), row.get("latest_sha"), row.get("latest_on"),
        row.get("state", "unchecked"),
    ))
    return statuses


def model_targets(statuses: list[ModelStatus], enabled: Callable[[str | None], bool]) -> list[ModelStatus]:
    """What Update would fetch: every model with a newer version, and every missing model
    whose ability is ticked (or that every conversion needs)."""
    return [s for s in statuses if s.update_available or (s.missing and enabled(s.ability))]


def run_model_update(targets: list[ModelStatus], log: Callable[[str], None], job: ProcessJob | None = None) -> int:
    python = resolve_python()
    tool = asset_path("models_tool.py")
    if not python or not tool.exists():
        log("The model tool or Docling's python was not found.")
        return 1
    hub = [[t.label, t.repo, t.revision, t.gb] for t in targets if not t.repo.startswith("whisper:")]
    whisper = next((t.revision for t in targets if t.repo.startswith("whisper:")), "-")
    return stream_process([str(python), str(tool), "update", json.dumps(hub), whisper], _hub_env(), log, job=job)
