"""The window. Four tabs (Convert · Settings · Updates · Log), a Run bar that is always in
view, a results table that fills as Docling works, drag & drop from Explorer, presets, a
light and a dark look. Every conversion, update and check runs on a worker thread and
reports through one queue that a timer drains only while something is running.
"""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import queue
import re
import shutil
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from typing import Callable

from .admin import is_user_admin, run_elevated_batch
from .assets import asset_path
from .constants import (
    SPEAKER_COUNTS, SPEAKER_ENGINES, SPEECH_LANGUAGES,
    APP_NAME,
    APP_VERSION,
    CONVERSION_MODES,
    DEFAULT_DESCRIBE_PROMPT,
    DESCRIBE_MODELS,
    INPUT_FORMAT_GROUPS,
    MEDIA_INPUT_EXTENSIONS,
    OCR_ENGINES,
    OCR_MODES,
    OUTPUT_FORMATS,
    PRESET_FIELDS,
    SPEECH_MODELS,
    SUPPORTED_INPUT_EXTENSIONS,
    TOOLTIP_TEXT,
)
from .docling_cli import (
    ProcessJob,
    already_converted,
    build_batch_plans,
    build_preview,
    converted_ok,
    describe_pictures_in,
    discover_input_files,
    environment_for_run,
    output_dir_for,
    probe_text_layers,
    resolve_docling,
    stream_process,
    tidy_docling_line,
)
from .dragdrop import enable_drop
from .environment import check_all_dependencies, gpu_status, speech_available
from .media import add_scene_times, discard_wrapper, is_audio, is_media, is_video, scene_times, speakers_markdown, wrap_audio_as_video
from .models import ModelStatus, check_models, model_targets, run_model_update
from .settings import LauncherSettings
from . import launcher_update, safety, updates, windows
from .watcher import FolderWatcher


# Jobs that may not overlap: each one owns Docling's environment while it runs.
HEAVY_JOBS = {"batch", "update", "restore"}

# Engines that cannot work on this machine are not offered (a Mac-only one on Windows).
OFFERED_OCR_ENGINES = [engine for engine in OCR_ENGINES if not (os.name == "nt" and engine == "ocrmac")]
TESSERACT_ENGINES = {"tesseract", "tesserocr"}

_PROCESSING = re.compile(r"^Processing (?:video )?document (.+?)\.?$")
_FINISHED = re.compile(r"^Finished converting document (.+?) in ([\d.]+) sec\.$")
_DESCRIBED = re.compile(r"^described (\d+)/(\d+)$")

# ("h1" heading, "h2" sub-heading, "p" paragraph, "li" bullet) — shown by How to use.
HOW_TO_USE = [
    ("h1", "What this program is for"),
    ("p", "Docling Launcher turns documents into clean text files that a person, a search tool or an AI "
          "assistant can read: Markdown, HTML, JSON and more. It reads PDFs (digital or scanned), Word, "
          "PowerPoint, Excel, OpenDocument, EPUB e-books, web pages, e-mails, images, and the sound track of "
          "audio and video files. Tables stay tables, pictures are kept, formulas can be written as LaTeX, "
          "charts can be turned into numbers and every picture can be described in words. Everything runs on "
          "this computer; nothing is sent anywhere."),
    ("p", "Typical uses: a folder of technical manuals into Markdown for an AI assistant; scanned contracts "
          "into searchable text; e-books into plain text; recorded meetings into a transcript with who said what."),

    ("h2", "The five steps (Convert tab)"),
    ("li", "1.  Input folder — choose the folder with the files to convert, or drop a folder or files onto the "
           "window. Every supported file in it and in its subfolders is taken; choose 'Only selected files' to "
           "pick some. 'All input types…' shows exactly what can be read."),
    ("li", "2.  Output folder — where the results go (not needed for 'beside the originals')."),
    ("li", "3.  Where the results go — Mirror repeats the folder structure under the output folder; Beside "
           "writes each result next to its original; Single folder puts everything in one place."),
    ("li", "4.  Output formats — tick one or more. Markdown is the usual choice; JSON keeps the most detail; "
           "HTML looks like the page; Text is plain words."),
    ("li", "5.  Press Run. The results table fills as Docling works: one line per file with its outcome and "
           "time; the bar at the bottom shows how far the batch is. Stop closes Docling at once; finished "
           "files are kept. 'Open output folder' shows the results in Explorer; double-click a result line "
           "to open its folder."),
    ("p", "Presets: save the way you convert (mode, formats, OCR, technical abilities) under a name — "
          "'Technical manuals', 'Scans', 'E-books' — and pick it from the list next time. Folders are not "
          "part of a preset."),

    ("h2", "OCR — reading scans and pictures (Settings tab)"),
    ("p", "OCR is how text inside a scanned page or a picture is read. 'Automatic' looks at every PDF: a scan "
          "(no text layer) is read with OCR, a digital document is not — which is two to three times faster "
          "and gives the same text. Images are always read. 'Always, whole page' is for scans whose text "
          "layer is wrong. 'Off' never reads; a scan then comes out empty and is reported as failed. The OCR "
          "engine can stay on Auto. Portable Tesseract is only for a Tesseract that lives in a USB or "
          "standalone folder, and appears only when that engine is chosen."),

    ("h2", "Technical documents (Settings tab)"),
    ("li", "Keep pictures — figures are saved as PNG files in a folder beside the output and linked from the "
           "Markdown, so nothing is lost. Off leaves a placeholder where each picture was."),
    ("li", "Formulas as LaTeX — mathematical and physical formulas are written in LaTeX, the notation every "
           "technical editor and AI understands, and code blocks are kept as code. Uses the formula model."),
    ("li", "Charts as tables — bar, pie and line charts are turned into tables of their values. Uses the large "
           "chart model; it needs the graphics card to be quick."),
    ("li", "Describe each picture — a few AI-written sentences per figure, written in a pass of its own after "
           "Docling has finished, so it never competes with the chart model for the graphics card. The better "
           "model (2 billion parameters, made for documents) is given a technical instruction: what the "
           "figure shows, its axes and values, what it means. The small model is faster and rough. Video "
           "frames are described too."),
    ("li", "Who said what — in recordings and videos, the transcript is split by speaker. 'best' finds the "
           "speech with pyannote 3 (two people at once included), gives every voice a fingerprint and "
           "groups the fingerprints; the speaker is decided word by word, so a short 'yes, yes' keeps its "
           "owner. It runs beside the transcription and adds no wait. Tell it how many people speak if you "
           "know; leave it to find out if you do not. Docling's built-in separation is rougher (one speaker "
           "per sentence, 1.5-second windows)."),
    ("li", "Language spoken — tell it the language when you know it. Guessing from the first 30 seconds goes "
           "wrong for the whole file when a recording opens with silence, music or another language."),
    ("li", "Speech model — which Whisper model transcribes sound and video. Turbo is the best in practice; it "
           "is quick on the graphics card and slow without it. Large is 4-5 times slower and was not better "
           "on a noisy meeting. Smaller ones are faster and rougher."),
    ("p", "Each of these downloads its model once, on the first use or through Update. Models are only loaded "
          "while a conversion runs and leave memory the moment it ends."),

    ("h2", "Batch behaviour (Settings tab)"),
    ("li", "Skip files already converted — a file whose outputs exist and are newer than it is left alone, so "
           "a huge folder can be converted in several sittings. Untick to redo everything."),
    ("li", "Retry failed files — anything that fails is tried once more at the end, on its own."),
    ("li", "Run as Administrator is only for folders Windows protects; never needed for network shares."),

    ("h2", "Tables"),
    ("p", "Tables in PDFs, Word and Excel files come out as real Markdown tables, including merged headers. "
          "Nothing to switch on."),

    ("h2", "Updates (Updates tab)"),
    ("p", "The header shows the installed Docling. At every start the launcher quietly asks once whether "
          "Docling, an OCR add-in, an AI model or the launcher itself is newer; if so, an Update button "
          "appears. Update saves a restore point of today's versions, installs, and replaces models when "
          "'Also update the AI models' is ticked — the old copy of a replaced model is deleted to free the "
          "disk. Go back reinstalls the saved versions. The table shows, for every part, what is installed, "
          "when it was installed, what is newest and when it was released."),
    ("p", "The launcher updates itself from its own releases on GitHub; nothing to set up. (Should its "
          "repository ever be made private again, an update key would be needed in Settings → Launcher: on "
          "github.com, Settings → Developer settings → Personal access tokens → Fine-grained tokens, read "
          "access to Contents of docling-launcher.)"),

    ("h2", "Extension status (Updates tab)"),
    ("p", "Check extensions shows whether Docling, the graphics card, the speech library and each OCR engine "
          "are visible. GPU 'in use' means the AI models run on the graphics card."),

    ("h2", "Good to know"),
    ("li", "Docling starts once per output folder and converts all of that folder's files in one go; the first "
           "file waits about 15 seconds for the models to load, the rest follow quickly."),
    ("li", "The Log tab shows what Docling is told and everything it says."),
    ("li", "Sound and video need the speech library (installed) and the chosen speech model."),
    ("li", "☀ / ☾ cycles the look: follow Windows, light, dark."),
    ("li", "While a batch runs the PC does not go to sleep; when a batch longer than half a minute ends, "
           "Windows shows a notification (Settings → Batch behaviour)."),
    ("li", "'Web page…' converts a page by its address into the output folder. 'Chunks for AI' is an output "
           "format cut into pieces sized for AI search. OCR languages (fr,en …) help EasyOCR and Tesseract. "
           "'Save report…' writes a table of the batch; 'Name speakers…' puts real names into transcripts."),
    ("li", "Settings → Batch behaviour → 'Convert with Docling' adds the launcher to a folder's right-click "
           "menu in Explorer."),
    ("li", "'Watch this folder' converts files as they arrive while the launcher is open. 'Queue…' lines up "
           "several folders with their own output folder and preset, run one after another."),
    ("li", "Video frames are stamped with their time (At 00:04) and, with descriptions on, described. "
           "Updates → 'Reference check' converts a built-in set and compares it with the last good run; "
           "it also runs by itself after every update and warns if Docling got slower or worse."),
]


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str, enabled_callback):
        self.widget = widget
        self.text = text
        self.enabled_callback = enabled_callback
        self.tip_window: tk.Toplevel | None = None
        self.after_id: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        if self.enabled_callback():
            self.after_id = self.widget.after(550, self._show)

    def _cancel(self) -> None:
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def _show(self) -> None:
        if self.tip_window or not self.enabled_callback():
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.tip_window, text=self.text, padx=10, pady=6, justify="left",
            relief="solid", borderwidth=1, background="#fffbe6", foreground="#222222", wraplength=380,
        )
        label.pack()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class ScrollableFrame(ttk.Frame):
    """A tab that may be taller than the window: scrolls, and only when the wheel is over it."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, padding=(8, 8, 14, 8))
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.content.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window_id, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def match_background(self, colour: str) -> None:
        self.canvas.configure(background=colour)

    def _on_mousewheel(self, event) -> None:
        if not self.winfo_viewable():
            return
        try:
            under = self.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        widget = under
        while widget is not None:
            if widget is self:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                return
            widget = getattr(widget, "master", None)


class DoclingLauncherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1140x880")
        self.root.minsize(960, 720)

        self.settings = LauncherSettings.load()
        self.log_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        # Every Docling and pip process the launcher starts lives in this job, so Stop and
        # Exit end them all, and nothing outlives the window.
        self.job = ProcessJob()
        self.active_jobs: set[str] = set()
        self._pumping = False
        self._stop_requested = False
        self._stand_ins: dict[Path, Path] = {}
        self.update_statuses: list[updates.PackageStatus] = []
        self.model_statuses: list[ModelStatus] = []
        self.launcher_release: launcher_update.LauncherRelease | None = None
        self.launcher_release_note: str = ""
        self.result_rows: dict[str, str] = {}   # file name -> results-table item id
        self.batch_total = 0
        self.batch_done = 0

        s = self.settings
        self.input_folder_var = tk.StringVar(value=s.input_folder)
        self.output_folder_var = tk.StringVar(value=s.output_folder)
        self.convert_all_files_var = tk.BooleanVar(value=s.convert_all_files)
        self.selected_input_files = [Path(path) for path in s.selected_input_files]
        self.selected_files_summary_var = tk.StringVar()
        self.mode_var = tk.StringVar(value=s.conversion_mode)
        self.ocr_mode_var = tk.StringVar(value=s.ocr_mode)
        self.ocr_engine_var = tk.StringVar(value=s.ocr_engine if s.ocr_engine in OFFERED_OCR_ENGINES else "auto")
        self.allow_plugins_var = tk.BooleanVar(value=s.allow_external_plugins)
        self.portable_tesseract_var = tk.BooleanVar(value=s.portable_tesseract_enabled)
        self.portable_tesseract_path_var = tk.StringVar(value=s.portable_tesseract_path)
        self.run_as_admin_var = tk.BooleanVar(value=s.run_as_admin)
        self.show_tooltips_var = tk.BooleanVar(value=s.show_tooltips)
        self.keep_pictures_var = tk.BooleanVar(value=s.keep_pictures)
        self.enrich_formula_var = tk.BooleanVar(value=s.enrich_formula)
        self.enrich_chart_var = tk.BooleanVar(value=s.enrich_chart)
        self.describe_pictures_var = tk.BooleanVar(value=s.describe_pictures)
        self.describe_model_var = tk.StringVar(value=s.describe_model)
        self.speech_model_var = tk.StringVar(value=s.speech_model)
        self.speech_language_var = tk.StringVar(value=s.speech_language)
        self.video_speakers_var = tk.BooleanVar(value=s.video_speakers)
        self.speaker_engine_var = tk.StringVar(value=s.speaker_engine)
        self.speaker_count_var = tk.IntVar(value=s.speaker_count)
        self.skip_converted_var = tk.BooleanVar(value=s.skip_converted)
        self.retry_failed_var = tk.BooleanVar(value=s.retry_failed)
        self.notify_done_var = tk.BooleanVar(value=s.notify_done)
        self.explorer_menu_var = tk.BooleanVar(value=windows.explorer_menu_installed())
        self.ocr_lang_var = tk.StringVar(value=s.ocr_lang)
        self.describe_prompt = s.describe_prompt
        self._transcripts: list[Path] = []
        self.batch_started = 0.0
        self.watch_folder_var = tk.BooleanVar(value=s.watch_folder)
        self._watcher: FolderWatcher | None = None
        self._watch_pending = False
        self.queue_entries: list[dict] = list(s.queue)
        self._queue_running = False
        self._batch_override: LauncherSettings | None = None
        self.update_models_var = tk.BooleanVar(value=s.update_models)
        self.launcher_key_var = tk.StringVar(value=s.launcher_update_key)
        self.theme_var = tk.StringVar(value=s.theme)
        self.preset_var = tk.StringVar(value="")
        self.command_preview_var = tk.StringVar()
        self.docling_version_var = tk.StringVar(value="Docling")
        self.update_status_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.status_var = tk.StringVar(value="Ready.")
        self.format_vars = {value: tk.BooleanVar(value=value in s.output_formats) for _, value in OUTPUT_FORMATS}

        self.status_tree: ttk.Treeview | None = None
        self.updates_tree: ttk.Treeview | None = None
        self.results_tree: ttk.Treeview | None = None
        self.run_button: ttk.Button | None = None
        self.stop_button: ttk.Button | None = None
        self.update_button: ttk.Button | None = None
        self.check_updates_button: ttk.Button | None = None
        self.go_back_button: ttk.Button | None = None
        self.select_files_button: ttk.Button | None = None
        self.tesseract_widgets: list[tk.Widget] = []
        self.ocr_dependent_widgets: list[tk.Widget] = []
        self.tesseract_section: ttk.Widget | None = None
        self.output_widgets: list[tk.Widget] = []

        self._configure_style()
        self._build_ui()
        self._bind_var_changes()
        self._update_preview()
        self._sync_input_scope_state()
        self._sync_ocr_state()
        self._sync_describe_state()
        self._sync_speakers_state()
        self._refresh_presets()
        self._show_installed_versions()
        self._append_log("Ready.")
        self.input_folder_var.trace_add("write", lambda *_: self._sync_watcher() if self.watch_folder_var.get() else None)
        if self.watch_folder_var.get():
            self._sync_watcher()
        note = launcher_update.cleanup_after_update()
        if note:
            self._append_log(note)
        # One quiet look for a newer Docling, after the first frame is on screen.
        self.root.after(400, lambda: self._check_updates(quiet=True))

    # ------------------------------------------------------------------ look

    def _configure_style(self) -> None:
        self.themed = False
        try:
            import sv_ttk
            sv_ttk.set_theme(self._effective_theme())
            self.themed = True
        except Exception:
            try:
                ttk.Style().theme_use("vista")
            except tk.TclError:
                pass
        self._configure_fonts()

    def _configure_fonts(self) -> None:
        """Our named styles; a theme switch resets them, so this runs after every switch."""
        style = ttk.Style()
        style.configure("Header.TLabel", font=("Segoe UI Semibold", 17))
        style.configure("Version.TLabel", font=("Segoe UI", 10))
        style.configure("Available.TLabel", font=("Segoe UI Semibold", 10), foreground="#1a7f37")
        style.configure("Section.TLabelframe.Label", font=("Segoe UI Semibold", 10))
        style.configure("Hint.TLabel", font=("Segoe UI", 9), foreground="#8a8a8a" if self._effective_theme() == "dark" else "#6b6b6b")
        style.configure("Status.TLabel", font=("Segoe UI", 10))
        style.configure("Treeview", rowheight=24)

    def _effective_theme(self) -> str:
        """'light' or 'dark' to draw with: the chosen one, or Windows' own when 'system'."""
        chosen = self.theme_var.get()
        return windows.system_theme() if chosen == "system" else chosen

    def _palette(self) -> tuple[str, str]:
        """(background, foreground) of the current look, for the plain Tk widgets."""
        if self._effective_theme() == "dark":
            return "#1c1c1c", "#e6e6e6"
        return "#fbfbfb", "#1b1b1b"

    def _apply_theme(self) -> None:
        if self.themed:
            import sv_ttk
            sv_ttk.set_theme(self._effective_theme())
        self._configure_fonts()
        bg, fg = self._palette()
        self.log_text.configure(background=bg, foreground=fg, insertbackground=fg)
        frame_bg = ttk.Style().lookup("TFrame", "background") or bg
        for scroller in (self.settings_scroller, self.updates_scroller):
            scroller.match_background(frame_bg)

    def _toggle_theme(self) -> None:
        """Follow Windows -> light -> dark -> follow Windows."""
        order = ["system", "light", "dark"]
        current = self.theme_var.get() if self.theme_var.get() in order else "system"
        self.theme_var.set(order[(order.index(current) + 1) % len(order)])
        self._apply_theme()
        self._save_settings()
        self._set_status({"system": "Look: follows Windows", "light": "Look: light", "dark": "Look: dark"}[self.theme_var.get()])

    # ------------------------------------------------------------------ structure

    def _build_ui(self) -> None:
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self._build_header()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=14, pady=(4, 0))
        self.convert_tab = ttk.Frame(self.notebook, padding=12)
        self.settings_scroller = ScrollableFrame(self.notebook)
        self.updates_scroller = ScrollableFrame(self.notebook)
        self.log_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.convert_tab, text="  Convert  ")
        self.notebook.add(self.settings_scroller, text="  Settings  ")
        self.notebook.add(self.updates_scroller, text="  Updates  ")
        self.notebook.add(self.log_tab, text="  Log  ")

        self._build_convert_tab(self.convert_tab)
        self._build_settings_tab(self.settings_scroller.content)
        self._build_updates_tab(self.updates_scroller.content)
        self._build_log_tab(self.log_tab)
        self._build_run_bar()
        self._apply_theme()
        enable_drop(self.root, self._on_drop)

    def _section(self, parent, title: str, row: int, column: int = 0) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title, padding=(12, 8, 12, 12), style="Section.TLabelframe")
        frame.grid(row=row, column=column, sticky="nsew", pady=(0, 10), padx=(0, 10))
        return frame

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, padding=(16, 12, 16, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(2, weight=1)

        icon_file = asset_path("docling_launcher_40.png")
        if icon_file.exists():
            try:
                self.header_icon = tk.PhotoImage(file=str(icon_file))
                ttk.Label(header, image=self.header_icon).grid(row=0, column=0, rowspan=2, padx=(0, 12))
            except tk.TclError:
                pass
        ttk.Label(header, text=APP_NAME, style="Header.TLabel").grid(row=0, column=1, sticky="w")
        version_row = ttk.Frame(header)
        version_row.grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Label(version_row, textvariable=self.docling_version_var, style="Version.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(version_row, textvariable=self.update_status_var, style="Available.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.update_button = ttk.Button(version_row, text="Update", command=self._on_update_clicked, style="Accent.TButton")
        self.update_button.grid(row=0, column=2, padx=(12, 0))
        self.update_button.grid_remove()
        self._tooltip(self.update_button, TOOLTIP_TEXT["update"])

        tools = ttk.Frame(header)
        tools.grid(row=0, column=3, rowspan=2, sticky="e")
        ttk.Button(tools, text="How to use", command=self._show_how_to_use).grid(row=0, column=0, padx=(0, 8))
        theme_button = ttk.Button(tools, text="☀ / ☾", width=7, command=self._toggle_theme)
        theme_button.grid(row=0, column=1, padx=(0, 8))
        self._tooltip(theme_button, TOOLTIP_TEXT["theme"])
        tips = ttk.Checkbutton(tools, text="Tips", variable=self.show_tooltips_var, command=self._save_settings)
        tips.grid(row=0, column=2)
        preset_row = ttk.Frame(tools)
        preset_row.grid(row=1, column=0, columnspan=3, sticky="e", pady=(6, 0))
        ttk.Label(preset_row, text="Preset").grid(row=0, column=0, padx=(0, 8))
        self.preset_box = ttk.Combobox(preset_row, textvariable=self.preset_var, state="readonly", width=26)
        self.preset_box.grid(row=0, column=1)
        self.preset_box.bind("<<ComboboxSelected>>", lambda _e: self._apply_preset(self.preset_var.get()))
        ttk.Button(preset_row, text="Save as…", command=self._save_preset).grid(row=0, column=2, padx=(8, 0))
        self.delete_preset_button = ttk.Button(preset_row, text="Delete", command=self._delete_preset)
        self.delete_preset_button.grid(row=0, column=3, padx=(8, 0))
        self._tooltip(self.preset_box, TOOLTIP_TEXT["preset"])

    # ------------------------------------------------------------------ Convert tab

    def _build_convert_tab(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(3, weight=1)

        io = self._section(tab, "Files", 1)
        io.grid_columnconfigure(1, weight=1)
        ttk.Label(io, text="Input folder").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        input_entry = ttk.Entry(io, textvariable=self.input_folder_var)
        input_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=3)
        input_button = ttk.Button(io, text="Browse…", command=lambda: self._browse_folder(self.input_folder_var))
        input_button.grid(row=0, column=2, pady=3)

        scope = ttk.Frame(io)
        scope.grid(row=1, column=1, columnspan=2, sticky="w", pady=(2, 2))
        ttk.Radiobutton(scope, text="Every supported file in the folder and its subfolders", value=True,
                        variable=self.convert_all_files_var, command=self._sync_input_scope_state).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(scope, text="Only selected files", value=False,
                        variable=self.convert_all_files_var, command=self._sync_input_scope_state).grid(row=0, column=1, sticky="w", padx=(16, 0))
        self.select_files_button = ttk.Button(scope, text="Select files…", command=self._select_input_files)
        self.select_files_button.grid(row=0, column=2, padx=(10, 0))
        ttk.Label(scope, textvariable=self.selected_files_summary_var, style="Hint.TLabel").grid(row=0, column=3, sticky="w", padx=(10, 0))

        reads = ttk.Frame(io)
        reads.grid(row=2, column=1, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(reads, style="Hint.TLabel", wraplength=560, justify="left",
                  text="Reads PDF, Word, PowerPoint, Excel, EPUB, web pages, e-mail, images, sound and video — "
                       "or drop files or a folder anywhere on this window.").grid(row=0, column=0, sticky="w")
        formats_button = ttk.Button(reads, text="All input types…", command=self._show_input_formats)
        formats_button.grid(row=0, column=1, padx=(10, 0))
        self._tooltip(formats_button, TOOLTIP_TEXT["input_formats"])
        web_button = ttk.Button(reads, text="Web page…", command=self._convert_web_page)
        web_button.grid(row=0, column=2, padx=(8, 0))
        self._tooltip(web_button, TOOLTIP_TEXT["web_page"])

        watch = ttk.Checkbutton(io, text="Watch this folder — convert new files as they arrive",
                                variable=self.watch_folder_var, command=self._sync_watcher)
        watch.grid(row=4, column=1, columnspan=2, sticky="w", pady=(4, 0))
        self._tooltip(watch, TOOLTIP_TEXT["watch_folder"])
        ttk.Label(io, text="Output folder").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=3)
        output_entry = ttk.Entry(io, textvariable=self.output_folder_var)
        output_entry.grid(row=3, column=1, sticky="ew", padx=(0, 8), pady=3)
        output_button = ttk.Button(io, text="Browse…", command=lambda: self._browse_folder(self.output_folder_var))
        output_button.grid(row=3, column=2, pady=3)
        self.output_widgets = [output_entry, output_button]
        for widget in (input_entry, input_button):
            self._tooltip(widget, TOOLTIP_TEXT["input_folder"])
        for widget in (output_entry, output_button):
            self._tooltip(widget, TOOLTIP_TEXT["output_folder"])

        two = ttk.Frame(tab)
        two.grid(row=2, column=0, sticky="ew")
        two.grid_columnconfigure(0, weight=1)
        two.grid_columnconfigure(1, weight=1)
        mode = self._section(two, "Where the results go", 0, column=0)
        for index, (value, label) in enumerate(CONVERSION_MODES.items()):
            button = ttk.Radiobutton(mode, text=label, value=value, variable=self.mode_var, command=self._sync_input_scope_state)
            button.grid(row=index, column=0, sticky="w", pady=2)
            self._tooltip(button, TOOLTIP_TEXT[f"mode_{value}"])
        formats = self._section(two, "Output formats", 0, column=1)
        for index, (label, value) in enumerate(OUTPUT_FORMATS):
            button = ttk.Checkbutton(formats, text=label, variable=self.format_vars[value])
            button.grid(row=index // 4, column=index % 4, sticky="w", padx=(0, 18), pady=2)
            self._tooltip(button, TOOLTIP_TEXT["formats"])

        results = self._section(tab, "Results", 3)
        results.grid_rowconfigure(0, weight=1)
        results.grid_columnconfigure(0, weight=1)
        self.results_tree = ttk.Treeview(results, columns=("file", "where", "result", "time"), show="headings", height=5)
        for column, title, width, stretch in (
            ("file", "File", 320, True), ("where", "Folder", 300, True), ("result", "Result", 180, False), ("time", "Time", 80, False),
        ):
            self.results_tree.heading(column, text=title, anchor="w")
            self.results_tree.column(column, width=width, anchor="w", stretch=stretch)
        scrollbar = ttk.Scrollbar(results, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results_tree.tag_configure("ok", foreground="#1a7f37")
        self.results_tree.tag_configure("bad", foreground="#c62828")
        self.results_tree.tag_configure("dim", foreground="#8a8a8a")
        self.results_tree.bind("<Double-1>", lambda _e: self._open_result_folder())
        result_buttons = ttk.Frame(results)
        result_buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.report_button = ttk.Button(result_buttons, text="Save report…", command=self._save_report, state="disabled")
        self.report_button.grid(row=0, column=0, padx=(0, 8))
        self._tooltip(self.report_button, TOOLTIP_TEXT["save_report"])
        self.speakers_button = ttk.Button(result_buttons, text="Name speakers…", command=self._name_speakers)
        self.speakers_button.grid(row=0, column=1)
        self.speakers_button.grid_remove()
        self._tooltip(self.speakers_button, TOOLTIP_TEXT["name_speakers"])

    # ------------------------------------------------------------------ Settings tab

    def _build_settings_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)

        ocr = self._section(parent, "OCR — reading scans and pictures", 0)
        ocr.grid_columnconfigure(1, weight=1)
        ttk.Label(ocr, text="OCR").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        ocr_labels = dict(OCR_MODES)
        self.ocr_display_var = tk.StringVar(value=ocr_labels.get(self.ocr_mode_var.get(), ""))
        ocr_box = ttk.Combobox(ocr, textvariable=self.ocr_display_var, values=list(ocr_labels.values()), state="readonly", width=52)
        ocr_box.grid(row=0, column=1, sticky="w", pady=3)
        ocr_box.bind("<<ComboboxSelected>>", lambda _e: (self.ocr_mode_var.set(self._key_of(ocr_labels, self.ocr_display_var.get())), self._sync_ocr_state()))
        self._tooltip(ocr_box, TOOLTIP_TEXT["ocr_mode"])
        engine_label = ttk.Label(ocr, text="OCR engine")
        engine_label.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=3)
        engine_box = ttk.Combobox(ocr, textvariable=self.ocr_engine_var, values=OFFERED_OCR_ENGINES, state="readonly", width=24)
        engine_box.grid(row=1, column=1, sticky="w", pady=3)
        engine_box.bind("<<ComboboxSelected>>", lambda _e: self._sync_tesseract_state())
        self._tooltip(engine_box, TOOLTIP_TEXT["ocr_engine"])
        lang_row = ttk.Frame(ocr)
        lang_row.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 3))
        lang_label = ttk.Label(lang_row, text="Languages")
        lang_label.grid(row=0, column=0, sticky="w", padx=(0, 10))
        lang_entry = ttk.Entry(lang_row, textvariable=self.ocr_lang_var, width=16)
        lang_entry.grid(row=0, column=1, sticky="w")
        ttk.Label(lang_row, text="e.g. fr,en  —  for EasyOCR and Tesseract", style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=(10, 0))
        lang_entry.bind("<FocusOut>", lambda _e: self._save_settings())
        self._tooltip(lang_entry, TOOLTIP_TEXT["ocr_lang"])
        self.ocr_dependent_widgets = [engine_label, engine_box, lang_label, lang_entry]

        self.tesseract_section = ttk.Frame(ocr)
        self.tesseract_section.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.tesseract_section.grid_columnconfigure(1, weight=1)
        enabled = ttk.Checkbutton(self.tesseract_section, text="Use a portable Tesseract folder", variable=self.portable_tesseract_var, command=self._sync_tesseract_state)
        enabled.grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(self.tesseract_section, text="Tesseract folder").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=3)
        path_entry = ttk.Entry(self.tesseract_section, textvariable=self.portable_tesseract_path_var)
        path_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=3)
        browse = ttk.Button(self.tesseract_section, text="Browse…", command=lambda: self._browse_folder(self.portable_tesseract_path_var))
        browse.grid(row=1, column=2, pady=3)
        self.tesseract_widgets = [path_entry, browse]
        self._tooltip(enabled, TOOLTIP_TEXT["portable_tesseract"])
        self._tooltip(path_entry, TOOLTIP_TEXT["portable_tesseract_path"])

        tech = self._section(parent, "Technical documents", 1)
        tech.grid_columnconfigure(1, weight=1)
        rows = (
            ("Keep pictures (saved as PNG files beside the output, linked from it)", self.keep_pictures_var, "keep_pictures"),
            ("Formulas as LaTeX and code blocks as code", self.enrich_formula_var, "enrich_formula"),
            ("Charts as tables of their values (bar, pie, line)", self.enrich_chart_var, "enrich_chart"),
            ("Describe each picture in words (AI)", self.describe_pictures_var, "describe_pictures"),
            ("Who said what in recordings and videos (speaker separation)", self.video_speakers_var, "video_speakers"),
        )
        for index, (text, variable, key) in enumerate(rows):
            box = ttk.Checkbutton(tech, text=text, variable=variable)
            box.grid(row=index, column=0, columnspan=2, sticky="w", pady=2)
            self._tooltip(box, TOOLTIP_TEXT[key])
            if key == "describe_pictures":
                box.configure(command=self._sync_describe_state)
            elif key == "video_speakers":
                box.configure(command=self._sync_speakers_state)
        describe_labels = dict(DESCRIBE_MODELS)
        self.describe_display_var = tk.StringVar(value=describe_labels.get(self.describe_model_var.get(), ""))
        self.describe_model_label = ttk.Label(tech, text="Describing model")
        self.describe_model_label.grid(row=len(rows), column=0, sticky="w", padx=(0, 10), pady=(4, 0))
        self.describe_model_box = ttk.Combobox(tech, textvariable=self.describe_display_var, values=list(describe_labels.values()), state="readonly", width=48)
        self.describe_model_box.grid(row=len(rows), column=1, sticky="w", pady=(4, 0))
        self.describe_model_box.bind("<<ComboboxSelected>>", lambda _e: self.describe_model_var.set(self._key_of(describe_labels, self.describe_display_var.get())))
        self._tooltip(self.describe_model_box, TOOLTIP_TEXT["describe_model"])
        self.describe_prompt_label = ttk.Label(tech, text="Instruction")
        self.describe_prompt_label.grid(row=len(rows) + 1, column=0, sticky="nw", padx=(0, 10), pady=(6, 0))
        prompt_frame = ttk.Frame(tech)
        prompt_frame.grid(row=len(rows) + 1, column=1, sticky="ew", pady=(6, 0))
        prompt_frame.grid_columnconfigure(0, weight=1)
        self.describe_prompt_text = tk.Text(prompt_frame, height=3, wrap="word", font=("Segoe UI", 9), relief="flat", borderwidth=1)
        self.describe_prompt_text.grid(row=0, column=0, sticky="ew")
        self.describe_prompt_text.insert("1.0", self.describe_prompt)
        self.describe_prompt_text.bind("<FocusOut>", lambda _e: self._take_prompt())
        reset = ttk.Button(prompt_frame, text="Reset", width=7, command=self._reset_prompt)
        reset.grid(row=0, column=1, sticky="n", padx=(8, 0))
        self._tooltip(self.describe_prompt_text, TOOLTIP_TEXT["describe_prompt"])
        self.describe_prompt_frame = prompt_frame
        speech_labels = {name: f"{name}  —  {note}" for name, _, note in SPEECH_MODELS}
        ttk.Label(tech, text="Speech model").grid(row=len(rows) + 2, column=0, sticky="w", padx=(0, 10), pady=(8, 0))
        self.speech_display_var = tk.StringVar(value=speech_labels.get(self.speech_model_var.get(), ""))
        speech = ttk.Combobox(tech, textvariable=self.speech_display_var, values=list(speech_labels.values()), state="readonly", width=48)
        speech.grid(row=len(rows) + 2, column=1, sticky="w", pady=(8, 0))
        speech.bind("<<ComboboxSelected>>", lambda _e: self.speech_model_var.set(self.speech_display_var.get().split("  —  ")[0]))
        self._tooltip(speech, TOOLTIP_TEXT["speech_model"])
        language_labels = {code: (f"{name}" if not code else f"{name}  ({code})") for code, name in SPEECH_LANGUAGES}
        ttk.Label(tech, text="Language spoken").grid(row=len(rows) + 3, column=0, sticky="w", padx=(0, 10), pady=(4, 0))
        self.speech_language_display_var = tk.StringVar(value=language_labels.get(self.speech_language_var.get(), language_labels[""]))
        language_box = ttk.Combobox(tech, textvariable=self.speech_language_display_var, values=list(language_labels.values()), state="readonly", width=48)
        language_box.grid(row=len(rows) + 3, column=1, sticky="w", pady=(4, 0))
        language_box.bind("<<ComboboxSelected>>", lambda _e: self.speech_language_var.set(self._key_of(language_labels, self.speech_language_display_var.get())))
        self._tooltip(language_box, TOOLTIP_TEXT["speech_language"])
        # Only while "Who said what" is ticked: how voices are told apart, and how many.
        engine_labels = dict(SPEAKER_ENGINES)
        self.speaker_engine_label = ttk.Label(tech, text="Voices told apart by")
        self.speaker_engine_label.grid(row=len(rows) + 4, column=0, sticky="w", padx=(0, 10), pady=(4, 0))
        self.speaker_engine_display_var = tk.StringVar(value=engine_labels.get(self.speaker_engine_var.get(), ""))
        self.speaker_engine_box = ttk.Combobox(tech, textvariable=self.speaker_engine_display_var, values=list(engine_labels.values()), state="readonly", width=48)
        self.speaker_engine_box.grid(row=len(rows) + 4, column=1, sticky="w", pady=(4, 0))
        self.speaker_engine_box.bind("<<ComboboxSelected>>", lambda _e: self.speaker_engine_var.set(self._key_of(engine_labels, self.speaker_engine_display_var.get())))
        self._tooltip(self.speaker_engine_box, TOOLTIP_TEXT["speaker_engine"])
        count_labels = {n: label for n, label in SPEAKER_COUNTS}
        self.speaker_count_label = ttk.Label(tech, text="People speaking")
        self.speaker_count_label.grid(row=len(rows) + 5, column=0, sticky="w", padx=(0, 10), pady=(4, 0))
        self.speaker_count_display_var = tk.StringVar(value=count_labels.get(self.speaker_count_var.get(), count_labels[0]))
        self.speaker_count_box = ttk.Combobox(tech, textvariable=self.speaker_count_display_var, values=list(count_labels.values()), state="readonly", width=48)
        self.speaker_count_box.grid(row=len(rows) + 5, column=1, sticky="w", pady=(4, 0))
        self.speaker_count_box.bind("<<ComboboxSelected>>", lambda _e: self.speaker_count_var.set(self._key_of(count_labels, self.speaker_count_display_var.get())))
        self._tooltip(self.speaker_count_box, TOOLTIP_TEXT["speaker_count"])
        self._sync_speakers_state()

        batch = self._section(parent, "Batch behaviour", 2)
        for index, (text, variable, key) in enumerate((
            ("Skip files already converted (outputs newer than the source)", self.skip_converted_var, "skip_converted"),
            ("Retry failed files once at the end", self.retry_failed_var, "retry_failed"),
            ("Windows notification when a long batch ends", self.notify_done_var, "notify_done"),
            ("'Convert with Docling' in Explorer's right-click menu", self.explorer_menu_var, "explorer_menu"),
            ("Run as Administrator (only for folders Windows protects)", self.run_as_admin_var, "run_admin"),
            ("Allow Docling's external plugins", self.allow_plugins_var, "plugins"),
        )):
            box = ttk.Checkbutton(batch, text=text, variable=variable)
            box.grid(row=index, column=0, sticky="w", pady=2)
            self._tooltip(box, TOOLTIP_TEXT[key])
            if key == "explorer_menu":
                box.configure(command=self._sync_explorer_menu)

        launcher = self._section(parent, "Launcher", 3)
        launcher.grid_columnconfigure(1, weight=1)
        ttk.Label(launcher, text="Update key").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        key_entry = ttk.Entry(launcher, textvariable=self.launcher_key_var, show="•", width=48)
        key_entry.grid(row=0, column=1, sticky="w", pady=3)
        key_entry.bind("<FocusOut>", lambda _e: self._save_settings())
        self._tooltip(key_entry, TOOLTIP_TEXT["launcher_key"])
        ttk.Label(launcher, style="Hint.TLabel",
                  text="Only needed if the launcher's GitHub repository is made private again; "
                       "today it is public and no key is needed.").grid(row=1, column=0, columnspan=2, sticky="w")

    # ------------------------------------------------------------------ Updates tab

    def _build_updates_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        section = self._section(parent, "Docling, add-ins, AI models and the launcher", 0)
        section.grid_columnconfigure(0, weight=1)
        self.updates_tree = ttk.Treeview(section, columns=("component", "installed", "installed_on", "latest", "released", "status"), show="headings", height=3)
        for column, title, width in (
            ("component", "Component", 225), ("installed", "Installed", 95), ("installed_on", "Installed on", 100),
            ("latest", "Latest", 95), ("released", "Released", 100), ("status", "Status", 240),
        ):
            self.updates_tree.heading(column, text=title, anchor="w")
            self.updates_tree.column(column, width=width, anchor="w", stretch=(column == "status"))
        self.updates_tree.grid(row=0, column=0, sticky="ew")
        self.updates_tree.tag_configure("update", foreground="#1a7f37")
        self.updates_tree.tag_configure("unknown", foreground="#8a8a8a")
        self.updates_tree.tag_configure("missing", foreground="#c62828")

        models_check = ttk.Checkbutton(section, text="Also update the AI models (replaces old copies and frees their disk space)",
                                       variable=self.update_models_var, command=self._save_settings)
        models_check.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._tooltip(models_check, TOOLTIP_TEXT["update_models"])
        buttons = ttk.Frame(section)
        buttons.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.check_updates_button = ttk.Button(buttons, text="Check now", command=lambda: self._check_updates(quiet=False))
        self.check_updates_button.grid(row=0, column=0, padx=(0, 8))
        self._tooltip(self.check_updates_button, TOOLTIP_TEXT["check_updates"])
        self.go_back_button = ttk.Button(buttons, text="Go back", command=self._on_go_back_clicked)
        self.go_back_button.grid(row=0, column=1)
        self.go_back_button.grid_remove()
        self._tooltip(self.go_back_button, TOOLTIP_TEXT["go_back"])
        self.reference_button = ttk.Button(buttons, text="Reference check", command=self._on_reference_check_clicked)
        self.reference_button.grid(row=0, column=2, padx=(8, 0))
        self._tooltip(self.reference_button, TOOLTIP_TEXT["reference_check"])

        status = self._section(parent, "Extension status", 1)
        status.grid_columnconfigure(0, weight=1)
        self.status_tree = ttk.Treeview(status, columns=("component", "status", "detail"), show="headings", height=7)
        for column, title, width in (("component", "Component", 170), ("status", "Status", 90), ("detail", "Detail", 560)):
            self.status_tree.heading(column, text=title, anchor="w")
            self.status_tree.column(column, width=width, anchor="w", stretch=(column == "detail"))
        self.status_tree.grid(row=0, column=0, sticky="ew")
        self.status_tree.tag_configure("ok", foreground="#1a7f37")
        self.status_tree.tag_configure("bad", foreground="#c62828")
        for name in ["Docling CLI", "GPU", "Speech (Whisper)", "RapidOCR", "EasyOCR", "Tesseract", "OnnxTR"]:
            self.status_tree.insert("", "end", values=(name, "Unknown", "Not checked yet"))
        ttk.Button(status, text="Check extensions", command=self._check_extensions).grid(row=1, column=0, sticky="w", pady=(8, 0))

    # ------------------------------------------------------------------ Log tab

    def _build_log_tab(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)
        ttk.Label(tab, text="What Docling is told (one example command; the run makes one per output folder)", style="Hint.TLabel").grid(row=0, column=0, sticky="w")
        command_entry = ttk.Entry(tab, textvariable=self.command_preview_var, state="readonly")
        command_entry.grid(row=1, column=0, sticky="ew", pady=(2, 10))
        self._tooltip(command_entry, TOOLTIP_TEXT["command_preview"])
        self.log_text = scrolledtext.ScrolledText(tab, height=12, wrap="word", state="disabled", font=("Consolas", 9), relief="flat", borderwidth=0)
        self.log_text.grid(row=2, column=0, sticky="nsew")

    # ------------------------------------------------------------------ Run bar

    def _build_run_bar(self) -> None:
        bar = ttk.Frame(self.root, padding=(16, 10, 16, 12))
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_columnconfigure(3, weight=1)
        self.run_button = ttk.Button(bar, text="Run conversion", command=self._on_run_clicked, style="Accent.TButton", width=18)
        self.run_button.grid(row=0, column=0, padx=(0, 8))
        self.stop_button = ttk.Button(bar, text="Stop", command=self._on_stop_clicked, width=8)
        self.stop_button.grid(row=0, column=1, padx=(0, 8))
        self.stop_button.grid_remove()
        self._tooltip(self.stop_button, TOOLTIP_TEXT["stop"])
        self.progress = ttk.Progressbar(bar, variable=self.progress_var, maximum=1.0, length=180)
        self.progress.grid(row=0, column=2, padx=(4, 12))
        ttk.Label(bar, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=3, sticky="w")
        open_button = ttk.Button(bar, text="Open output folder", command=self._open_output_folder)
        open_button.grid(row=0, column=4, padx=(8, 8))
        self._tooltip(open_button, TOOLTIP_TEXT["open_output"])
        self.queue_button = ttk.Button(bar, text="Queue…", command=self._show_queue, width=9)
        self.queue_button.grid(row=0, column=5, padx=(0, 8))
        self._tooltip(self.queue_button, TOOLTIP_TEXT["queue"])
        ttk.Button(bar, text="Exit", command=self._on_close, width=8).grid(row=0, column=6)

    # ------------------------------------------------------------------ small helpers

    def _tooltip(self, widget: tk.Widget, text: str) -> None:
        ToolTip(widget, text, lambda: self.show_tooltips_var.get())

    @staticmethod
    def _key_of(labels: dict[str, str], label: str) -> str:
        return next((key for key, value in labels.items() if value == label), next(iter(labels)))

    def _bind_var_changes(self) -> None:
        variables = [
            self.input_folder_var, self.output_folder_var, self.convert_all_files_var, self.mode_var,
            self.ocr_mode_var, self.ocr_engine_var, self.allow_plugins_var, self.portable_tesseract_var,
            self.portable_tesseract_path_var, self.run_as_admin_var, self.show_tooltips_var,
            self.keep_pictures_var, self.enrich_formula_var, self.enrich_chart_var, self.describe_pictures_var,
            self.describe_model_var, self.speech_model_var, self.video_speakers_var,
            self.speech_language_var, self.speaker_engine_var, self.speaker_count_var,
        ]
        for var in variables:
            var.trace_add("write", lambda *_: self._update_preview())
        for var in self.format_vars.values():
            var.trace_add("write", lambda *_: self._update_preview())

    def _selected_formats(self) -> list[str]:
        return [value for _, value in OUTPUT_FORMATS if self.format_vars[value].get()]

    def _settings_from_vars(self) -> LauncherSettings:
        return LauncherSettings(
            input_folder=self.input_folder_var.get().strip(),
            output_folder=self.output_folder_var.get().strip(),
            convert_all_files=self.convert_all_files_var.get(),
            selected_input_files=[str(path) for path in self.selected_input_files],
            conversion_mode=self.mode_var.get(),
            output_formats=self._selected_formats(),
            ocr_mode=self.ocr_mode_var.get(),
            ocr_engine=self.ocr_engine_var.get(),
            ocr_lang=self.ocr_lang_var.get().strip(),
            allow_external_plugins=self.allow_plugins_var.get(),
            portable_tesseract_enabled=self.portable_tesseract_var.get(),
            portable_tesseract_path=self.portable_tesseract_path_var.get().strip(),
            run_as_admin=self.run_as_admin_var.get(),
            show_tooltips=self.show_tooltips_var.get(),
            keep_pictures=self.keep_pictures_var.get(),
            enrich_formula=self.enrich_formula_var.get(),
            enrich_chart=self.enrich_chart_var.get(),
            describe_pictures=self.describe_pictures_var.get(),
            describe_model=self.describe_model_var.get(),
            describe_prompt=self.describe_prompt,
            speech_model=self.speech_model_var.get(),
            speech_language=self.speech_language_var.get(),
            video_speakers=self.video_speakers_var.get(),
            speaker_engine=self.speaker_engine_var.get(),
            speaker_count=int(self.speaker_count_var.get() or 0),
            skip_converted=self.skip_converted_var.get(),
            retry_failed=self.retry_failed_var.get(),
            notify_done=self.notify_done_var.get(),
            explorer_menu=self.explorer_menu_var.get(),
            watch_folder=self.watch_folder_var.get(),
            queue=list(self.queue_entries),
            reference_baseline=dict(self.settings.reference_baseline),
            update_models=self.update_models_var.get(),
            presets=dict(self.settings.presets),
            theme=self.theme_var.get(),
            launcher_update_key=self.launcher_key_var.get().strip(),
        )

    def _save_settings(self) -> None:
        self.settings = self._settings_from_vars()
        self.settings.save()

    def _update_preview(self) -> None:
        selected_source = (
            self.selected_input_files[0]
            if not self.convert_all_files_var.get() and self.selected_input_files
            else None
        )
        try:
            options = self._settings_from_vars().conversion_options()
            if not options.formats:
                options = options.__class__(**{**options.__dict__, "formats": ("md",)})
            preview = build_preview(
                self.input_folder_var.get().strip(), self.output_folder_var.get().strip(),
                self.mode_var.get(), options, source_path=selected_source,
            )
        except Exception as exc:
            preview = f"Unable to build preview: {exc}"
        self.command_preview_var.set(preview)

    def _sync_ocr_state(self) -> None:
        """With OCR off, an engine changes nothing — so it is not shown. Values survive hidden."""
        show = self.ocr_mode_var.get() != "off"
        for widget in self.ocr_dependent_widgets:
            widget.grid() if show else widget.grid_remove()
        self._sync_tesseract_state()

    def _sync_tesseract_state(self) -> None:
        """The portable-Tesseract row exists only while a Tesseract engine is chosen and OCR is on."""
        relevant = self.ocr_mode_var.get() != "off" and self.ocr_engine_var.get() in TESSERACT_ENGINES
        if self.tesseract_section is not None:
            self.tesseract_section.grid() if relevant else self.tesseract_section.grid_remove()
        state = "normal" if self.portable_tesseract_var.get() else "disabled"
        for widget in self.tesseract_widgets:
            widget.configure(state=state)
        self._update_preview()

    def _sync_describe_state(self) -> None:
        for widget in (self.describe_model_label, self.describe_model_box, self.describe_prompt_label, self.describe_prompt_frame):
            widget.grid() if self.describe_pictures_var.get() else widget.grid_remove()
        self._update_preview()

    def _sync_speakers_state(self) -> None:
        """The engine and the head count matter only while "Who said what" is ticked. The
        label column keeps the width of the longest of them even while they are hidden, so
        ticking the box never shifts the other boxes (measured once the theme's font is on)."""
        self.speaker_engine_label.update_idletasks()
        self.speaker_engine_label.master.grid_columnconfigure(0, minsize=self.speaker_engine_label.winfo_reqwidth() + 10)
        for widget in (self.speaker_engine_label, self.speaker_engine_box, self.speaker_count_label, self.speaker_count_box):
            widget.grid() if self.video_speakers_var.get() else widget.grid_remove()
        if hasattr(self, "command_preview_var"):
            self._update_preview()

    def _take_prompt(self) -> None:
        text = self.describe_prompt_text.get("1.0", "end").strip()
        if text and text != self.describe_prompt:
            self.describe_prompt = text
            self._save_settings()

    def _reset_prompt(self) -> None:
        self.describe_prompt = DEFAULT_DESCRIBE_PROMPT
        self.describe_prompt_text.delete("1.0", "end")
        self.describe_prompt_text.insert("1.0", DEFAULT_DESCRIBE_PROMPT)
        self._save_settings()

    def _sync_explorer_menu(self) -> None:
        exe = Path(sys.executable) if getattr(sys, "frozen", False) else None
        if self.explorer_menu_var.get() and not exe:
            self._append_log("The Explorer menu entry can only point at the built launcher exe.")
            self.explorer_menu_var.set(False)
            return
        try:
            windows.set_explorer_menu(self.explorer_menu_var.get(), exe)
            self._append_log("Explorer's right-click menu now has 'Convert with Docling'." if self.explorer_menu_var.get()
                             else "'Convert with Docling' removed from Explorer's menu.")
        except OSError as exc:
            self._append_log(f"Could not change Explorer's menu: {exc}")
        self._save_settings()

    def _sync_input_scope_state(self) -> None:
        selecting_files = not self.convert_all_files_var.get()
        if self.select_files_button:
            self.select_files_button.configure(state="normal" if selecting_files else "disabled")
        count = len(self.selected_input_files)
        self.selected_files_summary_var.set(
            "" if not selecting_files else ("No files selected." if not count else f"{count} file(s) selected.")
        )
        if self.run_button:
            self.run_button.configure(text="Run selected files" if selecting_files else "Run conversion")
        beside = self.mode_var.get() == "beside"
        for widget in self.output_widgets:
            widget.configure(state="disabled" if beside else "normal")
        self._update_preview()

    def _browse_folder(self, variable: tk.StringVar) -> None:
        initial = variable.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(initialdir=initial)
        if selected:
            variable.set(selected)
            if variable is self.input_folder_var:
                self.selected_input_files = []
                self._sync_input_scope_state()
            self._save_settings()

    def _select_input_files(self) -> None:
        raw_input_folder = self.input_folder_var.get().strip()
        input_folder = Path(raw_input_folder)
        if not raw_input_folder or not input_folder.is_dir():
            messagebox.showerror(APP_NAME, "Choose a valid input folder before selecting files.")
            return
        patterns = " ".join(f"*{extension}" for extension in sorted(SUPPORTED_INPUT_EXTENSIONS))
        selected = filedialog.askopenfilenames(
            title="Select files to convert", initialdir=str(input_folder),
            filetypes=[("Supported documents", patterns), ("All files", "*.*")],
        )
        if selected:
            self._take_selected_files([Path(raw) for raw in selected], input_folder)

    def _take_selected_files(self, files: list[Path], input_folder: Path) -> None:
        valid: list[Path] = []
        rejected = 0
        input_root = input_folder.resolve()
        for path in files:
            try:
                path.resolve().relative_to(input_root)
            except ValueError:
                rejected += 1
                continue
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
                rejected += 1
                continue
            valid.append(path)
        self.selected_input_files = sorted({path.resolve() for path in valid}, key=lambda p: str(p).lower())
        self.convert_all_files_var.set(False)
        self._sync_input_scope_state()
        self._save_settings()
        if rejected:
            messagebox.showwarning(APP_NAME, f"Ignored {rejected} file(s). Selected files must be supported and inside the input folder.")

    def _on_drop(self, paths: list[Path]) -> None:
        """A folder becomes the input folder; files become the selection (their common folder the input)."""
        paths = [path for path in paths if path.exists()]
        if not paths:
            return
        folders = [path for path in paths if path.is_dir()]
        files = [path for path in paths if path.is_file()]
        if folders and not files:
            self.input_folder_var.set(str(folders[0]))
            self.selected_input_files = []
            self.convert_all_files_var.set(True)
            self._sync_input_scope_state()
            self._save_settings()
            self._append_log(f"Input folder: {folders[0]}")
            self.notebook.select(self.convert_tab)
            return
        if files:
            common = Path(os.path.commonpath([str(path.parent) for path in files]))
            self.input_folder_var.set(str(common))
            self._take_selected_files(files, common)
            self._append_log(f"{len(self.selected_input_files)} dropped file(s) selected in {common}")
            self.notebook.select(self.convert_tab)

    # ------------------------------------------------------------------ presets

    def _refresh_presets(self) -> None:
        names = sorted(self.settings.presets)
        self.preset_box.configure(values=names)
        if self.preset_var.get() not in names:
            self.preset_var.set("")
        self.delete_preset_button.configure(state="normal" if self.preset_var.get() else "disabled")

    def _save_preset(self) -> None:
        name = simpledialog.askstring(APP_NAME, "Name for this way of converting:", parent=self.root, initialvalue=self.preset_var.get())
        if not name or not name.strip():
            return
        name = name.strip()
        current = self._settings_from_vars()
        self.settings.presets[name] = {field: getattr(current, field) for field in PRESET_FIELDS}
        self.preset_var.set(name)
        self._save_settings()
        self._refresh_presets()
        self._append_log(f"Preset saved: {name}")

    def _delete_preset(self) -> None:
        name = self.preset_var.get()
        if name and name in self.settings.presets and messagebox.askyesno(APP_NAME, f"Delete the preset '{name}'?"):
            del self.settings.presets[name]
            self.preset_var.set("")
            self._save_settings()
            self._refresh_presets()

    def _apply_preset(self, name: str) -> None:
        values = self.settings.presets.get(name)
        if not values:
            return
        self.mode_var.set(values.get("conversion_mode", self.mode_var.get()))
        wanted = set(values.get("output_formats", []))
        for fmt, var in self.format_vars.items():
            var.set(fmt in wanted)
        for field, var in (
            ("ocr_mode", self.ocr_mode_var), ("ocr_engine", self.ocr_engine_var),
            ("allow_external_plugins", self.allow_plugins_var), ("portable_tesseract_enabled", self.portable_tesseract_var),
            ("portable_tesseract_path", self.portable_tesseract_path_var), ("keep_pictures", self.keep_pictures_var),
            ("enrich_formula", self.enrich_formula_var), ("enrich_chart", self.enrich_chart_var),
            ("describe_pictures", self.describe_pictures_var), ("describe_model", self.describe_model_var),
            ("speech_model", self.speech_model_var), ("video_speakers", self.video_speakers_var),
            ("speech_language", self.speech_language_var), ("speaker_engine", self.speaker_engine_var),
            ("speaker_count", self.speaker_count_var),
            ("skip_converted", self.skip_converted_var), ("retry_failed", self.retry_failed_var),
            ("ocr_lang", self.ocr_lang_var),
        ):
            if field in values:
                var.set(values[field])
        if values.get("describe_prompt"):
            self.describe_prompt = values["describe_prompt"]
            self.describe_prompt_text.delete("1.0", "end")
            self.describe_prompt_text.insert("1.0", self.describe_prompt)
        self.ocr_display_var.set(dict(OCR_MODES).get(self.ocr_mode_var.get(), ""))
        self.describe_display_var.set(dict(DESCRIBE_MODELS).get(self.describe_model_var.get(), ""))
        self.speech_display_var.set(next((f"{n}  —  {note}" for n, _, note in SPEECH_MODELS if n == self.speech_model_var.get()), ""))
        self.speech_language_display_var.set(next((name if not code else f"{name}  ({code})" for code, name in SPEECH_LANGUAGES if code == self.speech_language_var.get()), ""))
        self.speaker_engine_display_var.set(dict(SPEAKER_ENGINES).get(self.speaker_engine_var.get(), ""))
        self.speaker_count_display_var.set(dict(SPEAKER_COUNTS).get(int(self.speaker_count_var.get() or 0), ""))
        self._sync_speakers_state()
        self._sync_ocr_state()
        self._sync_describe_state()
        self._sync_input_scope_state()
        self._refresh_presets()
        self._save_settings()
        self._append_log(f"Preset applied: {name}")

    # ------------------------------------------------------------------ log and worker plumbing

    def _append_log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        lines = message.splitlines() or [""]
        self.log_text.configure(state="normal")
        for line in lines:
            self.log_text.insert("end", f"[{stamp}] {line}\n")
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def _queue_log(self, message: str) -> None:
        self.log_queue.put(("log", message))

    def _queue_call(self, function: Callable[[], None]) -> None:
        """Run `function` on the Tk thread at the next pump."""
        self.log_queue.put(("call", function))

    def _start_job(self, kind: str, target: Callable[[], None]) -> bool:
        """Run `target` on a worker thread; the log pump turns only while something runs.
        Heavy jobs own Docling's environment and refuse to overlap; light ones just pump."""
        if kind in HEAVY_JOBS and self.active_jobs & HEAVY_JOBS:
            return False
        self.active_jobs.add(kind)
        self._sync_buttons()

        def run() -> None:
            try:
                target()
            except Exception as exc:
                self._queue_log(f"ERROR: {exc}")
            finally:
                self.log_queue.put(("done", kind))

        threading.Thread(target=run, daemon=True).start()
        if not self._pumping:
            self._pumping = True
            self.root.after(100, self._pump)
        return True

    def _wake_pump(self) -> None:
        """Start the pump if it is not turning (a message arrived while idle)."""
        if not self._pumping:
            self._pumping = True
            self.root.after(0, self._pump)

    def _post(self, function: Callable[[], None]) -> None:
        """From any thread: run `function` on the Tk thread soon. The message goes through
        the queue; the wake-up call is the only Tk call, and is harmless if refused."""
        self.log_queue.put(("call", function))
        try:
            self.root.after(0, self._wake_pump)
        except RuntimeError:
            pass  # no event loop right now (tests drive the pump themselves)

    def _pump(self) -> None:
        while True:
            try:
                kind, payload = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "call":
                payload()
            elif kind == "done":
                self.active_jobs.discard(str(payload))
                self._sync_buttons()
                if payload == "batch" and not self.running:
                    self._continue_after_batch()
        if self.active_jobs or not self.log_queue.empty():
            self.root.after(100, self._pump)
        else:
            self._pumping = False  # idle again: no timer runs

    @property
    def running(self) -> bool:
        return bool(self.active_jobs & HEAVY_JOBS)

    def _sync_buttons(self) -> None:
        busy = self.running
        batch = "batch" in self.active_jobs
        if self.run_button:
            self.run_button.configure(state="disabled" if busy else "normal")
        if self.stop_button:
            if batch:
                self.stop_button.grid()
                self.stop_button.configure(state="disabled" if self._stop_requested else "normal")
            else:
                self.stop_button.grid_remove()
        checking = "check" in self.active_jobs
        for button in (self.update_button, self.check_updates_button, self.go_back_button, getattr(self, "reference_button", None)):
            if button:
                button.configure(state="disabled" if busy or checking else "normal")

    def _set_status(self, text: str, fraction: float | None = None) -> None:
        if len(text) > 60:  # the bar has buttons on both sides; a long file name is shortened in the middle
            text = text[:36] + "…" + text[-20:]
        self.status_var.set(text)
        if fraction is not None:
            self.progress_var.set(max(0.0, min(1.0, fraction)))

    # ------------------------------------------------------------------ results table

    def _results_reset(self, files: list[Path], input_root: Path) -> None:
        if not self.results_tree:
            return
        self.results_tree.delete(*self.results_tree.get_children())
        self.result_rows = {}
        for path in files:
            try:
                where = str(path.parent.relative_to(input_root)) or "."
            except ValueError:
                where = str(path.parent)
            item = self.results_tree.insert("", "end", values=(path.name, where, "waiting", ""), tags=("dim",))
            self.result_rows[path.name] = item

    def _results_set(self, name: str, result: str, seconds: str = "", tag: str = "") -> None:
        item = self.result_rows.get(name) if self.results_tree else None
        if not item:
            return
        values = list(self.results_tree.item(item, "values"))
        values[2] = result
        if seconds:
            values[3] = seconds
        self.results_tree.item(item, values=values, tags=(tag,) if tag else ())
        self.results_tree.see(item)

    def _open_result_folder(self) -> None:
        if not self.results_tree:
            return
        selected = self.results_tree.selection()
        if not selected:
            return
        where = self.results_tree.item(selected[0], "values")[1]
        folder = self._output_folder_for(Path(where))
        if folder and folder.is_dir():
            os.startfile(str(folder))

    def _output_folder_for(self, relative: Path) -> Path | None:
        mode = self.mode_var.get()
        raw = self.input_folder_var.get().strip() if mode == "beside" else self.output_folder_var.get().strip()
        if not raw:
            return None
        root = Path(raw)
        return root if mode == "flat" else root / relative

    def _open_output_folder(self) -> None:
        folder = self._output_folder_for(Path("."))
        if folder and folder.is_dir():
            os.startfile(str(folder))
        else:
            messagebox.showinfo(APP_NAME, "The output folder does not exist yet.")

    # ------------------------------------------------------------------ extension status

    def _apply_statuses(self, statuses) -> None:
        if not self.status_tree:
            return
        self.status_tree.delete(*self.status_tree.get_children())
        for status in statuses:
            self.status_tree.insert("", "end", values=(status.name, "OK" if status.ok else "Missing", status.detail),
                                    tags=("ok" if status.ok else "bad",))

    def _check_extensions(self) -> None:
        self._append_log("Checking extension status.")
        env = environment_for_run(self.portable_tesseract_var.get(), self.portable_tesseract_path_var.get(), use_launcher_temp=False)

        def worker() -> None:
            statuses = check_all_dependencies(env)
            self._queue_call(lambda: self._apply_statuses(statuses))
            for status in statuses:
                self._queue_log(f"{status.name}: {'OK' if status.ok else 'Missing'} - {status.detail}")

        self._start_job("extensions", worker)

    # ------------------------------------------------------------------ updates

    def _show_installed_versions(self) -> None:
        statuses = updates.check_updates(online=False)
        models = check_models(self.speech_model_var.get(), online=False)
        self._apply_update_statuses(statuses, quiet=True, models=models)

    def _ability_enabled(self, ability: str | None) -> bool:
        """Is the ability that needs a model ticked? None means every conversion needs it;
        "ability:choice" means ticked AND that choice is the one a run would use."""
        if ability is None or ability == "speech":
            return True
        name, _, choice = ability.partition(":")
        variable = getattr(self, f"{name}_var", None)
        if variable is None or not variable.get():
            return False
        if not choice:
            return True
        if name == "describe_pictures":
            return self.describe_model_var.get() == choice
        if name == "video_speakers":
            return self.speaker_engine_var.get() == choice
        return True

    def _apply_update_statuses(self, statuses, quiet: bool, models: list[ModelStatus] | None = None) -> None:
        self.update_statuses = statuses
        if models is not None:
            self.model_statuses = models
        docling = next((s for s in statuses if s.name == "docling"), None)
        self.docling_version_var.set(f"Docling {docling.installed}" if docling and docling.installed else "Docling not found")

        available = updates.upgrade_targets(statuses)
        wanted_models = model_targets(self.model_statuses, self._ability_enabled) if self.update_models_var.get() else []
        launcher = self.launcher_release
        launcher_newer = bool(launcher and launcher.newer)
        if docling and docling.update_available:
            self.update_status_var.set(f"{docling.latest} available")
        elif launcher_newer:
            self.update_status_var.set(f"launcher {launcher.version} available")
        elif available:
            self.update_status_var.set(f"{len(available)} add-in update(s) available")
        elif wanted_models:
            newer = [m for m in wanted_models if m.update_available]
            missing = [m for m in wanted_models if m.missing]
            parts = ([f"{len(newer)} newer model(s)"] if newer else []) + ([f"{len(missing)} model(s) to download"] if missing else [])
            self.update_status_var.set(", ".join(parts))
        elif quiet:
            self.update_status_var.set("")
        elif docling and docling.latest:
            self.update_status_var.set("up to date")
        else:
            self.update_status_var.set("")
        if self.update_button:
            self.update_button.grid() if (available or wanted_models or launcher_newer) else self.update_button.grid_remove()

        if self.updates_tree:
            self.updates_tree.delete(*self.updates_tree.get_children())
            if launcher or self.launcher_release_note:
                if launcher:
                    row = ("Docling Launcher", APP_VERSION, "—", launcher.version, launcher.published or "—",
                           "Update available" if launcher.newer else "Up to date")
                    tag = "update" if launcher.newer else ""
                else:
                    row = ("Docling Launcher", APP_VERSION, "—", "—", "—", f"Could not check: {self.launcher_release_note}")
                    tag = "unknown"
                self.updates_tree.insert("", "end", values=row, tags=(tag,) if tag else ())
            for status in statuses:
                if status.latest is None:
                    latest, released, state, tag = "—", "—", ("Not checked" if quiet else "Could not check"), "unknown"
                else:
                    latest, released, state = status.latest, status.released or "—", status.state
                    tag = "update" if status.update_available else ""
                self.updates_tree.insert("", "end", values=(status.label, status.installed or "—", status.installed_on or "—", latest, released, state), tags=(tag,) if tag else ())
            for model in self.model_statuses:
                needed = self._ability_enabled(model.ability)
                if model.state == "unchecked" and model.installed_sha:
                    latest, released, tag, state = "—", "—", "unknown", "Not checked"
                elif model.state == "newer":
                    latest, released, tag, state = "newer", model.latest_on or "—", "update", model.state_text(needed)
                elif model.state == "current":
                    latest, released, tag, state = "same", model.latest_on or "—", "", model.state_text(needed)
                elif model.state == "missing":
                    latest, released, tag, state = "—", model.latest_on or "—", ("missing" if needed else "unknown"), model.state_text(needed)
                else:
                    latest, released, tag, state = "—", "—", "unknown", model.state_text(needed)
                self.updates_tree.insert("", "end", values=(model.label, "downloaded" if model.installed_sha else "—", model.installed_on or "—", latest, released, state), tags=(tag,) if tag else ())
            self.updates_tree.configure(height=max(3, len(statuses) + len(self.model_statuses) + 1))

        point = updates.restore_point()
        if self.go_back_button:
            if point:
                self.go_back_button.configure(text=f"Go back to Docling {point[1]}")
                self.go_back_button.grid()
            else:
                self.go_back_button.grid_remove()
        self._sync_buttons()

    def _check_updates(self, quiet: bool) -> None:
        if "check" in self.active_jobs:
            return
        if not quiet:
            self._append_log("Checking for updates.")
            self.update_status_var.set("checking…")
        speech = self.speech_model_var.get()
        key = self.launcher_key_var.get().strip() or None

        def worker() -> None:
            statuses = updates.check_updates(online=True)
            models = check_models(speech, online=True)
            release = launcher_update.check(key)
            if isinstance(release, str):
                self.launcher_release, self.launcher_release_note = None, release
            else:
                self.launcher_release, self.launcher_release_note = release, ""
            gpu = gpu_status()
            self._queue_call(lambda: self._apply_update_statuses(statuses, quiet=quiet, models=models))
            self._queue_call(lambda: self.docling_version_var.set(
                self.docling_version_var.get().split("  ·")[0] + ("  ·  GPU in use" if gpu.ok else "  ·  CPU only")))
            if quiet:
                return
            if not statuses:
                self._queue_log("Docling was not found in its environment.")
                return
            if all(status.latest is None for status in statuses):
                self._queue_log("Could not reach the package index. Is the internet connected?")
                return
            for status in statuses:
                if status.update_available:
                    self._queue_log(f"{status.label}: {status.installed} -> {status.latest} available")
            for model in models:
                if model.update_available:
                    self._queue_log(f"{model.label}: a newer model was published on {model.latest_on}.")
                elif model.missing and self._ability_enabled(model.ability):
                    self._queue_log(f"{model.label}: not downloaded yet ({model.gb:.1f} GB) — needed by a ticked ability.")
            if isinstance(release, str):
                self._queue_log(f"Launcher: could not check ({release}).")
            elif release.newer:
                self._queue_log(f"Launcher {release.version} is available (released {release.published}).")
            newer_launcher = bool(self.launcher_release and self.launcher_release.newer)
            if not updates.upgrade_targets(statuses) and not model_targets(models, self._ability_enabled) and not newer_launcher:
                self._queue_log("Everything is up to date.")

        self._start_job("check", worker)

    def _on_update_clicked(self) -> None:
        targets = updates.upgrade_targets(self.update_statuses)
        models = model_targets(self.model_statuses, self._ability_enabled) if self.update_models_var.get() else []
        release = self.launcher_release if (self.launcher_release and self.launcher_release.newer) else None
        if not targets and not models and not release:
            return
        before = {status.name: status.installed for status in self.update_statuses}
        labels = ", ".join(status.label for status in self.update_statuses if status.update_available)
        torch_before = updates.torch_version()
        speech = self.speech_model_var.get()
        key = self.launcher_key_var.get().strip() or None

        def worker() -> None:
            code = 0
            if targets:
                self._queue_log(f"Updating {labels}. This can take a few minutes.")
                snapshot = updates.take_snapshot()
                self._queue_log(f"Restore point saved: {snapshot.name}" if snapshot else "Warning: could not save a restore point; continuing without one.")
                code = updates.run_upgrade(targets, self._queue_log, job=self.job)
                if code == 0:
                    code = updates.restore_gpu_edition(torch_before, self._queue_log, job=self.job)
                statuses = updates.check_updates(online=False)
                self._queue_call(lambda: self._apply_update_statuses(statuses, quiet=True))
                changed = [f"{s.label} {before.get(s.name)} -> {s.installed}" for s in statuses
                           if s.installed and before.get(s.name) and s.installed != before.get(s.name)]
                if code == 0:
                    self._queue_log("Update finished: " + (", ".join(changed) if changed else "nothing changed."))
                else:
                    self._queue_log(f"Update failed (exit code {code}). Your previous versions are safe: use 'Go back' if Docling misbehaves.")
            if models and code == 0:
                names = ", ".join(m.label for m in models)
                total = sum(m.gb for m in models if m.missing or m.update_available)
                self._queue_log(f"Updating models: {names} (about {total:.1f} GB to download).")
                model_code = run_model_update(models, self._queue_log, job=self.job)
                fresh = check_models(speech, online=False)
                self._queue_call(lambda: self._apply_update_statuses(self.update_statuses, quiet=True, models=fresh))
                self._queue_log("Models are up to date." if model_code == 0 else f"Model update ended with errors (exit code {model_code}); see the lines above.")
            if code == 0 and (targets or models):
                self._queue_log("Checking the update against the reference documents.")
                after = updates.installed_versions(["docling"]).get("docling") or "?"
                self._run_reference_check(after)
            if release and code == 0:
                self._queue_log(f"Downloading launcher {release.version}.")
                new_exe = launcher_update.download(release, key, self._queue_log)
                if new_exe:
                    self._queue_call(lambda: self._install_launcher(new_exe))
                    return
            self._queue_call(lambda: self._check_updates(quiet=True))

        if not self._start_job("update", worker):
            messagebox.showinfo(APP_NAME, "Wait for the current job to finish first.")

    def _install_launcher(self, new_exe: Path) -> None:
        if not messagebox.askyesno(APP_NAME, "The new launcher is downloaded. Close this one and start the new one now?"):
            self._append_log("The new launcher is ready beside this one; say yes next time to install it.")
            return
        self._save_settings()
        if launcher_update.install(new_exe) is None:
            self._append_log("Self-update works only from the built exe.")
            return
        self.job.terminate()
        self.job.close()
        self.root.destroy()

    def _on_go_back_clicked(self) -> None:
        point = updates.restore_point()
        if not point:
            return
        snapshot, version = point
        if not messagebox.askyesno(APP_NAME, f"Reinstall the versions saved on {updates.snapshot_label(snapshot)} (Docling {version})?"):
            return

        def worker() -> None:
            self._queue_log(f"Going back to Docling {version}.")
            code = updates.run_restore(snapshot, self._queue_log, job=self.job)
            statuses = updates.check_updates(online=False)
            self._queue_call(lambda: self._apply_update_statuses(statuses, quiet=True))
            docling = next((s.installed for s in statuses if s.name == "docling"), None)
            self._queue_log(f"Restored. Docling is now {docling}." if code == 0 else f"Restore failed (exit code {code}). Docling is {docling}.")
            self._queue_call(lambda: self._check_updates(quiet=True))

        if not self._start_job("restore", worker):
            messagebox.showinfo(APP_NAME, "Wait for the current job to finish first.")

    # ------------------------------------------------------------------ batch conversion

    def _validated_selected_files(self, input_folder: Path) -> list[Path]:
        if not self.selected_input_files:
            raise ValueError("Select one or more files to convert.")
        input_root = input_folder.resolve()
        files: list[Path] = []
        for path in self.selected_input_files:
            resolved = path.resolve()
            try:
                resolved.relative_to(input_root)
            except ValueError:
                raise ValueError("Some selected files are outside the input folder. Select the files again.")
            if not resolved.is_file() or resolved.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
                raise ValueError("Some selected files are no longer available or unsupported. Select the files again.")
            files.append(resolved)
        return sorted(set(files), key=lambda path: str(path).lower())

    def _validate(self) -> tuple[Path, Path | None, list[str], list[Path] | None]:
        input_folder = Path(self.input_folder_var.get().strip())
        if not self.input_folder_var.get().strip() or not input_folder.is_dir():
            raise ValueError("Choose a valid input folder.")
        formats = self._selected_formats()
        if not formats:
            raise ValueError("Select at least one output format.")
        output_folder: Path | None = None
        if self.mode_var.get() != "beside":
            raw_output = self.output_folder_var.get().strip()
            if not raw_output:
                raise ValueError("Choose an output folder.")
            output_folder = Path(raw_output)
        if self.ocr_mode_var.get() != "off" and self.ocr_engine_var.get() in TESSERACT_ENGINES and self.portable_tesseract_var.get():
            raw_tesseract = self.portable_tesseract_path_var.get().strip()
            if not raw_tesseract or not Path(raw_tesseract).exists():
                raise ValueError("Choose a valid portable Tesseract folder.")
        if not resolve_docling():
            raise ValueError("docling.exe was not found. Put it in .venv\\Scripts, next to the app, or on PATH.")
        selected_files = None if self.convert_all_files_var.get() else self._validated_selected_files(input_folder)
        return input_folder, output_folder, formats, selected_files

    def _on_run_clicked(self) -> None:
        if self.running:
            return
        try:
            input_folder, output_folder, formats, selected_files = self._validate()
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self._save_settings()
        self._stop_requested = False
        self._set_status("Starting…", 0.0)
        self._append_log("Starting conversion." if selected_files is None else f"Starting conversion of {len(selected_files)} selected file(s).")
        settings = self._batch_override or self._settings_from_vars()
        self._batch_override = None
        self._start_job("batch", lambda: self._run_batch(input_folder, output_folder, formats, selected_files, settings))

    def _on_stop_clicked(self) -> None:
        if "batch" not in self.active_jobs or self._stop_requested:
            return
        self._stop_requested = True
        self._append_log("Stopping — Docling is being closed.")
        self._set_status("Stopping…")
        self._sync_buttons()
        self.job.terminate()

    def _batch_log(self, line: str) -> None:
        """Log lines from Docling also drive the results table and the progress bar."""
        self._queue_log(line)
        match = _PROCESSING.match(line)
        if match:
            name = self._shown_name(match.group(1))
            self._queue_call(lambda: (self._results_set(name, "converting…"), self._set_status(f"{self.batch_done + 1} of {self.batch_total}: {name}")))
            return
        match = _FINISHED.match(line)
        if match:
            name, seconds = self._shown_name(match.group(1)), match.group(2)
            self.batch_done += 1
            done, total = self.batch_done, self.batch_total
            left = ""
            if 0 < done < total and self.batch_started:
                per_file = (time.time() - self.batch_started) / done
                remaining = per_file * (total - done)
                left = f" — about {int(remaining // 60)} min left" if remaining >= 90 else f" — about {int(remaining)} s left"
            self._queue_call(lambda: (self._results_set(name, "converted", f"{float(seconds):.0f} s", "ok"),
                                      self._set_status(f"{done} of {total} done{left}", done / total if total else None)))
            return
        match = _DESCRIBED.match(line)
        if match:
            done, total = int(match.group(1)), int(match.group(2))
            self._queue_call(lambda: self._set_status(f"Describing pictures: {done} of {total}", done / total if total else None))

    def _shown_name(self, name: str) -> str:
        """A wrapped sound file is reported by its own name."""
        for source, wrapper in self._stand_ins.items():
            if wrapper.name == name:
                return source.name
        return name

    def _run_batch(self, input_folder: Path, output_folder: Path | None, formats: list[str],
                   selected_files: list[Path] | None, settings: LauncherSettings) -> None:
        windows.keep_awake(True)  # this thread lives as long as the batch; Windows may not sleep meanwhile
        try:
            self._run_batch_inner(input_folder, output_folder, formats, selected_files, settings)
        finally:
            windows.keep_awake(False)

    def _run_batch_inner(self, input_folder: Path, output_folder: Path | None, formats: list[str],
                         selected_files: list[Path] | None, settings: LauncherSettings) -> None:
        self._transcripts = []
        self._last_report = None
        self._queue_call(lambda: (self.report_button.configure(state="disabled"), self.speakers_button.grid_remove()))
        if selected_files is None:
            files = discover_input_files(input_folder)
            self._queue_log(f"Discovered {len(files)} supported input file(s).")
        else:
            files = selected_files
            self._queue_log(f"Using {len(files)} selected input file(s).")
        self._queue_call(lambda listed=list(files): self._results_reset(listed, input_folder))

        media = [path for path in files if path.suffix.lower() in MEDIA_INPUT_EXTENSIONS]
        if media and not speech_available():
            self._queue_log(f"Skipped {len(media)} sound/video file(s): Docling's speech library (Whisper) is not installed in this environment.")
            for path in media:
                self._queue_call(lambda p=path: self._results_set(p.name, "skipped — no speech library", tag="dim"))
            files = [path for path in files if path not in media]

        output_root = output_folder or input_folder
        if settings.skip_converted:
            skipped = [path for path in files
                       if already_converted(path, output_dir_for(path, input_folder, output_root, settings.conversion_mode), formats)]
            if skipped:
                self._queue_log(f"Skipped {len(skipped)} file(s) already converted (outputs newer than the source).")
                for path in skipped:
                    self._queue_call(lambda p=path: self._results_set(p.name, "already converted", tag="dim"))
                files = [path for path in files if path not in skipped]
        if not files:
            self._queue_log("Nothing to convert.")
            self._queue_call(lambda: self._set_status("Nothing to convert.", 1.0))
            return

        stem_counts: dict[str, int] = {}
        for source in files:
            stem_counts[source.stem.lower()] = stem_counts.get(source.stem.lower(), 0) + 1
        if settings.conversion_mode == "flat":
            duplicates = sorted(stem for stem, count in stem_counts.items() if count > 1)
            if duplicates:
                self._queue_log("Warning: duplicate file names in single-folder mode may overwrite outputs: " + ", ".join(duplicates[:20]))

        # OCR "auto": look at each PDF once; scans read, digital documents do not.
        text_chars: dict[Path, int | None] = {}
        if settings.ocr_mode == "auto":
            text_chars = probe_text_layers(files)
            if text_chars:
                scans = sum(1 for chars in text_chars.values() if chars is None or chars < 50)
                self._queue_log(f"OCR decided per file: {scans} scanned PDF(s) will be read with OCR, {len(text_chars) - scans} digital PDF(s) without.")

        # "Who said what" exists only on Docling's video road: sound files travel there
        # inside a video container (see media.py), under the same name.
        stand_ins: dict[Path, Path] = {}
        if settings.video_speakers:
            for source in files:
                if is_audio(source):
                    wrapper = wrap_audio_as_video(source)
                    if wrapper:
                        stand_ins[source] = wrapper
                    else:
                        self._queue_log(f"Could not prepare {source.name} for speaker separation; transcribing without speakers.")
        self._stand_ins = stand_ins

        options = settings.conversion_options()
        plans = build_batch_plans(files, input_folder, output_root, settings.conversion_mode, options, stand_ins, text_chars)
        for plan in plans:
            plan.output_dir.mkdir(parents=True, exist_ok=True)
        self._queue_log(f"{len(files)} file(s) in {len(plans)} Docling run(s).")
        self.batch_total, self.batch_done = len(files), 0
        started_at = time.time()
        self.batch_started = started_at

        if settings.run_as_admin and not is_user_admin():
            exit_code = run_elevated_batch(plans, self._batch_log)
            self._queue_log(f"Elevated batch exited with code {exit_code}.")
        else:
            self._run_plans(plans)

        # Once more for whatever failed, on its own.
        if not self._stop_requested and settings.retry_failed:
            originals = {wrapper: source for source, wrapper in stand_ins.items()}
            failed = [originals.get(s, s) for plan in plans for s in plan.sources
                      if not converted_ok(s, plan.output_dir, formats, started_at)]
            if failed and len(failed) < len(files):
                self._queue_log(f"Retrying {len(failed)} failed file(s).")
                for path in failed:
                    self._queue_call(lambda p=path: self._results_set(p.name, "retrying…"))
                self._run_plans(build_batch_plans(failed, input_folder, output_root, settings.conversion_mode, options, stand_ins, text_chars))

        self._finish_media(plans, settings)

        # The describe pass: Docling's describing model on the pictures each Markdown links.
        if not self._stop_requested and settings.describe_pictures and "md" in formats:
            markdowns = [plan.output_dir / f"{s.stem}.md" for plan in plans for s in plan.sources
                         if converted_ok(s, plan.output_dir, formats, started_at)]
            markdowns = [m for m in markdowns if m.is_file()]
            if markdowns:
                self._queue_log(f"Describing pictures in {len(markdowns)} file(s) with the {settings.describe_model} model.")
                self._queue_call(lambda: self._set_status("Describing pictures…"))
                code = describe_pictures_in(markdowns, settings.describe_model, self._batch_log, job=self.job,
                                            env=plans[0].env if plans else None, cancelled=lambda: self._stop_requested,
                                            prompt=settings.describe_prompt)
                if code != 0 and not self._stop_requested:
                    self._queue_log(f"The describing pass ended with code {code}; the documents are converted, some pictures may lack their text.")

        self._report_results(plans, formats, started_at)

    def _run_plans(self, plans) -> None:
        for index, plan in enumerate(plans, start=1):
            if self._stop_requested:
                break
            self._queue_log(f"[{index}/{len(plans)}] {len(plan.sources)} file(s) -> {plan.output_dir}")
            exit_code = stream_process(plan.command, plan.env, self._batch_log, job=self.job, cwd=plan.output_dir,
                                       tidy=tidy_docling_line, cancelled=lambda: self._stop_requested)
            if self._stop_requested:
                break
            if exit_code != 0:
                self._queue_log(f"Docling exited with code {exit_code}.")

    def _finish_media(self, plans, settings: LauncherSettings) -> None:
        """After Docling: the transcript by speaker, the wrappers and their black frames gone."""
        wrappers = set(self._stand_ins.values())
        for wrapper in wrappers:
            discard_wrapper(wrapper)
        for plan in plans:
            for source in plan.sources:
                if not is_media(source):
                    continue
                if source in wrappers:
                    shutil.rmtree(plan.output_dir / f"{source.stem}_artifacts", ignore_errors=True)
                json_path = plan.output_dir / f"{source.stem}.json"
                markdown = plan.output_dir / f"{source.stem}.md"
                if is_video(source) and source not in wrappers and json_path.is_file() and markdown.is_file():
                    stamped = add_scene_times(markdown, scene_times(json_path))
                    if stamped:
                        self._queue_log(f"{source.stem}.md: {stamped} scene(s) stamped with their time.")
                if json_path.is_file() and "json" not in settings.output_formats:
                    json_path.unlink()
                vtt = plan.output_dir / f"{source.stem}.vtt"
                if not vtt.is_file():
                    continue
                try:
                    text = speakers_markdown(vtt.read_text(encoding="utf-8"), source.stem) if settings.video_speakers else None
                    if text and "md" in settings.output_formats:
                        markdown.write_text(text, encoding="utf-8")
                        self._transcripts.append(markdown)
                        self._queue_log(f"{source.stem}.md: transcript written by speaker.")
                    if "vtt" not in settings.output_formats:
                        vtt.unlink()
                except OSError as exc:
                    self._queue_log(f"Could not finish the transcript for {source.name}: {exc}")

    def _report_results(self, plans, formats: list[str], started_at: float) -> None:
        done: list[Path] = []
        failed: list[Path] = []
        originals = {wrapper: source for source, wrapper in self._stand_ins.items()}
        for plan in plans:
            for source in plan.sources:
                shown = originals.get(source, source)
                (done if converted_ok(source, plan.output_dir, formats, started_at) else failed).append(shown)
        elapsed = time.time() - started_at
        minutes, seconds = divmod(int(elapsed), 60)
        took = f"{minutes} min {seconds} s" if minutes else f"{seconds} s"
        for source in done:
            self._queue_call(lambda s=source: self._results_set(s.name, "converted", tag="ok"))
        for source in failed:
            self._queue_call(lambda s=source: self._results_set(s.name, "failed", tag="bad"))
        self._last_report = (plans, formats, started_at, list(done), list(failed))
        self._queue_call(self._after_batch)
        if self._stop_requested:
            self._queue_log(f"Stopped. {len(done)} file(s) were finished before the stop, in {took}.")
            self._queue_call(lambda: self._set_status(f"Stopped after {len(done)} file(s)."))
            return
        for source in failed:
            self._queue_log(f"Failed: {source} (no complete output written)")
        if failed:
            self._queue_log(f"Batch completed in {took}: {len(done)} converted, {len(failed)} failed.")
            self._queue_call(lambda: self._set_status(f"Done: {len(done)} converted, {len(failed)} failed ({took})", 1.0))
        else:
            self._queue_log(f"Batch completed successfully: {len(done)} file(s) in {took}.")
            self._queue_call(lambda: self._set_status(f"Done: {len(done)} converted ({took})", 1.0))

    def _after_batch(self) -> None:
        """Buttons, notifications, and whatever is waiting its turn once the results are in."""
        self.report_button.configure(state="normal")
        if self._transcripts:
            self.speakers_button.grid()
        if self._last_report and self.notify_done_var.get() and time.time() - self._last_report[2] >= 30:
            _, _, _, done, failed = self._last_report
            windows.notify("Docling Launcher", "Batch finished: " + (f"{len(done)} converted, {len(failed)} failed." if failed else f"{len(done)} file(s) converted."))

    def _continue_after_batch(self) -> None:
        """Called by the pump the moment the batch's own end message arrives: no timer."""
        if self._queue_running:
            self._run_next_in_queue()
        elif self._watch_pending and self.watch_folder_var.get() and not self._stop_requested:
            self._watch_pending = False
            self._on_watch_fired()

    # ------------------------------------------------------------------ watching a folder

    def _sync_watcher(self) -> None:
        if self._watcher:
            self._watcher.stop()
            self._watcher = None
        folder = Path(self.input_folder_var.get().strip()) if self.input_folder_var.get().strip() else None
        if self.watch_folder_var.get() and folder and folder.is_dir():
            watcher = FolderWatcher(folder, lambda: self._post(self._on_watch_fired),
                                    wanted=lambda p: p.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS)
            if watcher.start():
                self._watcher = watcher
                self._append_log(f"Watching {folder} — new files will be converted as they arrive.")
                self._set_status("Watching the input folder.")
            else:
                self._append_log("Could not watch that folder.")
                self.watch_folder_var.set(False)
        elif self.watch_folder_var.get():
            self.watch_folder_var.set(False)
        self._save_settings()

    def _on_watch_fired(self) -> None:
        """Files arrived and the folder went quiet: convert what is new (already-converted
        files are skipped whatever the tick box says, so the batch is only the new ones)."""
        if not self.watch_folder_var.get():
            return
        if self.running:
            self._watch_pending = True
            return
        settings = self._settings_from_vars()
        settings.skip_converted = True
        self._batch_override = settings
        self.convert_all_files_var.set(True)
        self._append_log("New files in the watched folder — converting them.")
        self._on_run_clicked()

    # ------------------------------------------------------------------ the queue

    def _show_queue(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Queue")
        window.geometry("820x380")
        window.transient(self.root)
        window.grid_rowconfigure(0, weight=1)
        window.grid_columnconfigure(0, weight=1)
        tree = ttk.Treeview(window, columns=("input", "output", "mode", "preset"), show="headings")
        for column, title, width in (("input", "Input folder", 280), ("output", "Output folder", 260), ("mode", "Where", 90), ("preset", "Preset", 120)):
            tree.heading(column, text=title, anchor="w")
            tree.column(column, width=width, anchor="w", stretch=(column != "mode"))
        tree.grid(row=0, column=0, columnspan=5, sticky="nsew", padx=12, pady=12)

        def refresh() -> None:
            tree.delete(*tree.get_children())
            for entry in self.queue_entries:
                tree.insert("", "end", values=(entry.get("input", ""), entry.get("output", ""), entry.get("mode", ""), entry.get("preset", "")))

        def add_current() -> None:
            self.queue_entries.append({
                "input": self.input_folder_var.get().strip(), "output": self.output_folder_var.get().strip(),
                "mode": self.mode_var.get(), "preset": self.preset_var.get(),
            })
            self._save_settings()
            refresh()

        def remove() -> None:
            for item in tree.selection():
                index = tree.index(item)
                if 0 <= index < len(self.queue_entries):
                    del self.queue_entries[index]
            self._save_settings()
            refresh()

        def run_all() -> None:
            if not self.queue_entries or self.running:
                return
            window.destroy()
            self._queue_running = True
            self._append_log(f"Running the queue: {len(self.queue_entries)} folder(s).")
            self._run_next_in_queue()

        ttk.Button(window, text="Add current folders", command=add_current).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))
        ttk.Button(window, text="Remove selected", command=remove).grid(row=1, column=1, sticky="w", padx=(0, 12), pady=(0, 12))
        ttk.Button(window, text="Run queue", command=run_all, style="Accent.TButton").grid(row=1, column=4, sticky="e", padx=12, pady=(0, 12))
        refresh()

    def _run_next_in_queue(self) -> None:
        if not self.queue_entries:
            self._queue_running = False
            self._append_log("Queue finished.")
            self._save_settings()
            return
        entry = self.queue_entries.pop(0)
        self._save_settings()
        self.input_folder_var.set(entry.get("input", ""))
        self.output_folder_var.set(entry.get("output", ""))
        if entry.get("mode") in CONVERSION_MODES:
            self.mode_var.set(entry["mode"])
        if entry.get("preset"):
            self._apply_preset(entry["preset"])
        self.selected_input_files = []
        self.convert_all_files_var.set(True)
        self._sync_input_scope_state()
        self._append_log(f"Queue: {entry.get('input', '')}")
        before = self.running
        self._on_run_clicked()
        if not self.running and not before:
            # validation refused it; move on
            self._run_next_in_queue()

    # ------------------------------------------------------------------ the reference check

    def _on_reference_check_clicked(self) -> None:
        self._append_log("Reference check: converting the built-in reference documents.")
        version = next((s.installed for s in self.update_statuses if s.name == "docling"), None) or "?"

        def worker() -> None:
            self._run_reference_check(version)

        if not self._start_job("batch", worker):
            messagebox.showinfo(APP_NAME, "Wait for the current job to finish first.")

    def _run_reference_check(self, version: str) -> None:
        """Convert the reference set; compare with the baseline, or record one."""
        measured = safety.run_reference(self._queue_log, self.job, version)
        if measured is None:
            return
        baseline = dict(self.settings.reference_baseline)
        if not baseline:
            self.settings.reference_baseline = measured.to_dict()
            self._queue_call(self._save_settings)
            self._queue_log(f"Reference recorded: {measured.words} words, {measured.table_rows} table rows, "
                            f"scan read ({measured.scan_words} words), {measured.seconds:.0f} s with Docling {version}.")
            return
        fine, sentence = safety.compare(baseline, measured)
        self._queue_log(sentence)
        if fine:
            self.settings.reference_baseline = measured.to_dict()
            self._queue_call(self._save_settings)
        else:
            self._queue_call(lambda: messagebox.showwarning(APP_NAME, sentence))

    def _save_report(self) -> None:
        if not self._last_report:
            return
        plans, formats, started_at, done, failed = self._last_report
        stamp = datetime.fromtimestamp(started_at)
        folder = self._output_folder_for(Path(".")) or Path.home()
        target = filedialog.asksaveasfilename(
            title="Save the batch report", initialdir=str(folder), initialfile=f"Docling report {stamp:%Y-%m-%d %H%M}.md",
            defaultextension=".md", filetypes=[("Markdown", "*.md")],
        )
        if not target:
            return
        target = Path(target)
        lines = [f"# Docling batch — {stamp:%Y-%m-%d %H:%M}", "", "| File | Folder | Result | Time | Output |", "|---|---|---|---|---|"]
        rows = {self.results_tree.item(i, "values")[0]: self.results_tree.item(i, "values") for i in self.results_tree.get_children()}
        outputs = {}
        for plan in plans:
            for source in plan.sources:
                shown = self._shown_name(source.name if isinstance(source, Path) else str(source))
                outputs[shown] = plan.output_dir / f"{Path(shown).stem}.md"
        for name, (file, where, result, seconds) in rows.items():
            out = outputs.get(name)
            link = ""
            if out and out.exists():
                try:
                    link = f"[{out.name}]({os.path.relpath(out, target.parent).replace(os.sep, '/')})"
                except ValueError:
                    link = str(out)
            lines.append(f"| {file} | {where} | {result} | {seconds} | {link} |")
        try:
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._append_log(f"Report saved: {target}")
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Could not save the report: {exc}")

    def _name_speakers(self) -> None:
        """Speaker 1, Speaker 2 ... -> real names, in every transcript of the last batch."""
        transcripts = [path for path in self._transcripts if path.is_file()]
        if not transcripts:
            return
        found: list[str] = []
        for path in transcripts:
            for label in re.findall(r"\*\*(Speaker \d+)\*\*", path.read_text(encoding="utf-8")):
                if label not in found:
                    found.append(label)
        if not found:
            messagebox.showinfo(APP_NAME, "No speaker labels in the transcripts of this batch.")
            return
        window = tk.Toplevel(self.root)
        window.title("Name the speakers")
        window.transient(self.root)
        window.grid_columnconfigure(1, weight=1)
        ttk.Label(window, text=f"{len(transcripts)} transcript(s). Leave a name empty to keep the label.",
                  style="Hint.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 8))
        entries = {}
        for row, label in enumerate(sorted(found, key=lambda s: int(s.split()[1])), start=1):
            ttk.Label(window, text=label).grid(row=row, column=0, sticky="w", padx=(14, 10), pady=3)
            entry = ttk.Entry(window, width=32)
            entry.grid(row=row, column=1, sticky="ew", padx=(0, 14), pady=3)
            entries[label] = entry

        def apply() -> None:
            names = {label: entry.get().strip() for label, entry in entries.items() if entry.get().strip()}
            changed = self._apply_speaker_names(transcripts, names)
            self._append_log(f"Speakers named in {changed} transcript(s).")
            window.destroy()

        ttk.Button(window, text="Apply", command=apply, style="Accent.TButton").grid(row=len(found) + 1, column=1, sticky="e", padx=14, pady=(10, 12))

    @staticmethod
    def _apply_speaker_names(transcripts: list[Path], names: dict[str, str]) -> int:
        changed = 0
        for path in transcripts:
            text = path.read_text(encoding="utf-8")
            new = text
            for label, name in names.items():
                if name.strip():  # an empty name keeps the label
                    new = new.replace(f"**{label}**", f"**{name.strip()}**")
            if new != text:
                path.write_text(new, encoding="utf-8")
                changed += 1
        return changed

    def _convert_web_page(self) -> None:
        """A web address as the source: Docling reads the page; the result lands in the output folder."""
        if self.running:
            messagebox.showinfo(APP_NAME, "Wait for the current batch to finish first.")
            return
        address = simpledialog.askstring(APP_NAME, "Address of the web page:", parent=self.root)
        if not address or not address.strip().lower().startswith(("http://", "https://")):
            if address:
                messagebox.showerror(APP_NAME, "The address must start with http:// or https://")
            return
        address = address.strip()
        raw_output = self.output_folder_var.get().strip() or self.input_folder_var.get().strip()
        if not raw_output:
            messagebox.showerror(APP_NAME, "Choose an output folder first.")
            return
        formats = self._selected_formats() or ["md"]
        output = Path(raw_output)
        settings = self._settings_from_vars()
        self._save_settings()
        self._stop_requested = False
        self._set_status("Reading the web page…", 0.0)
        self._append_log(f"Converting web page {address}")

        def worker() -> None:
            windows.keep_awake(True)
            try:
                output.mkdir(parents=True, exist_ok=True)
                options = settings.conversion_options()
                options = options.__class__(**{**options.__dict__, "formats": tuple(formats)})
                from .docling_cli import build_command_plan
                plan = build_command_plan([address], output, options, ocr=False)
                started = time.time()
                self._queue_call(lambda: self._results_reset([Path(address)], output))
                code = stream_process(plan.command, plan.env, self._batch_log, job=self.job, cwd=output,
                                      tidy=tidy_docling_line, cancelled=lambda: self._stop_requested)
                written = sorted(p for p in output.iterdir() if p.is_file() and p.stat().st_mtime >= started - 1)
                if code == 0 and written:
                    self._queue_log("Written: " + ", ".join(p.name for p in written))
                    self._queue_call(lambda: (self._results_set(Path(address).name, "converted", f"{time.time() - started:.0f} s", "ok"),
                                              self._set_status(f"Web page converted: {written[0].name}", 1.0)))
                else:
                    self._queue_log(f"The web page could not be converted (exit code {code}).")
                    self._queue_call(lambda: (self._results_set(Path(address).name, "failed", tag="bad"), self._set_status("Web page failed.", 1.0)))
            finally:
                windows.keep_awake(False)

        self._start_job("batch", worker)

    # ------------------------------------------------------------------ help and exit

    def _show_input_formats(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("What Docling can read")
        window.geometry("780x470")
        window.minsize(560, 320)
        window.transient(self.root)
        window.grid_rowconfigure(0, weight=1)
        window.grid_columnconfigure(0, weight=1)
        tree = ttk.Treeview(window, columns=("kind", "types", "note"), show="headings")
        for column, title, width in (("kind", "Kind", 150), ("types", "File types", 300), ("note", "Note", 290)):
            tree.heading(column, text=title, anchor="w")
            tree.column(column, width=width, anchor="w", stretch=(column == "note"))
        for kind, types, note in INPUT_FORMAT_GROUPS:
            tree.insert("", "end", values=(kind, types, note))
        tree.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        ttk.Label(window, wraplength=720, style="Hint.TLabel",
                  text="Every one of these can be dropped into the input folder or onto the window; the launcher picks "
                       "them up by their file ending. Anything else is left alone.").grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))

    def _show_how_to_use(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("How to use Docling Launcher")
        window.geometry("780x660")
        window.minsize(560, 420)
        window.transient(self.root)
        bg, fg = self._palette()
        text = scrolledtext.ScrolledText(window, wrap="word", padx=18, pady=14, font=("Segoe UI", 10),
                                         background=bg, foreground=fg, relief="flat", borderwidth=0)
        text.pack(fill="both", expand=True)
        text.tag_configure("h1", font=("Segoe UI Semibold", 15), spacing1=6, spacing3=6)
        text.tag_configure("h2", font=("Segoe UI Semibold", 11), spacing1=12, spacing3=4)
        text.tag_configure("p", spacing3=6)
        text.tag_configure("li", lmargin1=18, lmargin2=34, spacing3=3)
        for kind, line in HOW_TO_USE:
            text.insert("end", line + "\n", kind)
        text.configure(state="disabled")

    def _on_close(self) -> None:
        if "update" in self.active_jobs or "restore" in self.active_jobs:
            if not messagebox.askyesno(APP_NAME, "An update is in progress. Closing now can leave Docling half-installed (Go back can repair it next time). Close anyway?"):
                return
        elif self.running:
            if not messagebox.askyesno(APP_NAME, "A batch is still running. Closing stops Docling. Close anyway?"):
                return
        if self._watcher:
            self._watcher.stop()
        if not getattr(self, "_selftest", False):  # a proof run never writes the real settings
            self._save_settings()
        self.job.terminate()
        self.job.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    selftest = os.environ.get("DOCLING_LAUNCHER_SELFTEST")
    if selftest:
        # Proof that the BUILT exe works, without showing anything: withdraw the window,
        # let the start-up update check run, write what the header would say, and quit.
        root.withdraw()
    icon = asset_path("docling_launcher.ico")
    if icon.exists():
        try:
            root.iconbitmap(default=str(icon))
        except tk.TclError:
            pass
    app = DoclingLauncherApp(root)
    root.protocol("WM_DELETE_WINDOW", app._on_close)
    # Explorer's "Convert with Docling" starts the launcher with the folder as its argument.
    given = [Path(arg) for arg in sys.argv[1:] if not arg.startswith("-")]
    if given and given[0].exists():
        app._on_drop(given[:1])
    if selftest:
        app._selftest = True

        def report() -> None:
            import json
            Path(selftest).write_text(json.dumps({
                "app": APP_VERSION,
                "frozen": bool(getattr(sys, "frozen", False)),
                "icon_found": icon.exists(),
                "tools_found": {name: asset_path(name).exists() for name in ("models_tool.py", "media_tool.py", "convert_tool.py", "speakers_tool.py")},
                "themed": app.themed,
                "models_checked": len(app.model_statuses),
                "docling": app.docling_version_var.get(),
                "update_status": app.update_status_var.get(),
                "launcher_note": app.launcher_release_note,
                "update_button_shown": bool(app.update_button and app.update_button.winfo_manager()),
                "docling_exe": str(resolve_docling()),
                "log": app.log_text.get("1.0", "end").strip(),
            }, indent=2), encoding="utf-8")
            app._on_close()
        root.after(8000, report)
    root.mainloop()
