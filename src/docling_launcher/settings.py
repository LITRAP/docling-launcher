from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Any

from .constants import DEFAULT_OUTPUT_FORMATS, OCR_ENGINES, OUTPUT_FORMATS


def _settings_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "DoclingLauncher" / "settings.json"


VALID_FORMATS = {value for _, value in OUTPUT_FORMATS}


@dataclass
class LauncherSettings:
    input_folder: str = ""
    output_folder: str = ""
    convert_all_files: bool = True
    selected_input_files: list[str] = field(default_factory=list)
    conversion_mode: str = "mirror"
    output_formats: list[str] = field(default_factory=lambda: list(DEFAULT_OUTPUT_FORMATS))
    ocr_engine: str = "auto"
    allow_external_plugins: bool = False
    portable_tesseract_enabled: bool = False
    portable_tesseract_path: str = ""
    run_as_admin: bool = False
    show_tooltips: bool = True

    @classmethod
    def load(cls) -> "LauncherSettings":
        path = _settings_path()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception:
            return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LauncherSettings":
        settings = cls()
        for key in asdict(settings):
            if key in data:
                setattr(settings, key, data[key])

        settings.output_formats = [
            fmt for fmt in settings.output_formats if fmt in VALID_FORMATS
        ] or list(DEFAULT_OUTPUT_FORMATS)
        if settings.ocr_engine not in OCR_ENGINES:
            settings.ocr_engine = "auto"
        if settings.conversion_mode not in {"mirror", "beside", "flat"}:
            settings.conversion_mode = "mirror"
        settings.convert_all_files = bool(settings.convert_all_files)
        if not isinstance(settings.selected_input_files, list):
            settings.selected_input_files = []
        else:
            settings.selected_input_files = [
                str(path) for path in settings.selected_input_files if isinstance(path, str)
            ]
        settings.allow_external_plugins = bool(settings.allow_external_plugins)
        settings.portable_tesseract_enabled = bool(settings.portable_tesseract_enabled)
        settings.run_as_admin = bool(settings.run_as_admin)
        settings.show_tooltips = bool(settings.show_tooltips)
        return settings

    def save(self) -> Path:
        path = _settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return path
