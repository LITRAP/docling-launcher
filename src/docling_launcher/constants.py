from __future__ import annotations

APP_NAME = "Docling Launcher"
APP_VERSION = "1.0.0"

OUTPUT_FORMATS = [
    ("Markdown", "md"),
    ("JSON", "json"),
    ("HTML", "html"),
    ("Text", "text"),
    ("DocLang XML", "doclang"),
    ("Doctags", "doctags"),
    ("WebVTT", "vtt"),
    ("DCLX", "dclx"),
]

DEFAULT_OUTPUT_FORMATS = ["md"]

OCR_ENGINES = [
    "auto",
    "rapidocr",
    "easyocr",
    "tesseract",
    "tesserocr",
    "onnxtr",
    "kserve_v2_ocr",
    "nemotron-ocr",
    "ocrmac",
]

CONVERSION_MODES = {
    "mirror": "Mirror input folder structure into output folder",
    "beside": "Save converted files beside the original files",
    "flat": "Save all converted files into one output folder",
}

SUPPORTED_INPUT_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".xhtml",
    ".md",
    ".adoc",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
    ".xml",
    ".wav",
    ".mp3",
    ".m4a",
    ".mp4",
}

TOOLTIP_TEXT = {
    "input_folder": "Folder containing the documents to convert. Batch mode scans it recursively; selected-files mode uses it as the allowed source folder.",
    "input_scope": "When checked, every supported file in the input folder is converted. Clear it to choose one or more specific files.",
    "selected_files": "Choose one or more supported input files from the selected input folder.",
    "output_folder": "Folder where converted files are written for mirror or single-folder modes.",
    "mode_mirror": "Keeps the same relative subfolders under the chosen output folder.",
    "mode_beside": "Writes each conversion into the same folder as its source file.",
    "mode_flat": "Writes every conversion into the selected output folder.",
    "formats": "Docling output types. Select at least one.",
    "ocr_engine": "OCR engine passed to Docling with --ocr-engine.",
    "plugins": "Allows Docling to load installed third-party plugins.",
    "portable_tesseract": "Prepends a portable Tesseract folder to PATH for this run.",
    "portable_tesseract_path": "Folder containing tesseract.exe, or its parent install folder.",
    "command_preview": "Representative command for one file. The run creates one command per input file.",
    "run_admin": "Runs the batch through a Windows UAC elevation prompt.",
}
