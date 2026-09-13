from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_DESCRIBE_MODEL,
    DEFAULT_DESCRIBE_PROMPT,
    DEFAULT_OCR_MODE,
    DEFAULT_OUTPUT_FORMATS,
    DEFAULT_SPEECH_MODEL,
    DESCRIBE_MODELS,
    OCR_ENGINES,
    OCR_MODES,
    OUTPUT_FORMATS,
    SPEECH_MODELS,
)


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
    ocr_mode: str = DEFAULT_OCR_MODE
    ocr_engine: str = "auto"
    ocr_lang: str = ""
    allow_external_plugins: bool = False
    portable_tesseract_enabled: bool = False
    portable_tesseract_path: str = ""
    run_as_admin: bool = False
    show_tooltips: bool = True
    # Technical documents
    keep_pictures: bool = True
    enrich_formula: bool = False
    enrich_chart: bool = False
    describe_pictures: bool = False
    describe_model: str = DEFAULT_DESCRIBE_MODEL
    describe_prompt: str = DEFAULT_DESCRIBE_PROMPT
    speech_model: str = DEFAULT_SPEECH_MODEL
    video_speakers: bool = True
    # Batch behaviour
    skip_converted: bool = True
    retry_failed: bool = True
    notify_done: bool = True
    explorer_menu: bool = False
    # Updates
    update_models: bool = True
    # Presets: name -> the settings fields a preset carries
    presets: dict = field(default_factory=dict)
    theme: str = "system"
    launcher_update_key: str = ""

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
        if "ocr_mode" not in data and "use_ocr" in data:
            # settings written before 2026-09-12 round 4 had an on/off tick
            settings.ocr_mode = "auto" if data["use_ocr"] else "off"
        if settings.ocr_mode not in {name for name, _ in OCR_MODES}:
            settings.ocr_mode = DEFAULT_OCR_MODE
        if not isinstance(settings.presets, dict):
            settings.presets = {}
        if settings.theme not in ("light", "dark", "system"):
            settings.theme = "system"
        if not isinstance(settings.describe_prompt, str) or not settings.describe_prompt.strip():
            settings.describe_prompt = DEFAULT_DESCRIBE_PROMPT
        settings.ocr_lang = str(settings.ocr_lang or "").strip()

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
        for field_name in ("keep_pictures", "enrich_formula", "enrich_chart", "describe_pictures",
                           "video_speakers", "update_models", "skip_converted", "retry_failed",
                           "notify_done", "explorer_menu"):
            setattr(settings, field_name, bool(getattr(settings, field_name)))
        if settings.speech_model not in {name for name, _, _ in SPEECH_MODELS}:
            settings.speech_model = DEFAULT_SPEECH_MODEL
        if settings.describe_model not in {name for name, _ in DESCRIBE_MODELS}:
            settings.describe_model = DEFAULT_DESCRIBE_MODEL
        return settings

    def conversion_options(self):
        from .docling_cli import ConversionOptions
        return ConversionOptions(
            formats=tuple(self.output_formats),
            ocr_mode=self.ocr_mode,
            ocr_engine=self.ocr_engine,
            ocr_lang=self.ocr_lang,
            allow_external_plugins=self.allow_external_plugins,
            portable_tesseract_enabled=self.portable_tesseract_enabled,
            portable_tesseract_path=self.portable_tesseract_path,
            keep_pictures=self.keep_pictures,
            enrich_formula=self.enrich_formula,
            enrich_chart=self.enrich_chart,
            describe_pictures=self.describe_pictures,
            describe_model=self.describe_model,
            describe_prompt=self.describe_prompt,
            speech_model=self.speech_model,
            video_speakers=self.video_speakers,
        )

    def save(self) -> Path:
        path = _settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return path
