from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Callable

from .admin import is_user_admin, run_elevated_batch
from .constants import (
    APP_NAME,
    APP_VERSION,
    CONVERSION_MODES,
    MEDIA_INPUT_EXTENSIONS,
    OCR_ENGINES,
    OUTPUT_FORMATS,
    SUPPORTED_INPUT_EXTENSIONS,
    TOOLTIP_TEXT,
)
from .docling_cli import (
    ProcessJob,
    build_batch_plans,
    build_preview,
    converted_ok,
    discover_input_files,
    environment_for_run,
    resolve_docling,
    stream_process,
    tidy_docling_line,
)
from .environment import check_all_dependencies, speech_available
from .settings import LauncherSettings
from . import updates


# Jobs that may not overlap: each one owns Docling's environment while it runs.
HEAVY_JOBS = {"batch", "update", "restore"}


def asset_path(name: str) -> Path:
    """A file shipped inside the exe (PyInstaller unpacks to _MEIPASS) or beside the source."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "docling_launcher" / "assets" / name
    return Path(__file__).resolve().parent / "assets" / name


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
        label = ttk.Label(
            self.tip_window,
            text=self.text,
            padding=(8, 5),
            relief="solid",
            borderwidth=1,
            background="#fff8dc",
            wraplength=360,
        )
        label.pack()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def _on_content_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _on_mousewheel(self, event) -> None:
        # Only when the wheel turns OVER this area. A wheel over the log used to scroll
        # the log and these settings at the same time.
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
        self.root.geometry("1080x860")
        self.root.minsize(900, 650)

        self.settings = LauncherSettings.load()
        self.log_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        # Every Docling and pip process the launcher starts lives in this job, so Stop and
        # Exit end them all, and nothing outlives the window.
        self.job = ProcessJob()
        self.active_jobs: set[str] = set()
        self._pumping = False
        self._stop_requested = False
        self.update_statuses: list[updates.PackageStatus] = []

        self.input_folder_var = tk.StringVar(value=self.settings.input_folder)
        self.output_folder_var = tk.StringVar(value=self.settings.output_folder)
        self.convert_all_files_var = tk.BooleanVar(value=self.settings.convert_all_files)
        self.selected_input_files = [
            Path(path) for path in self.settings.selected_input_files
        ]
        self.selected_files_summary_var = tk.StringVar()
        self.mode_var = tk.StringVar(value=self.settings.conversion_mode)
        self.use_ocr_var = tk.BooleanVar(value=self.settings.use_ocr)
        self.ocr_engine_var = tk.StringVar(value=self.settings.ocr_engine)
        self.allow_plugins_var = tk.BooleanVar(value=self.settings.allow_external_plugins)
        self.portable_tesseract_var = tk.BooleanVar(
            value=self.settings.portable_tesseract_enabled
        )
        self.portable_tesseract_path_var = tk.StringVar(
            value=self.settings.portable_tesseract_path
        )
        self.run_as_admin_var = tk.BooleanVar(value=self.settings.run_as_admin)
        self.show_tooltips_var = tk.BooleanVar(value=self.settings.show_tooltips)
        self.command_preview_var = tk.StringVar()
        self.docling_version_var = tk.StringVar(value="Docling")
        self.update_status_var = tk.StringVar(value="")
        self.format_vars = {
            value: tk.BooleanVar(value=value in self.settings.output_formats)
            for _, value in OUTPUT_FORMATS
        }

        self.status_tree: ttk.Treeview | None = None
        self.updates_tree: ttk.Treeview | None = None
        self.run_button: ttk.Button | None = None
        self.stop_button: ttk.Button | None = None
        self.update_button: ttk.Button | None = None
        self.check_updates_button: ttk.Button | None = None
        self.go_back_button: ttk.Button | None = None
        self.select_files_button: ttk.Button | None = None
        self.tesseract_widgets: list[tk.Widget] = []
        self.ocr_dependent_widgets: list[tk.Widget] = []  # shown only while OCR is on

        self._configure_style()
        self._build_ui()
        self._bind_var_changes()
        self._update_preview()
        self._sync_input_scope_state()
        self._sync_tesseract_state()
        self._sync_ocr_state()
        self._show_installed_versions()
        self._append_log("Ready.")
        # One quiet look for a newer Docling, after the first frame is on screen.
        self.root.after(400, lambda: self._check_updates(quiet=True))

    def _configure_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Version.TLabel", font=("Segoe UI", 10))
        style.configure("Available.TLabel", font=("Segoe UI", 10, "bold"), foreground="#177245")
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("StatusOk.TLabel", foreground="#177245")
        style.configure("StatusBad.TLabel", foreground="#a4262c")

    def _build_ui(self) -> None:
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self._build_header()

        scroller = ScrollableFrame(self.root)
        scroller.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        scroller.content.grid_columnconfigure(0, weight=1)

        self._build_io_section(scroller.content)
        self._build_mode_section(scroller.content)
        self._build_formats_section(scroller.content)
        self._build_ocr_section(scroller.content)
        self._build_tesseract_section(scroller.content)
        self._build_status_section(scroller.content)
        self._build_run_section(scroller.content)
        self._build_updates_section(scroller.content)
        self._build_log_section()

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, padding=(12, 12, 12, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ttk.Label(header, text=APP_NAME, style="Header.TLabel").grid(row=0, column=0, sticky="w")

        tools = ttk.Frame(header)
        tools.grid(row=0, column=1, sticky="e")
        how_button = ttk.Button(tools, text="How to Use", command=self._show_how_to_use)
        how_button.grid(row=0, column=0, padx=(0, 10))
        tips = ttk.Checkbutton(
            tools,
            text="Show tooltips",
            variable=self.show_tooltips_var,
            command=self._save_settings,
        )
        tips.grid(row=0, column=1)

        # The version line: what is installed, and — only when there is one — the newer
        # version with the button that installs it.
        version_row = ttk.Frame(header)
        version_row.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(version_row, textvariable=self.docling_version_var, style="Version.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(version_row, textvariable=self.update_status_var, style="Available.TLabel").grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )
        self.update_button = ttk.Button(version_row, text="Update", command=self._on_update_clicked)
        self.update_button.grid(row=0, column=2, padx=(12, 0))
        self.update_button.grid_remove()
        self._tooltip(self.update_button, TOOLTIP_TEXT["update"])

    def _section(self, parent, title: str, row: int) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title, padding=10, style="Section.TLabelframe")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        frame.grid_columnconfigure(0, weight=1)
        return frame

    def _build_updates_section(self, parent) -> None:
        section = self._section(parent, "Updates", 7)
        self.updates_tree = ttk.Treeview(
            section,
            columns=("component", "installed", "latest", "status"),
            show="headings",
            height=3,
        )
        for column, title, width in (
            ("component", "Component", 180),
            ("installed", "Installed", 110),
            ("latest", "Latest", 110),
            ("status", "Status", 200),
        ):
            self.updates_tree.heading(column, text=title, anchor="w")
            self.updates_tree.column(column, width=width, anchor="w", stretch=(column == "status"))
        self.updates_tree.grid(row=0, column=0, sticky="ew")
        self.updates_tree.tag_configure("update", foreground="#177245")
        self.updates_tree.tag_configure("unknown", foreground="#6d6d6d")

        buttons = ttk.Frame(section)
        buttons.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.check_updates_button = ttk.Button(
            buttons, text="Check now", command=lambda: self._check_updates(quiet=False)
        )
        self.check_updates_button.grid(row=0, column=0, padx=(0, 8))
        self._tooltip(self.check_updates_button, TOOLTIP_TEXT["check_updates"])
        self.go_back_button = ttk.Button(buttons, text="Go back", command=self._on_go_back_clicked)
        self.go_back_button.grid(row=0, column=1)
        self.go_back_button.grid_remove()
        self._tooltip(self.go_back_button, TOOLTIP_TEXT["go_back"])

    def _build_io_section(self, parent) -> None:
        section = self._section(parent, "Input / Output", 0)
        section.grid_columnconfigure(1, weight=1)

        ttk.Label(section, text="Input folder").grid(row=0, column=0, sticky="w", padx=(0, 8))
        input_entry = ttk.Entry(section, textvariable=self.input_folder_var)
        input_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        input_button = ttk.Button(
            section,
            text="Browse",
            command=lambda: self._browse_folder(self.input_folder_var),
        )
        input_button.grid(row=0, column=2)

        scope_check = ttk.Checkbutton(
            section,
            text="Convert every supported file in this folder",
            variable=self.convert_all_files_var,
            command=self._sync_input_scope_state,
        )
        scope_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.select_files_button = ttk.Button(
            section,
            text="Select Files...",
            command=self._select_input_files,
        )
        self.select_files_button.grid(row=1, column=2, sticky="e", pady=(8, 0))
        ttk.Label(section, textvariable=self.selected_files_summary_var).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )

        ttk.Label(section, text="Output folder").grid(
            row=3, column=0, sticky="w", padx=(0, 8), pady=(8, 0)
        )
        output_entry = ttk.Entry(section, textvariable=self.output_folder_var)
        output_entry.grid(row=3, column=1, sticky="ew", padx=(0, 8), pady=(8, 0))
        output_button = ttk.Button(
            section,
            text="Browse",
            command=lambda: self._browse_folder(self.output_folder_var),
        )
        output_button.grid(row=3, column=2, pady=(8, 0))

        self._tooltip(input_entry, TOOLTIP_TEXT["input_folder"])
        self._tooltip(input_button, TOOLTIP_TEXT["input_folder"])
        self._tooltip(scope_check, TOOLTIP_TEXT["input_scope"])
        self._tooltip(self.select_files_button, TOOLTIP_TEXT["selected_files"])
        self._tooltip(output_entry, TOOLTIP_TEXT["output_folder"])
        self._tooltip(output_button, TOOLTIP_TEXT["output_folder"])

    def _build_mode_section(self, parent) -> None:
        section = self._section(parent, "Conversion Mode", 1)
        for index, (value, label) in enumerate(CONVERSION_MODES.items()):
            button = ttk.Radiobutton(section, text=label, value=value, variable=self.mode_var)
            button.grid(row=index, column=0, sticky="w", pady=2)
            self._tooltip(button, TOOLTIP_TEXT[f"mode_{value}"])

    def _build_formats_section(self, parent) -> None:
        section = self._section(parent, "Output Formats", 2)
        for index, (label, value) in enumerate(OUTPUT_FORMATS):
            button = ttk.Checkbutton(section, text=label, variable=self.format_vars[value])
            button.grid(row=index // 4, column=index % 4, sticky="w", padx=(0, 24), pady=3)
            self._tooltip(button, TOOLTIP_TEXT["formats"])

    def _build_ocr_section(self, parent) -> None:
        section = self._section(parent, "OCR and Plugins", 3)
        section.grid_columnconfigure(1, weight=1)
        use_ocr = ttk.Checkbutton(
            section,
            text="Read text in pictures and scans (OCR)",
            variable=self.use_ocr_var,
            command=self._sync_ocr_state,
        )
        use_ocr.grid(row=0, column=0, columnspan=2, sticky="w")
        engine_label = ttk.Label(section, text="OCR engine")
        engine_label.grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        combo = ttk.Combobox(
            section,
            textvariable=self.ocr_engine_var,
            values=OCR_ENGINES,
            state="readonly",
            width=28,
        )
        combo.grid(row=1, column=1, sticky="w", pady=(8, 0))
        plugin_check = ttk.Checkbutton(
            section,
            text="Allow external plugins",
            variable=self.allow_plugins_var,
        )
        plugin_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.ocr_dependent_widgets.extend([engine_label, combo])
        self._tooltip(use_ocr, TOOLTIP_TEXT["use_ocr"])
        self._tooltip(combo, TOOLTIP_TEXT["ocr_engine"])
        self._tooltip(plugin_check, TOOLTIP_TEXT["plugins"])

    def _build_tesseract_section(self, parent) -> None:
        section = self._section(parent, "Portable Tesseract", 4)
        section.grid_columnconfigure(1, weight=1)
        self.ocr_dependent_widgets.append(section)
        enabled = ttk.Checkbutton(
            section,
            text="Use portable Tesseract",
            variable=self.portable_tesseract_var,
            command=self._sync_tesseract_state,
        )
        enabled.grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(section, text="Tesseract folder").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0)
        )
        path_entry = ttk.Entry(section, textvariable=self.portable_tesseract_path_var)
        path_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(8, 0))
        browse = ttk.Button(
            section,
            text="Browse",
            command=lambda: self._browse_folder(self.portable_tesseract_path_var),
        )
        browse.grid(row=1, column=2, pady=(8, 0))

        self.tesseract_widgets = [path_entry, browse]
        self._tooltip(enabled, TOOLTIP_TEXT["portable_tesseract"])
        self._tooltip(path_entry, TOOLTIP_TEXT["portable_tesseract_path"])
        self._tooltip(browse, TOOLTIP_TEXT["portable_tesseract_path"])

    def _build_status_section(self, parent) -> None:
        section = self._section(parent, "Extension Status", 5)
        self.status_tree = ttk.Treeview(
            section,
            columns=("component", "status", "detail"),
            show="headings",
            height=5,
        )
        self.status_tree.heading("component", text="Component", anchor="w")
        self.status_tree.heading("status", text="Status", anchor="w")
        self.status_tree.heading("detail", text="Detail", anchor="w")
        self.status_tree.column("component", width=150, anchor="w")
        self.status_tree.column("status", width=90, anchor="w")
        self.status_tree.column("detail", width=600, anchor="w")
        self.status_tree.grid(row=0, column=0, sticky="ew")
        self.status_tree.tag_configure("ok", foreground="#177245")
        self.status_tree.tag_configure("bad", foreground="#a4262c")
        for name in ["Docling CLI", "RapidOCR", "EasyOCR", "Tesseract", "OnnxTR"]:
            self.status_tree.insert("", "end", values=(name, "Unknown", "Not checked yet"))

    def _build_run_section(self, parent) -> None:
        section = self._section(parent, "Run", 6)
        section.grid_columnconfigure(0, weight=1)

        command_entry = ttk.Entry(
            section,
            textvariable=self.command_preview_var,
            state="readonly",
        )
        command_entry.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 8))
        self._tooltip(command_entry, TOOLTIP_TEXT["command_preview"])

        self.run_button = ttk.Button(
            section,
            text="Run Batch Conversion",
            command=self._on_run_clicked,
        )
        self.run_button.grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.stop_button = ttk.Button(section, text="Stop", command=self._on_stop_clicked)
        self.stop_button.grid(row=1, column=1, sticky="w", padx=(0, 8))
        self.stop_button.grid_remove()
        self._tooltip(self.stop_button, TOOLTIP_TEXT["stop"])
        ttk.Button(section, text="Check Extensions", command=self._check_extensions).grid(
            row=1, column=2, sticky="w", padx=(0, 8)
        )
        ttk.Button(section, text="Exit", command=self._on_close).grid(
            row=1, column=3, sticky="w", padx=(0, 16)
        )
        admin_check = ttk.Checkbutton(
            section,
            text="Run as Administrator",
            variable=self.run_as_admin_var,
        )
        admin_check.grid(row=1, column=4, sticky="w")
        self._tooltip(admin_check, TOOLTIP_TEXT["run_admin"])

    def _build_log_section(self) -> None:
        section = ttk.LabelFrame(self.root, text="Log", padding=10, style="Section.TLabelframe")
        section.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        section.grid_rowconfigure(0, weight=1)
        section.grid_columnconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(
            section,
            height=11,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

    def _tooltip(self, widget: tk.Widget, text: str) -> None:
        ToolTip(widget, text, lambda: self.show_tooltips_var.get())

    def _bind_var_changes(self) -> None:
        variables = [
            self.input_folder_var,
            self.output_folder_var,
            self.convert_all_files_var,
            self.mode_var,
            self.use_ocr_var,
            self.ocr_engine_var,
            self.allow_plugins_var,
            self.portable_tesseract_var,
            self.portable_tesseract_path_var,
            self.run_as_admin_var,
            self.show_tooltips_var,
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
            use_ocr=self.use_ocr_var.get(),
            ocr_engine=self.ocr_engine_var.get(),
            allow_external_plugins=self.allow_plugins_var.get(),
            portable_tesseract_enabled=self.portable_tesseract_var.get(),
            portable_tesseract_path=self.portable_tesseract_path_var.get().strip(),
            run_as_admin=self.run_as_admin_var.get(),
            show_tooltips=self.show_tooltips_var.get(),
        )

    def _save_settings(self) -> None:
        self.settings = self._settings_from_vars()
        self.settings.save()

    def _update_preview(self) -> None:
        formats = self._selected_formats()
        selected_source = (
            self.selected_input_files[0]
            if not self.convert_all_files_var.get() and self.selected_input_files
            else None
        )
        try:
            preview = build_preview(
                self.input_folder_var.get().strip(),
                self.output_folder_var.get().strip(),
                self.mode_var.get(),
                formats,
                self.ocr_engine_var.get(),
                self.allow_plugins_var.get(),
                self.portable_tesseract_var.get(),
                self.portable_tesseract_path_var.get(),
                source_path=selected_source,
                use_ocr=self.use_ocr_var.get(),
            )
        except Exception as exc:
            preview = f"Unable to build preview: {exc}"
        self.command_preview_var.set(preview)

    def _sync_ocr_state(self) -> None:
        """With OCR off, an engine or a Tesseract folder changes nothing - so they are not
        shown. Their values survive hidden and come back the moment OCR is on again."""
        for widget in self.ocr_dependent_widgets:
            if self.use_ocr_var.get():
                widget.grid()
            else:
                widget.grid_remove()
        self._update_preview()

    def _sync_tesseract_state(self) -> None:
        state = "normal" if self.portable_tesseract_var.get() else "disabled"
        for widget in self.tesseract_widgets:
            widget.configure(state=state)
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

    def _sync_input_scope_state(self) -> None:
        selecting_files = not self.convert_all_files_var.get()
        if self.select_files_button:
            self.select_files_button.configure(state="normal" if selecting_files else "disabled")
        if selecting_files:
            count = len(self.selected_input_files)
            self.selected_files_summary_var.set(
                "No files selected." if not count else f"{count} file(s) selected for conversion."
            )
        else:
            self.selected_files_summary_var.set(
                "All supported files in this folder and its subfolders will be converted."
            )
        if self.run_button:
            self.run_button.configure(
                text="Run Selected Files" if selecting_files else "Run Batch Conversion"
            )
        self._update_preview()

    def _select_input_files(self) -> None:
        raw_input_folder = self.input_folder_var.get().strip()
        input_folder = Path(raw_input_folder)
        if not raw_input_folder or not input_folder.is_dir():
            messagebox.showerror(APP_NAME, "Choose a valid input folder before selecting files.")
            return

        patterns = " ".join(f"*{extension}" for extension in sorted(SUPPORTED_INPUT_EXTENSIONS))
        selected = filedialog.askopenfilenames(
            title="Select files to convert",
            initialdir=str(input_folder),
            filetypes=[("Supported documents", patterns), ("All files", "*.*")],
        )
        if not selected:
            return

        valid_files: list[Path] = []
        rejected = 0
        input_root = input_folder.resolve()
        for raw_path in selected:
            path = Path(raw_path)
            try:
                path.resolve().relative_to(input_root)
            except ValueError:
                rejected += 1
                continue
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
                rejected += 1
                continue
            valid_files.append(path)

        self.selected_input_files = sorted(
            {path.resolve() for path in valid_files}, key=lambda path: str(path).lower()
        )
        self._sync_input_scope_state()
        self._save_settings()
        if rejected:
            messagebox.showwarning(
                APP_NAME,
                f"Ignored {rejected} file(s). Selected files must be supported and inside the input folder.",
            )

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

        Heavy jobs (a batch, an update, a restore) own Docling's environment and refuse to
        overlap. Light ones (a version check, the extension check) just need the pump."""
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
        for button in (self.update_button, self.check_updates_button, self.go_back_button):
            if button:
                button.configure(state="disabled" if busy or checking else "normal")

    # ------------------------------------------------------------------ extension status

    def _apply_statuses(self, statuses) -> None:
        if not self.status_tree:
            return
        self.status_tree.delete(*self.status_tree.get_children())
        for status in statuses:
            tag = "ok" if status.ok else "bad"
            value = "OK" if status.ok else "Missing"
            self.status_tree.insert(
                "",
                "end",
                values=(status.name, value, status.detail),
                tags=(tag,),
            )

    def _check_extensions(self) -> None:
        self._append_log("Checking extension status.")
        env = environment_for_run(
            self.portable_tesseract_var.get(),
            self.portable_tesseract_path_var.get(),
            use_launcher_temp=False,
        )

        def worker() -> None:
            statuses = check_all_dependencies(env)
            self._queue_call(lambda: self._apply_statuses(statuses))
            for status in statuses:
                state = "OK" if status.ok else "Missing"
                self._queue_log(f"{status.name}: {state} - {status.detail}")

        self._start_job("extensions", worker)

    # ------------------------------------------------------------------ updates

    def _show_installed_versions(self) -> None:
        """Instant: read from Docling's environment, no network, no process."""
        statuses = updates.check_updates(online=False)
        self._apply_update_statuses(statuses, quiet=True)

    def _apply_update_statuses(self, statuses: list[updates.PackageStatus], quiet: bool) -> None:
        self.update_statuses = statuses
        docling = next((s for s in statuses if s.name == "docling"), None)
        if docling and docling.installed:
            self.docling_version_var.set(f"Docling {docling.installed}")
        else:
            self.docling_version_var.set("Docling not found")

        available = updates.upgrade_targets(statuses)
        if docling and docling.update_available:
            self.update_status_var.set(f"{docling.latest} available")
        elif available:
            self.update_status_var.set(f"{len(available)} add-in update(s) available")
        elif quiet:
            self.update_status_var.set("")
        elif docling and docling.latest:
            self.update_status_var.set("up to date")
        else:
            self.update_status_var.set("")
        if self.update_button:
            if available:
                self.update_button.grid()
            else:
                self.update_button.grid_remove()

        if self.updates_tree:
            self.updates_tree.delete(*self.updates_tree.get_children())
            for status in statuses:
                if status.latest is None:
                    latest, state, tag = "—", ("Not checked" if quiet else "Could not check"), "unknown"
                else:
                    latest, state = status.latest, status.state
                    tag = "update" if status.update_available else ""
                self.updates_tree.insert(
                    "", "end",
                    values=(status.label, status.installed or "—", latest, state),
                    tags=(tag,) if tag else (),
                )
            self.updates_tree.configure(height=max(3, len(statuses)))

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
            self._append_log("Checking for Docling updates.")
            self.update_status_var.set("checking…")

        def worker() -> None:
            statuses = updates.check_updates(online=True)
            self._queue_call(lambda: self._apply_update_statuses(statuses, quiet=quiet))
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
            if not updates.upgrade_targets(statuses):
                self._queue_log("Everything is up to date.")

        self._start_job("check", worker)

    def _on_update_clicked(self) -> None:
        targets = updates.upgrade_targets(self.update_statuses)
        if not targets:
            return
        before = {status.name: status.installed for status in self.update_statuses}
        labels = ", ".join(status.label for status in self.update_statuses if status.update_available)

        def worker() -> None:
            self._queue_log(f"Updating {labels}. This can take a few minutes.")
            snapshot = updates.take_snapshot()
            if snapshot:
                self._queue_log(f"Restore point saved: {snapshot.name}")
            else:
                self._queue_log("Warning: could not save a restore point; continuing without one.")
            code = updates.run_upgrade(targets, self._queue_log, job=self.job)
            statuses = updates.check_updates(online=False)
            self._queue_call(lambda: self._apply_update_statuses(statuses, quiet=True))
            changed = [
                f"{s.label} {before.get(s.name)} -> {s.installed}"
                for s in statuses
                if s.installed and before.get(s.name) and s.installed != before.get(s.name)
            ]
            if code == 0:
                self._queue_log("Update finished: " + (", ".join(changed) if changed else "nothing changed."))
            else:
                self._queue_log(
                    f"Update failed (exit code {code}). Your previous versions are safe: "
                    "use 'Go back' if Docling misbehaves."
                )
            self._queue_call(lambda: self._check_updates(quiet=True))

        if not self._start_job("update", worker):
            messagebox.showinfo(APP_NAME, "Wait for the current job to finish first.")

    def _on_go_back_clicked(self) -> None:
        point = updates.restore_point()
        if not point:
            return
        snapshot, version = point
        if not messagebox.askyesno(
            APP_NAME,
            f"Reinstall the versions saved on {updates.snapshot_label(snapshot)} (Docling {version})?",
        ):
            return

        def worker() -> None:
            self._queue_log(f"Going back to Docling {version}.")
            code = updates.run_restore(snapshot, self._queue_log, job=self.job)
            statuses = updates.check_updates(online=False)
            self._queue_call(lambda: self._apply_update_statuses(statuses, quiet=True))
            docling = next((s.installed for s in statuses if s.name == "docling"), None)
            if code == 0:
                self._queue_log(f"Restored. Docling is now {docling}.")
            else:
                self._queue_log(f"Restore failed (exit code {code}). Docling is {docling}.")
            self._queue_call(lambda: self._check_updates(quiet=True))

        if not self._start_job("restore", worker):
            messagebox.showinfo(APP_NAME, "Wait for the current job to finish first.")

    # ------------------------------------------------------------------ batch conversion

    def _validated_selected_files(self, input_folder: Path) -> list[Path]:
        if not self.selected_input_files:
            raise ValueError("Select one or more files to convert.")

        input_root = input_folder.resolve()
        files: list[Path] = []
        invalid_files: list[Path] = []
        for path in self.selected_input_files:
            resolved = path.resolve()
            try:
                resolved.relative_to(input_root)
            except ValueError:
                invalid_files.append(path)
                continue
            if not resolved.is_file() or resolved.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
                invalid_files.append(path)
                continue
            files.append(resolved)

        if invalid_files:
            raise ValueError(
                "Some selected files are no longer available, unsupported, or outside the input folder. "
                "Select the files again."
            )
        return sorted(set(files), key=lambda path: str(path).lower())

    def _validate(self) -> tuple[Path, Path | None, list[str], list[Path] | None]:
        input_folder = Path(self.input_folder_var.get().strip())
        if not input_folder.exists() or not input_folder.is_dir():
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

        if self.use_ocr_var.get() and self.portable_tesseract_var.get():
            raw_tesseract = self.portable_tesseract_path_var.get().strip()
            if not raw_tesseract or not Path(raw_tesseract).exists():
                raise ValueError("Choose a valid portable Tesseract folder.")

        if not resolve_docling():
            raise ValueError(
                "docling.exe was not found. Put it in .venv\\Scripts, next to the app, or on PATH."
            )

        selected_files = (
            None
            if self.convert_all_files_var.get()
            else self._validated_selected_files(input_folder)
        )
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
        if selected_files is None:
            self._append_log("Starting batch conversion.")
        else:
            self._append_log(f"Starting conversion of {len(selected_files)} selected file(s).")

        settings = self._settings_from_vars()
        self._start_job(
            "batch",
            lambda: self._run_batch(input_folder, output_folder, formats, selected_files, settings),
        )

    def _on_stop_clicked(self) -> None:
        if "batch" not in self.active_jobs or self._stop_requested:
            return
        self._stop_requested = True
        self._append_log("Stopping — Docling is being closed.")
        self._sync_buttons()
        self.job.terminate()

    def _run_batch(
        self,
        input_folder: Path,
        output_folder: Path | None,
        formats: list[str],
        selected_files: list[Path] | None,
        settings: LauncherSettings,
    ) -> None:
        if selected_files is None:
            files = discover_input_files(input_folder)
            self._queue_log(f"Discovered {len(files)} supported input file(s).")
        else:
            files = selected_files
            self._queue_log(f"Using {len(files)} selected input file(s).")

        media = [path for path in files if path.suffix.lower() in MEDIA_INPUT_EXTENSIONS]
        if media and not speech_available():
            self._queue_log(
                f"Skipped {len(media)} sound/video file(s): Docling's speech library (Whisper) "
                "is not installed in this environment."
            )
            files = [path for path in files if path not in media]
        if not files:
            self._queue_log("No supported files were found or selected.")
            return

        stem_counts: dict[str, int] = {}
        for source in files:
            stem_counts[source.stem.lower()] = stem_counts.get(source.stem.lower(), 0) + 1
        if settings.conversion_mode == "flat":
            duplicates = sorted(stem for stem, count in stem_counts.items() if count > 1)
            if duplicates:
                self._queue_log(
                    "Warning: duplicate file names in single-folder mode may overwrite outputs: "
                    + ", ".join(duplicates[:20])
                )

        plans = build_batch_plans(
            files,
            input_folder,
            output_folder or input_folder,
            settings.conversion_mode,
            formats,
            settings.ocr_engine,
            settings.allow_external_plugins,
            settings.portable_tesseract_enabled,
            settings.portable_tesseract_path,
            use_ocr=settings.use_ocr,
        )
        for plan in plans:
            plan.output_dir.mkdir(parents=True, exist_ok=True)
        self._queue_log(
            f"{len(files)} file(s) in {len(plans)} Docling run(s) — one per output folder."
        )

        started_at = time.time()
        if settings.run_as_admin and not is_user_admin():
            exit_code = run_elevated_batch(plans, self._queue_log)
            self._queue_log(f"Elevated batch exited with code {exit_code}.")
            self._report_results(plans, formats, started_at)
            return

        for index, plan in enumerate(plans, start=1):
            if self._stop_requested:
                break
            self._queue_log(f"[{index}/{len(plans)}] {len(plan.sources)} file(s) -> {plan.output_dir}")
            exit_code = stream_process(
                plan.command,
                plan.env,
                self._queue_log,
                job=self.job,
                cwd=plan.output_dir,
                tidy=tidy_docling_line,
                cancelled=lambda: self._stop_requested,
            )
            if self._stop_requested:
                break
            if exit_code != 0:
                self._queue_log(f"Docling exited with code {exit_code}.")
        self._report_results(plans, formats, started_at)

    def _report_results(self, plans, formats: list[str], started_at: float) -> None:
        done: list[Path] = []
        failed: list[Path] = []
        for plan in plans:
            for source in plan.sources:
                (done if converted_ok(source, plan.output_dir, formats, started_at) else failed).append(source)
        elapsed = time.time() - started_at
        minutes, seconds = divmod(int(elapsed), 60)
        took = f"{minutes} min {seconds} s" if minutes else f"{seconds} s"
        if self._stop_requested:
            self._queue_log(f"Stopped. {len(done)} file(s) were finished before the stop, in {took}.")
            return
        for source in failed:
            self._queue_log(f"Failed: {source} (no complete output written)")
        if failed:
            self._queue_log(
                f"Batch completed in {took}: {len(done)} converted, {len(failed)} failed."
            )
        else:
            self._queue_log(f"Batch completed successfully: {len(done)} file(s) in {took}.")

    # ------------------------------------------------------------------ help and exit

    def _show_how_to_use(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("How to Use Docling Launcher")
        window.geometry("680x560")
        window.minsize(560, 420)
        window.transient(self.root)

        text = scrolledtext.ScrolledText(window, wrap="word", padx=14, pady=14)
        text.pack(fill="both", expand=True)
        guide = """1. Choose the input folder that contains the documents you want to convert.

2. Leave Convert every supported file in this folder checked to process the whole folder and its subfolders. Clear it, click Select Files, and choose one or more files when you only want a subset.

3. Choose an output folder unless you are saving converted files beside the originals.

4. Pick a conversion mode:
   - Mirror keeps the same subfolder structure under the output folder.
   - Beside writes output next to each original file.
   - Single folder writes every converted file into one output folder.

5. Select one or more output formats.

6. Leave Read text in pictures and scans (OCR) on for scanned documents and for text inside pictures. Switch it off for digital PDFs and e-books: it is 2-3 times faster and the text is the same. Pick an OCR engine when it is on; Auto is a good default.

7. Turn on external plugins only when you intentionally want Docling to load installed plugin packages.

8. Use Portable Tesseract when tesseract.exe lives in a USB or standalone folder. Choose either the folder containing tesseract.exe or the parent install folder.

9. Use Check Extensions to confirm Docling and OCR components are visible.

10. Review the command preview. Docling starts once per output folder and converts all of that folder's files in one go.

11. Click Run Batch Conversion or Run Selected Files. Watch the log for input selection, output targets, Docling output, warnings, errors and the final count. Stop closes Docling at once; files already finished are kept.

Updates

The header shows the installed Docling version. At every start the launcher quietly asks the package index once whether a newer Docling exists; if so, the newer version and an Update button appear beside it. Update saves a restore point of the current versions, then installs Docling and its OCR add-ins. Go back reinstalls the saved versions. Check now asks the package index at any time.
"""
        text.insert("1.0", guide)
        text.configure(state="disabled")

    def _on_close(self) -> None:
        if "update" in self.active_jobs or "restore" in self.active_jobs:
            if not messagebox.askyesno(
                APP_NAME,
                "An update is in progress. Closing now can leave Docling half-installed "
                "(Go back can repair it next time). Close anyway?",
            ):
                return
        elif self.running:
            if not messagebox.askyesno(
                APP_NAME,
                "A batch is still running. Closing stops Docling. Close anyway?",
            ):
                return
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
    if selftest:
        def report() -> None:
            import json
            Path(selftest).write_text(json.dumps({
                "app": APP_VERSION,
                "frozen": bool(getattr(sys, "frozen", False)),
                "icon_found": icon.exists(),
                "docling": app.docling_version_var.get(),
                "update_status": app.update_status_var.get(),
                "update_button_shown": bool(app.update_button and app.update_button.winfo_manager()),
                "docling_exe": str(resolve_docling()),
                "log": app.log_text.get("1.0", "end").strip(),
            }, indent=2), encoding="utf-8")
            app._on_close()
        root.after(6000, report)
    root.mainloop()
