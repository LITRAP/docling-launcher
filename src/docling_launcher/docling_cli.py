from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .constants import SUPPORTED_INPUT_EXTENSIONS


@dataclass(frozen=True)
class CommandPlan:
    source: Path
    output_dir: Path
    command: list[str]
    preview: str
    env: dict[str, str]


def app_base_candidates() -> list[Path]:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir, exe_dir.parent, Path.cwd()])
    else:
        module_root = Path(__file__).resolve().parents[2]
        candidates.extend([module_root, module_root.parent, Path.cwd()])

    unique: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved not in unique:
            unique.append(resolved)
    return unique


def _candidate_script_paths(name: str) -> list[Path]:
    suffixes = [name]
    if os.name == "nt" and not name.lower().endswith(".exe"):
        suffixes.insert(0, f"{name}.exe")

    candidates: list[Path] = []
    for base in app_base_candidates():
        for suffix in suffixes:
            candidates.extend(
                [
                    base / suffix,
                    base / ".venv" / "Scripts" / suffix,
                    base / "venv" / "Scripts" / suffix,
                    base / "Scripts" / suffix,
                ]
            )
    return candidates


def resolve_executable(name: str, env_var: str | None = None) -> Path | None:
    if env_var:
        override = os.environ.get(env_var)
        if override and Path(override).exists():
            return Path(override)

    for candidate in _candidate_script_paths(name):
        if candidate.exists():
            return candidate

    found = shutil.which(name)
    return Path(found) if found else None


def resolve_docling() -> Path | None:
    return resolve_executable("docling", "DOCLING_EXE")


def resolve_python() -> Path | None:
    return resolve_executable("python", "DOCLING_PYTHON")


def discover_input_files(input_folder: Path) -> list[Path]:
    files: list[Path] = []
    for path in input_folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS:
            files.append(path)
    return sorted(files, key=lambda item: str(item).lower())


def output_dir_for(source: Path, input_root: Path, output_root: Path, mode: str) -> Path:
    if mode == "beside":
        return source.parent
    if mode == "flat":
        return output_root
    relative_parent = source.parent.relative_to(input_root)
    return output_root / relative_parent


def environment_for_run(
    portable_tesseract_enabled: bool,
    portable_tesseract_path: str,
    use_launcher_temp: bool = True,
) -> dict[str, str]:
    env = os.environ.copy()
    if use_launcher_temp:
        local_appdata = os.environ.get("LOCALAPPDATA")
        temp_base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        temp_dir = temp_base / "DoclingLauncher" / "Temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        env["TEMP"] = str(temp_dir)
        env["TMP"] = str(temp_dir)

    if not portable_tesseract_enabled or not portable_tesseract_path.strip():
        return env

    raw_path = Path(portable_tesseract_path.strip()).expanduser()
    candidates = [raw_path, raw_path / "bin"]
    tesseract_dir = next(
        (candidate for candidate in candidates if (candidate / "tesseract.exe").exists()),
        raw_path,
    )
    env["PATH"] = f"{tesseract_dir}{os.pathsep}{env.get('PATH', '')}"

    tessdata_candidates = [raw_path / "tessdata", tesseract_dir / "tessdata"]
    tessdata = next((candidate for candidate in tessdata_candidates if candidate.exists()), None)
    if tessdata:
        env["TESSDATA_PREFIX"] = str(tessdata)
    return env


def build_command_plan(
    source: Path,
    output_dir: Path,
    formats: list[str],
    ocr_engine: str,
    allow_external_plugins: bool,
    portable_tesseract_enabled: bool,
    portable_tesseract_path: str,
    use_launcher_temp: bool = True,
) -> CommandPlan:
    docling = resolve_docling()
    executable = str(docling) if docling else "docling"
    command = [executable, "convert"]

    if allow_external_plugins:
        command.append("--allow-external-plugins")
    if ocr_engine:
        command.extend(["--ocr-engine", ocr_engine])
    for fmt in formats:
        command.extend(["--to", fmt])

    command.extend([str(source), "--output", str(output_dir)])

    preview_parts = ["docling" if Path(command[0]).name.lower().startswith("docling") else command[0]]
    preview_parts.extend(command[1:])
    preview = subprocess.list2cmdline(preview_parts)

    return CommandPlan(
        source=source,
        output_dir=output_dir,
        command=command,
        preview=preview,
        env=environment_for_run(
            portable_tesseract_enabled,
            portable_tesseract_path,
            use_launcher_temp=use_launcher_temp,
        ),
    )


def build_preview(
    input_folder: str,
    output_folder: str,
    mode: str,
    formats: list[str],
    ocr_engine: str,
    allow_external_plugins: bool,
    portable_tesseract_enabled: bool,
    portable_tesseract_path: str,
    source_path: Path | None = None,
) -> str:
    input_root = Path(input_folder) if input_folder else Path("<input-folder>")
    output_root = Path(output_folder) if output_folder else Path("<output-folder>")
    source = source_path or input_root / "<input-file>"
    output_dir = output_dir_for(source, input_root, output_root, mode)
    plan = build_command_plan(
        source=source,
        output_dir=output_dir,
        formats=formats or ["md"],
        ocr_engine=ocr_engine or "auto",
        allow_external_plugins=allow_external_plugins,
        portable_tesseract_enabled=portable_tesseract_enabled,
        portable_tesseract_path=portable_tesseract_path,
        use_launcher_temp=False,
    )
    return plan.preview
