from __future__ import annotations

APP_NAME = "Docling Launcher"
APP_VERSION = "1.5.1"

OUTPUT_FORMATS = [
    ("Markdown", "md"),
    ("JSON", "json"),
    ("HTML", "html"),
    ("Text", "text"),
    ("DocLang XML", "doclang"),
    ("Doctags", "doctags"),
    ("WebVTT", "vtt"),
    ("DCLX", "dclx"),
    ("Chunks for AI", "chunks"),
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
    "chunks": ".chunks.jsonl",
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
    ("Voice features (who said what)", "kaldi-native-fbank"),
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
    # Not on the model hub: two ONNX files from the sherpa-onnx project's GitHub releases
    # (assets/models_tool.py knows the addresses), kept in %LOCALAPPDATA%\DoclingLauncher\models\speakers.
    ("Who-said-what models", "speakers:pyannote3", "release", "video_speakers:best", 0.03),
]

# Which pipeline tells voices apart when "Who said what" is ticked (assets/speakers_tool.py).
SPEAKER_ENGINES = [
    ("best", "best  —  pyannote 3 + WeSpeaker on the GPU, word by word (recommended)"),
    ("docling", "Docling's built-in  —  Resemblyzer, sentence by sentence, rougher"),
]
DEFAULT_SPEAKER_ENGINE = "best"
SPEAKER_COUNTS = [(0, "let it find out")] + [(n, str(n)) for n in range(2, 9)]

# The language Whisper is told. "" = it guesses from the first 30 seconds, which goes wrong
# for a whole file when that opening is silence, music or another language.
SPEECH_LANGUAGES = [
    ("", "guess from the first 30 seconds"), ("fr", "French"), ("en", "English"), ("de", "German"),
    ("it", "Italian"), ("es", "Spanish"), ("pt", "Portuguese"), ("nl", "Dutch"), ("ru", "Russian"),
    ("uk", "Ukrainian"), ("pl", "Polish"), ("cs", "Czech"), ("ro", "Romanian"), ("tr", "Turkish"),
    ("ar", "Arabic"), ("zh", "Chinese"), ("ja", "Japanese"),
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

# The instruction the describing model is given; the owner can word it for their documents.
DEFAULT_DESCRIBE_PROMPT = (
    "Describe this figure for a technical reader in a few precise sentences: what it shows, "
    "the axes or labels, the key values or components, and what it means. If it contains "
    "text, quote the important text. Do not speculate beyond what is visible."
)

# Files in a model repo that Docling never loads on this machine (other runtimes' formats).
MODEL_IGNORE_PATTERNS = ["onnx/*", "*.onnx", "*.gguf", "*.bin", "*.h5", "*.msgpack", "*mlx*", "*.tflite", "*.ot"]

# Speech recognition (Whisper) sizes, smallest to best. Docling's own default is tiny.
SPEECH_MODELS = [
    ("tiny", "whisper_tiny", "75 MB, rough"),
    ("base", "whisper_base", "140 MB"),
    ("small", "whisper_small", "460 MB"),
    ("medium", "whisper_medium", "1.5 GB"),
    ("turbo", "whisper_turbo", "1.6 GB, best in practice; quick on the GPU"),
    ("large", "whisper_large", "3.1 GB, 4-5x slower; not clearly better on a noisy meeting (tested 2026-09-13)"),
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
    "speech_model": "Which Whisper model transcribes sound and video. turbo is the best in practice and quick on the GPU; large is 4-5 times slower and was not better on a noisy meeting recording.",
    "speaker_engine": "How voices are told apart. best: pyannote 3 finds the speech (two people at once included), WeSpeaker fingerprints each voice, and the speaker is decided word by word - on a 54-minute meeting it found the four people Docling's built-in had folded into two. Docling's built-in: 1.5-second windows, one speaker per sentence.",
    "speaker_count": "How many people speak, if you know it. Leave it to find out when you do not; a wrong number is worse than none.",
    "speech_language": "The language spoken. Telling Whisper skips its guess from the first 30 seconds, which goes wrong for the whole file when the recording opens with silence, music or another language.",
    "update_models": "When Update runs, AI models with a newer version on the model hub are replaced, and models needed by ticked abilities are downloaded. The old copy of a replaced model is deleted to free the disk.",
    "input_formats": "Every file type Docling can read, with notes on what each needs.",
})

# Where the launcher's own releases live (private; the launcher needs an update key to read it).
LAUNCHER_REPO = "LITRAP/docling-launcher"

# What a preset carries: how to convert, never where from or where to.
PRESET_FIELDS = (
    "conversion_mode", "output_formats", "ocr_mode", "ocr_engine", "ocr_lang", "allow_external_plugins",
    "portable_tesseract_enabled", "portable_tesseract_path", "keep_pictures", "enrich_formula",
    "enrich_chart", "describe_pictures", "describe_model", "describe_prompt", "speech_model", "video_speakers",
    "speaker_engine", "speaker_count", "speech_language",
    "skip_converted", "retry_failed",
)

TOOLTIP_TEXT.update({
    "ocr_lang": "Languages the scans are in, as short codes separated by commas: fr,en or lt or ru. Helps EasyOCR and Tesseract read accented and Cyrillic text; RapidOCR chooses by itself.",
    "chunks": "Docling cuts the document into pieces sized for AI search and retrieval (RAG), one JSON line per piece.",
    "web_page": "Convert a web page by its address, into the output folder.",
    "describe_prompt": "The instruction given to the describing model for every picture. Word it for your documents: manuals, drawings, papers, photos.",
    "notify_done": "A Windows notification when a batch that took more than half a minute ends.",
    "explorer_menu": "'Convert with Docling' on a folder's right-click menu in Explorer: opens the launcher with that folder as the input.",
    "save_report": "Writes a Markdown report of this batch - every file, its result and time, with links to the outputs - into the output folder.",
    "name_speakers": "Replace 'Speaker 1', 'Speaker 2' with real names in the transcripts of this batch.",
    "watch_folder": "While the launcher is open, files added to the input folder are converted as they arrive (once the folder has been quiet for a few seconds). Windows reports the changes; nothing runs in between.",
    "queue": "Line up several folders, each with its own output folder and preset, and run them one after another.",
    "reference_check": "Converts a built-in reference set (two paper pages and a scan) and compares words, tables and time with the last good run. Runs by itself after every update.",
    "preset": "A saved way of converting: mode, formats, OCR, technical abilities. Folders are not part of it.",
    "drop": "Drop a folder or files here from Explorer.",
    "launcher_key": "A GitHub key with read access to the launcher's private repository, so the launcher can fetch its own updates. Paste it once.",
    "open_output": "Opens the output folder in Explorer.",
    "theme": "Light or dark window.",
})
