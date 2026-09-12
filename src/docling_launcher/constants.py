from __future__ import annotations

APP_NAME = "Docling Launcher"
APP_VERSION = "1.4.0"

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
    "ocr_mode": "Automatic: each PDF is checked for a text layer - scans and images are read with OCR, digital documents are not (2-3x faster, same text). Always: OCR on every page, for scans whose text layer is wrong. Off: never OCR; a scan then comes out empty.",
    "skip_converted": "A file whose outputs already exist and are newer than it is left alone. Untick to convert everything again.",
    "retry_failed": "Files that fail are tried once more at the end of the batch, on their own.",
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

# ----------------------------------------------------------------------------- input formats
# What Docling reads, grouped the way a person thinks about files. The extensions match
# Docling 2.126's own format table (docling.datamodel.base_models.FormatToExtensions).
INPUT_FORMAT_GROUPS = [
    ("PDF", "pdf", "Digital or scanned. Scans need OCR on."),
    ("Word", "docx, docm, dotx, dotm, doc, dot", ""),
    ("PowerPoint", "pptx, pptm, ppsx, ppsm, potx, potm, ppt, pps, pot", ""),
    ("Excel", "xlsx, xlsm, xls, xlt", "Each sheet becomes a table."),
    ("OpenDocument", "odt, ott, ods, ots, odp, otp", "LibreOffice / OpenOffice files."),
    ("E-books", "epub", ""),
    ("Web pages", "html, htm, xhtml", ""),
    ("Text with markup", "md, rmd, qmd, adoc, asc, asciidoc, tex, latex", "Markdown, AsciiDoc, LaTeX."),
    ("E-mail", "eml", "Saved e-mail messages."),
    ("Tables", "csv", ""),
    ("XML", "xml, nxml, xbrl", "Patent (USPTO), journal (JATS) and financial (XBRL) XML only."),
    ("Images", "png, jpg, jpeg, tif, tiff, bmp, webp", "Read with OCR; keep OCR on."),
    ("Sound", "wav, mp3, m4a, aac, flac, ogg", "Transcribed with the speech model."),
    ("Video", "mp4, mkv, mov, avi, webm", "The sound track is transcribed."),
]

# ----------------------------------------------------------------------------- AI models
# The models Docling 2.126 loads for each ability, with the revision it pins. The Updates
# table shows these beside the packages; a guard in tests/ reads Docling's own source and
# fails the day these drift from what the installed Docling really uses.
# (label, hub repo, revision, ability that needs it or None for always, approx download GB)
# An ability with a choice is written "ability:choice" and is "needed" only when that
# choice is the active one (app._ability_enabled reads it).
MODELS = [
    ("Layout model", "docling-project/docling-layout-heron", "main", None, 0.17),
    ("Table & picture-class model", "docling-project/docling-models", "v2.3.0", None, 0.36),
    ("Formula & code model", "docling-project/CodeFormulaV2", "main", "enrich_formula", 0.64),
    ("Picture-description model (small)", "HuggingFaceTB/SmolVLM-256M-Instruct", "main", "describe_pictures:small", 0.52),
    ("Picture-description model (better)", "ibm-granite/granite-vision-3.3-2b", "main", "describe_pictures:better", 6.0),
    # Docling pins this one to an exact commit (ChartExtractionModelGraniteVisionV4._model_repo_revision):
    # "newer" can only come from a newer Docling, and a cleanup must keep exactly this copy.
    ("Chart model", "ibm-granite/granite-vision-4.1-4b", "dd48e97503de471803850df70843cf9eb5da8712", "enrich_chart", 8.0),
]

# How OCR is decided. "auto" is the smart one: the launcher looks at each PDF and turns OCR on
# only where there is no text layer; images always get it; digital documents skip it.
OCR_MODES = [
    ("auto", "Automatic — only scans and images (recommended)"),
    ("always", "Always, whole page — for scans with a wrong text layer"),
    ("off", "Off — fastest; digital documents only"),
]
DEFAULT_OCR_MODE = "auto"

# Which model describes pictures, in the describe pass that runs after Docling (assets/convert_tool.py).
DESCRIBE_MODELS = [
    ("better", "better  —  granite-vision 2B, 6 GB, made for documents"),
    ("small", "small  —  SmolVLM 256M, 0.5 GB, rough"),
]
DEFAULT_DESCRIBE_MODEL = "better"

# Files in a model repo that Docling never loads on this machine (other runtimes' formats).
MODEL_IGNORE_PATTERNS = ["onnx/*", "*.onnx", "*.gguf", "*.bin", "*.h5", "*.msgpack", "*mlx*", "*.tflite", "*.ot"]

# Speech recognition (Whisper) sizes, smallest to best. Docling's own default is tiny.
SPEECH_MODELS = [
    ("tiny", "whisper_tiny", "75 MB, rough"),
    ("base", "whisper_base", "140 MB"),
    ("small", "whisper_small", "460 MB"),
    ("medium", "whisper_medium", "1.5 GB"),
    ("turbo", "whisper_turbo", "1.6 GB, best; needs the GPU to be quick"),
]
DEFAULT_SPEECH_MODEL = "turbo"

# The GPU edition of the AI library lives on the PyTorch index, not the general one. An
# upgrade that touched torch would otherwise quietly reinstall the CPU edition.
TORCH_INDEX_URL = "https://download.pytorch.org/whl/{tag}"

# Versions an Update must not cross, each with the fault it prevents (2026-09-12). When
# pip cannot satisfy a pin together with a newer Docling, the update stops and says so -
# that is the moment to re-test the fault and lift the pin.
UPGRADE_PINS = [
    # Docling 2.126 loads the chart model through its bundled legacy code, which calls the
    # AI library in a way transformers 5.8+ rejects (create_causal_mask(cache_position=)).
    "transformers<5.8",
    # resemblyzer (speaker separation) imports pkg_resources, dropped by setuptools 80.
    "setuptools<80",
]

TOOLTIP_TEXT.update({
    "keep_pictures": "Figures and pictures are saved as PNG files in a folder beside the output and linked from the Markdown/HTML. Off: a placeholder comment is left where each picture was.",
    "enrich_formula": "Formulas are written as LaTeX and code blocks kept as code, using the formula model (0.6 GB, downloaded once). Slower per page; quick with the GPU.",
    "enrich_chart": "Bar, pie and line charts become tables of their values, using the chart model (8 GB, downloaded once). Heavy: sensible only with the GPU.",
    "describe_pictures": "A few AI-written sentences describing each picture. With the better model (2 billion parameters, 6 GB, made for documents) and a technical instruction; the small model (0.5 GB) is rough.",
    "describe_model": "Which model describes pictures. Better = granite-vision 2B (6 GB) with a technical instruction; small = SmolVLM 256M (0.5 GB), rough. Descriptions are written in a pass of their own after Docling, so they never compete with the chart model for the graphics card.",
    "video_speakers": "Recordings and videos come out as a transcript split by speaker (Speaker 1, Speaker 2, ...). Sound files travel through Docling's video road for this; nothing is re-encoded.",
    "speech_model": "Which Whisper model transcribes sound and video. Bigger is more accurate and slower; turbo is the best and is quick on the GPU.",
    "update_models": "When Update runs, AI models with a newer version on the model hub are replaced, and models needed by ticked abilities are downloaded. The old copy of a replaced model is deleted to free the disk.",
    "input_formats": "Every file type Docling can read, with notes on what each needs.",
})

# Where the launcher's own releases live (private; the launcher needs an update key to read it).
LAUNCHER_REPO = "LITRAP/docling-launcher"

# What a preset carries: how to convert, never where from or where to.
PRESET_FIELDS = (
    "conversion_mode", "output_formats", "ocr_mode", "ocr_engine", "allow_external_plugins",
    "portable_tesseract_enabled", "portable_tesseract_path", "keep_pictures", "enrich_formula",
    "enrich_chart", "describe_pictures", "describe_model", "speech_model", "video_speakers",
    "skip_converted", "retry_failed",
)

TOOLTIP_TEXT.update({
    "preset": "A saved way of converting: mode, formats, OCR, technical abilities. Folders are not part of it.",
    "drop": "Drop a folder or files here from Explorer.",
    "launcher_key": "A GitHub key with read access to the launcher's private repository, so the launcher can fetch its own updates. Paste it once.",
    "open_output": "Opens the output folder in Explorer.",
    "theme": "Light or dark window.",
})
