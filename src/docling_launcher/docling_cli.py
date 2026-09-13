from __future__ import annotations

import ctypes
from dataclasses import dataclass
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Callable, Iterable

from .constants import FORMAT_OUTPUT_SUFFIXES, MEDIA_INPUT_EXTENSIONS, SUPPORTED_INPUT_EXTENSIONS


# Windows refuses a command line longer than 32 767 characters; stay well under it so a
# folder of a thousand long UNC paths is split into several Docling runs, not one that fails.
MAX_COMMAND_CHARS = 30000

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class CommandPlan:
    """One Docling process: every source in `sources` lands in `output_dir`."""

    sources: tuple[Path, ...]
    output_dir: Path
    command: list[str]
    preview: str
    env: dict[str, str]


class ProcessJob:
    """A Windows job object: every process placed in it dies when the job is terminated,
    and when the launcher itself exits — even by crash — because the job is created with
    KILL_ON_JOB_CLOSE. This is what makes Stop and Exit reach Docling's real worker process
    behind the docling.exe stub, and any helper processes it spawns, with no polling."""

    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

    def __init__(self) -> None:
        self.handle = None
        if os.name != "nt":
            return
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = kernel32.SetInformationJobObject(
            handle,
            self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            kernel32.CloseHandle(handle)
            return
        self.handle = handle

    def add(self, process: subprocess.Popen) -> None:
        if self.handle is None:
            return
        ctypes.windll.kernel32.AssignProcessToJobObject(self.handle, int(process._handle))

    def terminate(self) -> None:
        """Kill everything in the job now. The job stays usable for later processes."""
        if self.handle is not None:
            ctypes.windll.kernel32.TerminateJobObject(self.handle, 1)

    def close(self) -> None:
        if self.handle is not None:
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None


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


def expected_outputs(source: Path, output_dir: Path, formats: Iterable[str]) -> list[Path]:
    """The files Docling writes for `source` — its stem plus one suffix per format."""
    return [
        output_dir / f"{source.stem}{FORMAT_OUTPUT_SUFFIXES[fmt]}"
        for fmt in formats
        if fmt in FORMAT_OUTPUT_SUFFIXES
    ]


def converted_ok(source: Path, output_dir: Path, formats: Iterable[str], started_at: float) -> bool:
    """True when every expected output exists and was written during this run.

    This is the truth about a file, independent of Docling's exit code: Docling on Windows
    sometimes reports failure while tidying its temporary folder AFTER writing every output."""
    paths = expected_outputs(source, output_dir, formats)
    if not paths:
        return False
    for path in paths:
        try:
            info = path.stat()
        except OSError:
            return False
        # An empty file is what Docling leaves behind when an export produced nothing
        # (a scan with OCR off, for one); it calls that a failure and so do we.
        if info.st_mtime < started_at - 2 or info.st_size == 0:
            return False
    return True


def environment_for_run(
    portable_tesseract_enabled: bool,
    portable_tesseract_path: str,
    use_launcher_temp: bool = True,
) -> dict[str, str]:
    env = os.environ.copy()
    # The model library tries a symbolic link per downloaded file; Windows refuses that
    # without Developer Mode, and its once-per-folder guess got it wrong mid-download
    # (WinError 1314, 2026-09-12). Without links it moves each file into place instead -
    # no crash, and no second copy of every model on the disk.
    env["HF_HUB_DISABLE_SYMLINKS"] = "1"
    env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
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


@dataclass(frozen=True)
class ConversionOptions:
    """Everything a run passes to Docling besides the files themselves — one object, so a
    new ability is one field here, one flag below, and one tick box in the window."""

    formats: tuple[str, ...] = ("md",)
    ocr_mode: str = "auto"           # auto (decided per file) | always (whole page) | off
    ocr_engine: str = "auto"
    ocr_lang: str = ""               # "fr,en" - a hint for EasyOCR / Tesseract
    allow_external_plugins: bool = False
    portable_tesseract_enabled: bool = False
    portable_tesseract_path: str = ""
    keep_pictures: bool = True       # figures saved as PNG beside the output and linked
    enrich_formula: bool = False     # formulas as LaTeX, code blocks as code (CodeFormula model)
    enrich_chart: bool = False       # bar / pie / line charts as tables of values
    describe_pictures: bool = False  # a few AI-written sentences per figure
    describe_model: str = "better"   # "better" = granite-vision 2B, "small" = SmolVLM 256M
    describe_prompt: str = ""        # "" = the describe pass's own default instruction
    speech_model: str = "turbo"      # Whisper size for sound and video
    video_speakers: bool = True      # "who said what" on video sound tracks
    threads: int = 0                 # 0 = Docling's own default


def convert_tool_command() -> list[str] | None:
    """The direct-Docling driver: Docling's own python running assets/convert_tool.py.
    DOCLING_CONVERT_TOOL overrides the script (the tests point it at a stand-in)."""
    from .assets import asset_path
    python = resolve_python()
    override = os.environ.get("DOCLING_CONVERT_TOOL")
    tool = Path(override) if override else asset_path("convert_tool.py")
    if not python or not tool.exists():
        return None
    return [str(python), str(tool)]


def default_threads() -> int:
    """Docling's default is 4 threads; this i9 has 16 cores. Measured 2026-09-12 on a
    five-page PDF, CPU only: 4 threads 10.3 s, 8 threads 8.1 s, 16 threads 8.2 s. Eight is
    the knee, and it leaves the machine usable while a batch runs."""
    return max(4, min(8, (os.cpu_count() or 4) // 2))


def ocr_wanted(source: Path, options: ConversionOptions, text_chars: dict[Path, int | None]) -> bool:
    """The one rule for OCR per file. "auto": images yes; a PDF only when its first pages
    carry no text layer (probed); everything else no. "always"/"off" say it themselves."""
    if options.ocr_mode == "always":
        return True
    if options.ocr_mode == "off":
        return False
    suffix = source.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return True
    if suffix == ".pdf":
        chars = text_chars.get(source)
        return chars is None or chars < 50   # unknown -> be safe and read it
    return False


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def build_command_plan(
    sources: Iterable[Path],
    output_dir: Path,
    options: ConversionOptions,
    use_launcher_temp: bool = True,
    verbose: bool = True,
    ocr: bool | None = None,
) -> CommandPlan:
    """`ocr` is the decision for this group when the mode is "auto" (None = apply the mode
    literally: "always" reads, "off" does not, "auto" alone counts as reading)."""
    # One road: Docling's command line, entered through the driver (assets/convert_tool.py).
    # Without the driver (no python beside docling.exe) the plain command line runs.
    driver = convert_tool_command()
    if driver:
        command = [*driver, "convert"]
    else:
        docling = resolve_docling()
        command = [str(docling) if docling else "docling", "convert"]

    sources = tuple(sources)
    # A web address is a source too (Docling reads pages by URL); it has no Path behaviour.
    media = [s for s in sources if isinstance(s, Path) and s.suffix.lower() in MEDIA_INPUT_EXTENSIONS]
    formats = list(options.formats)
    if media and options.video_speakers and "vtt" not in formats:
        # Docling writes the speaker of each line only into WebVTT; media.py turns that
        # into the Markdown transcript by speaker afterwards.
        formats.append("vtt")

    if options.allow_external_plugins:
        command.append("--allow-external-plugins")
    read = ocr if ocr is not None else options.ocr_mode != "off"
    if not read:
        # Docling 2.126 OCRs every picture region of a text PDF by default (measured:
        # 10.7 s -> 34 s on a five-page guide, same words). Off is the fast road for
        # digital documents; an engine choice means nothing then, so none is passed.
        command.append("--no-ocr")
    else:
        if options.ocr_engine:
            command.extend(["--ocr-engine", options.ocr_engine])
        if options.ocr_mode == "always":
            command.extend(["--ocr-mode", "full_page"])
        if options.ocr_lang.strip():
            command.extend(["--ocr-lang", ",".join(part.strip() for part in options.ocr_lang.split(",") if part.strip())])
    for fmt in formats:
        command.extend(["--to", fmt])
    if options.keep_pictures:
        # Docling's default is a placeholder comment where each figure was. "referenced"
        # writes the figures as PNG files into <stem>_artifacts beside the output and links
        # them from Markdown and HTML.
        command.extend(["--image-export-mode", "referenced"])
    if options.enrich_formula:
        command.extend(["--enrich-formula", "--enrich-code"])
    if options.enrich_chart:
        command.append("--enrich-chart-extraction")
    # Picture descriptions are NOT asked of Docling: they are a pass of their own afterwards
    # (describe_pictures_in below), so the describing and chart models never share the card.
    if media:
        if options.speech_model:
            command.extend(["--asr-model", f"whisper_{options.speech_model}"])
        if options.video_speakers:
            command.append("--video-diarization")
        # Frames at scene changes rather than every ten seconds: what changed on screen,
        # and none at all from the black track of a wrapped sound file.
        command.extend(["--video-sampling-mode", "scene"])
    threads = options.threads or default_threads()
    if threads:
        command.extend(["--num-threads", str(threads)])
    if verbose:
        # -v makes Docling announce each document as it starts and finishes, which is the
        # only per-file progress there is once a whole folder runs in one process.
        command.append("-v")

    command.extend(str(source) for source in sources)
    command.extend(["--output", str(output_dir)])

    # The preview reads as the command line it becomes, plus what happens around it.
    start = command.index("convert")
    preview = subprocess.list2cmdline(["docling", *command[start:]])
    notes = []
    if options.ocr_mode == "auto" and ocr is None:
        notes.append("OCR decided per file")
    if options.describe_pictures:
        notes.append(f"then pictures described by the {options.describe_model} model")
    if notes:
        preview += "   [" + "; ".join(notes) + "]"

    return CommandPlan(
        sources=sources,
        output_dir=output_dir,
        command=command,
        preview=preview,
        env=environment_for_run(
            options.portable_tesseract_enabled,
            options.portable_tesseract_path,
            use_launcher_temp=use_launcher_temp,
        ),
    )


def group_sources(
    files: Iterable[Path],
    input_root: Path,
    output_root: Path,
    mode: str,
    stand_ins: dict[Path, Path] | None = None,
    ocr_of: Callable[[Path], bool] | None = None,
) -> list[tuple[Path, bool, list[Path]]]:
    """Files that share an output folder go to Docling together, in one process.

    Measured 2026-09-12: one Docling process costs ~14 s of start-up and model loading
    before the first page, whatever the file. Twenty PDFs one-by-one paid that twenty times.

    Sound and video form their own run beside the documents of the same folder: the speech
    flags and the subtitle output then reach only them.

    `stand_ins` maps a source to the file Docling is actually given in its place (a sound
    file's video-container twin); the output folder is always the SOURCE's."""
    groups: dict[tuple[Path, bool, bool], list[Path]] = {}
    for source in files:
        destination = output_dir_for(source, input_root, output_root, mode)
        media = source.suffix.lower() in MEDIA_INPUT_EXTENSIONS
        read = bool(ocr_of(source)) if ocr_of else True
        groups.setdefault((destination, media, read), []).append((stand_ins or {}).get(source, source))
    return [(destination, read, sources) for (destination, _media, read), sources in groups.items()]


def build_batch_plans(
    files: Iterable[Path],
    input_root: Path,
    output_root: Path,
    mode: str,
    options: ConversionOptions,
    stand_ins: dict[Path, Path] | None = None,
    text_chars: dict[Path, int | None] | None = None,
) -> list[CommandPlan]:
    """Files that share an output folder, a kind (document / media) and an OCR decision go to
    Docling together. `text_chars` is the probe result per PDF for the "auto" OCR mode."""
    chars = text_chars or {}

    def plan_for(sources: list[Path], output_dir: Path, read: bool) -> CommandPlan:
        return build_command_plan(sources, output_dir, options, ocr=read)

    plans: list[CommandPlan] = []
    groups = group_sources(files, input_root, output_root, mode, stand_ins,
                           ocr_of=lambda source: ocr_wanted(source, options, chars))
    for output_dir, read, sources in groups:
        base_length = len(plan_for([], output_dir, read).preview)
        chunk: list[Path] = []
        length = base_length
        for source in sources:
            cost = len(str(source)) + 3  # quotes and a space
            if chunk and length + cost > MAX_COMMAND_CHARS:
                plans.append(plan_for(chunk, output_dir, read))
                chunk, length = [], base_length
            chunk.append(source)
            length += cost
        if chunk:
            plans.append(plan_for(chunk, output_dir, read))
    return plans


def probe_text_layers(files: Iterable[Path]) -> dict[Path, int | None]:
    """How many characters of text the first pages of each PDF carry (None = unknown).
    One short run of the driver's `probe`; ~50 ms per file."""
    pdfs = [path for path in files if path.suffix.lower() == ".pdf"]
    result: dict[Path, int | None] = {path: None for path in pdfs}
    driver = convert_tool_command()
    if not pdfs or not driver:
        return result
    import json
    try:
        run = subprocess.run(
            [*driver, "probe", *map(str, pdfs)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30 + 2 * len(pdfs), creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        return result
    by_name = {str(path): path for path in pdfs}
    for line in run.stdout.splitlines():
        if line.startswith("{"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            path = by_name.get(row.get("file"))
            if path is not None:
                result[path] = row.get("text_chars")
    return result


def describe_pictures_in(
    markdowns: list[Path],
    model: str,
    log: Callable[[str], None],
    job: ProcessJob | None = None,
    env: dict[str, str] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    prompt: str = "",
) -> int:
    """The describe pass: Docling's describing model on the pictures each Markdown links."""
    driver = convert_tool_command()
    if not driver:
        log("The describing pass needs Docling's python beside docling.exe; skipped.")
        return 1
    command = [*driver, "describe", "--model", model, "--threads", str(default_threads())]
    if prompt.strip():
        command.extend(["--prompt", prompt.strip()])
    command.extend(map(str, markdowns))
    return stream_process(command, env, log, job=job, tidy=tidy_docling_line, cancelled=cancelled)


def already_converted(source: Path, output_dir: Path, formats: Iterable[str]) -> bool:
    """Every expected output exists, is not empty and is newer than the source."""
    try:
        source_time = source.stat().st_mtime
    except OSError:
        return False
    paths = expected_outputs(source, output_dir, formats)
    if not paths:
        return False
    for path in paths:
        try:
            info = path.stat()
        except OSError:
            return False
        if info.st_size == 0 or info.st_mtime < source_time:
            return False
    return True


def build_preview(
    input_folder: str,
    output_folder: str,
    mode: str,
    options: ConversionOptions,
    source_path: Path | None = None,
) -> str:
    input_root = Path(input_folder) if input_folder else Path("<input-folder>")
    output_root = Path(output_folder) if output_folder else Path("<output-folder>")
    source = source_path or input_root / "<input-file>"
    output_dir = output_dir_for(source, input_root, output_root, mode)
    plan = build_command_plan(
        sources=[source],
        output_dir=output_dir,
        options=options,
        use_launcher_temp=False,
        verbose=False,
    )
    return plan.preview


# "2026-09-12 10:10:49,109<TAB>INFO<TAB>docling.document_converter: Finished converting ..."
_DOCLING_LOG_LINE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}\t(?P<level>[A-Z]+)\t(?P<module>[\w.]+): (?P<message>.*)$"
)

# The INFO lines worth a person's eye: the ones about THEIR documents. Everything else that
# -v produces (plugin registration, model fetching, HTTP requests, temp paths) is dropped.
_INFO_MODULES = ("docling.document_converter", "docling.pipeline.", "docling.cli.main")
# Plain (non-logger) lines nobody needs to read.
_PLAIN_NOISE = (
    "cache-system uses symlinks", "To support symlinks on Windows", "warnings.warn(",
    "unauthenticated requests to the HF Hub", "[transformers]",
    "The plugin docling_ocr_onnxtr will not be loaded", "Failed to launch Triton kernels",
    "Detecting language using up to the first 30 seconds", "[RapidOCR]", "triton not found",
)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")  # terminal colour codes some tools print
_INFO_NOISE = (
    "writing ", "paths:", "detected formats:", "Going to convert", "Initializing pipeline",
    "artifacts-path:", "accelerator_options:", "Available device for", "loading _",
)


def tidy_docling_line(line: str) -> str | None:
    """Docling's own log lines carry a timestamp and a module name; the launcher's log
    already stamps every line, so keep only the message, and the level when it matters.
    Returns None for a line that should not be shown at all."""
    line = _ANSI.sub("", line)
    match = _DOCLING_LOG_LINE.match(line)
    if not match:
        return None if any(noise in line for noise in _PLAIN_NOISE) else line
    level, module, message = match.group("level"), match.group("module"), match.group("message")
    if any(noise in message for noise in _PLAIN_NOISE):
        return None
    if level == "INFO":
        if not module.startswith(_INFO_MODULES) or message.startswith(_INFO_NOISE):
            return None
        return message
    return f"{level}: {message}"


def stream_process(
    command: list[str],
    env: dict[str, str] | None,
    log: Callable[[str], None],
    job: ProcessJob | None = None,
    cwd: Path | None = None,
    tidy: Callable[[str], str | None] = lambda line: line,
    cancelled: Callable[[], bool] = lambda: False,
) -> int:
    """Run one process, feed every complete output line to `log`, return its exit code.

    Shared by the batch runner and the updater so there is exactly one way a child
    process is started, watched and killed."""
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(cwd) if cwd else None,
        env=env,
        creationflags=CREATE_NO_WINDOW,
    )
    if job is not None:
        job.add(process)
    if cancelled():
        # Stop was pressed between the last process ending and this one starting.
        process.kill()
    assert process.stdout is not None
    # newline="\n": a text pipe would otherwise treat every carriage return as a line end,
    # and a progress bar that redraws itself 100 times would become 100 log lines.
    stdout = io.TextIOWrapper(process.stdout, encoding="utf-8", errors="replace", newline="\n")
    for line in stdout:
        # A progress bar redraws itself with carriage returns on one line; only its final
        # state is worth keeping.
        clean = line.rstrip().split("\r")[-1].strip()
        if clean:
            shown = tidy(clean)
            if shown:
                log(shown)
    return process.wait()
