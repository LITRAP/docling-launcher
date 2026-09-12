from __future__ import annotations

APP_NAME = "Docling Launcher"
APP_VERSION = "1.1.0"

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

# The file Docling writes for each output format, next to the source's stem.
# Measured on Docling 2.115 (doclang is ".dclg.xml", not ".xml"; text is ".txt").
FORMAT_OUTPUT_SUFFIXES = {
    "md": ".md",
    "json": ".json",
    "html": ".html",
    "text": ".txt",
    "doclang": ".dclg.xml",
    "doctags": ".doctags",
    "vtt": ".vtt",
    "dclx": ".dclx",
}

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

# Documents: everything Docling's own format table accepts (docling 2.115), minus plain
# .txt, which Docling would only re-wrap as Markdown.
DOCUMENT_INPUT_EXTENSIONS = {
    ".pdf",
    ".docx", ".docm", ".dotx", ".dotm", ".doc", ".dot",
    ".pptx", ".pptm", ".ppsx", ".ppsm", ".potx", ".potm", ".ppt", ".pps", ".pot",
    ".xlsx", ".xlsm", ".xls", ".xlt",
    ".odt", ".ott", ".ods", ".ots", ".odp", ".otp",
    ".epub",
    ".html", ".htm", ".xhtml",
    ".md", ".rmd", ".qmd",
    ".adoc", ".asc", ".asciidoc",
    ".tex", ".latex",
    ".eml",
    ".csv",
    ".xml", ".nxml", ".xbrl",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
}

# Sound and video go through Docling's speech pipeline, which needs the Whisper library.
MEDIA_INPUT_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg",
    ".mp4", ".mkv", ".mov", ".avi", ".webm",
}

SUPPORTED_INPUT_EXTENSIONS = DOCUMENT_INPUT_EXTENSIONS | MEDIA_INPUT_EXTENSIONS

# What one click of "Update" brings up to date, in the order the Updates table shows them.
# Only the ones actually installed are shown or touched.
UPDATE_PACKAGES = [
    ("Docling", "docling"),
    ("Docling core", "docling-core"),
    ("Docling parser", "docling-parse"),
    ("Docling models", "docling-ibm-models"),
    ("OnnxTR bridge", "docling-ocr-onnxtr"),
    ("RapidOCR", "rapidocr"),
    ("RapidOCR (legacy)", "rapidocr-onnxruntime"),
    ("EasyOCR", "easyocr"),
    ("OnnxTR", "onnxtr"),
    ("Tesserocr", "tesserocr"),
    ("Whisper (speech)", "openai-whisper"),
]

PYPI_JSON_URL = "https://pypi.org/pypi/{name}/json"

TOOLTIP_TEXT = {
    "input_folder": "Folder containing the documents to convert. Batch mode scans it recursively; selected-files mode uses it as the allowed source folder.",
    "input_scope": "When checked, every supported file in the input folder is converted. Clear it to choose one or more specific files.",
    "selected_files": "Choose one or more supported input files from the selected input folder.",
    "output_folder": "Folder where converted files are written for mirror or single-folder modes.",
    "mode_mirror": "Keeps the same relative subfolders under the chosen output folder.",
    "mode_beside": "Writes each conversion into the same folder as its source file.",
    "mode_flat": "Writes every conversion into the selected output folder.",
    "formats": "Docling output types. Select at least one.",
    "use_ocr": "On: Docling reads text inside scans and pictures (its thorough default; 2-3x slower on text PDFs with images). Off: only the text the file already contains - fastest, right for digital PDFs and e-books; a scan then comes out empty.",
    "ocr_engine": "OCR engine passed to Docling with --ocr-engine.",
    "plugins": "Allows Docling to load installed third-party plugins.",
    "portable_tesseract": "Prepends a portable Tesseract folder to PATH for this run.",
    "portable_tesseract_path": "Folder containing tesseract.exe, or its parent install folder.",
    "command_preview": "Representative command for one file. The run starts Docling once per output folder, with all of that folder's files in one go.",
    "run_admin": "Runs the batch through a Windows UAC elevation prompt.",
    "stop": "Stops Docling now. The file being converted is abandoned; files already finished are kept.",
    "check_updates": "Asks the Python package index which versions of Docling and its OCR add-ins are current. One small request per component.",
    "update": "Downloads and installs the newer versions into Docling's environment. A restore point is saved first.",
    "go_back": "Reinstalls the exact versions saved before the last update.",
}
