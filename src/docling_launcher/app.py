from __future__ import annotations

from datetime import datetime
from pathlib import Path
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .admin import is_user_admin, run_elevated_batch
from .constants import (
    APP_NAME,
    APP_VERSION,
    CONVERSION_MODES,
    OCR_ENGINES,
    OUTPUT_FORMATS,
    SUPPORTED_INPUT_EXTENSIONS,
    TOOLTIP_TEXT,
)
from .docling_cli import (
    build_command_plan,
    build_preview,
    discover_input_files,
    output_dir_for,
    resolve_docling,
)
from .environment import (
    check_all_dependencies,
    check_package_updates,
    get_docling_version,
)
from .settings import LauncherSettings


FORMAT_OUTPUT_SUFFIXES = {
    "md": ".md",
    "json": ".json",
    "html": ".html",
    "text": ".txt",
    "doclang": ".xml",
    "doctags": ".doctags",
    "vtt": ".vtt",
    "dclx": ".dclx",
}


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
        if self.winfo_viewable():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class DoclingLauncherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1080x860")
        self.root.minsize(900, 650)

        self.settings = LauncherSettings.load()
        self.log_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False

        self.input_folder_var = tk.StringVar(value=self.settings.input_folder)
        self.output_folder_var = tk.StringVar(value=self.settings.output_folder)
        self.convert_all_files_var = tk.BooleanVar(value=self.settings.convert_all_files)
        self.selected_input_files = [
            Path(path) for path in self.settings.selected_input_files
        ]
        self.selected_files_summary_var = tk.StringVar()
        self.mode_var = tk.StringVar(value=self.settings.conversion_mode)
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
        self.format_vars = {
            value: tk.BooleanVar(value=value in self.settings.output_formats)
            for _, value in OUTPUT_FORMATS
        }

        self.status_tree: ttk.Treeview | None = None
        self.run_button: ttk.Button | None = None
        self.select_files_button: ttk.Button | None = None
        self.tesseract_widgets: list[tk.Widget] = []

        self._configure_style()
        self._build_ui()
        self._bind_var_changes()
        self._update_preview()
        self._sync_input_scope_state()
        self._sync_tesseract_state()
        self._drain_log_queue()
        self._append_log("Ready.")

    def _configure_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
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

        self._build_updates_section(scroller.content)
        self._build_io_section(scroller.content)
        self._build_mode_section(scroller.content)
        self._build_formats_section(scroller.content)
        self._build_ocr_section(scroller.content)
        self._build_tesseract_section(scroller.content)
        self._build_status_section(scroller.content)
        self._build_run_section(scroller.content)
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

    def _section(self, parent, title: str, row: int) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title, padding=10, style="Section.TLabelframe")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        frame.grid_columnconfigure(0, weight=1)
        return frame

    def _build_updates_section(self, parent) -> None:
        section = self._section(parent, "Updates", 0)
        buttons = ttk.Frame(section)
        buttons.grid(row=0, column=0, sticky="w")
        ttk.Button(buttons, text="How to Use", command=self._show_how_to_use).grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(
            buttons,
            text="Check Docling Updates",
            command=self._check_docling_updates,
        ).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(
            buttons,
            text="Check Extensions / Add-ins Updates",
            command=self._check_extension_updates,
        ).grid(row=0, column=2)

    def _build_io_section(self, parent) -> None:
        section = self._section(parent, "Input / Output", 1)
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
        section = self._section(parent, "Conversion Mode", 2)
        for index, (value, label) in enumerate(CONVERSION_MODES.items()):
            button = ttk.Radiobutton(section, text=label, value=value, variable=self.mode_var)
            button.grid(row=index, column=0, sticky="w", pady=2)
            self._tooltip(button, TOOLTIP_TEXT[f"mode_{value}"])

    def _build_formats_section(self, parent) -> None:
        section = self._section(parent, "Output Formats", 3)
        for index, (label, value) in enumerate(OUTPUT_FORMATS):
            button = ttk.Checkbutton(section, text=label, variable=self.format_vars[value])
            button.grid(row=index // 4, column=index % 4, sticky="w", padx=(0, 24), pady=3)
            self._tooltip(button, TOOLTIP_TEXT["formats"])

    def _build_ocr_section(self, parent) -> None:
        section = self._section(parent, "OCR and Plugins", 4)
        section.grid_columnconfigure(1, weight=1)
        ttk.Label(section, text="OCR engine").grid(row=0, column=0, sticky="w", padx=(0, 8))
        combo = ttk.Combobox(
            section,
            textvariable=self.ocr_engine_var,
            values=OCR_ENGINES,
            state="readonly",
            width=28,
        )
        combo.grid(row=0, column=1, sticky="w")
        plugin_check = ttk.Checkbutton(
            section,
            text="Allow external plugins",
            variable=self.allow_plugins_var,
        )
        plugin_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._tooltip(combo, TOOLTIP_TEXT["ocr_engine"])
        self._tooltip(plugin_check, TOOLTIP_TEXT["plugins"])

    def _build_tesseract_section(self, parent) -> None:
        section = self._section(parent, "Portable Tesseract", 5)
        section.grid_columnconfigure(1, weight=1)
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
        section = self._section(parent, "Extension Status", 6)
        self.status_tree = ttk.Treeview(
            section,
            columns=("component", "status", "detail"),
            show="headings",
            height=5,
        )
        self.status_tree.heading("component", text="Component")
        self.status_tree.heading("status", text="Status")
        self.status_tree.heading("detail", text="Detail")
        self.status_tree.column("component", width=150, anchor="w")
        self.status_tree.column("status", width=90, anchor="w")
        self.status_tree.column("detail", width=600, anchor="w")
        self.status_tree.grid(row=0, column=0, sticky="ew")
        self.status_tree.tag_configure("ok", foreground="#177245")
        self.status_tree.tag_configure("bad", foreground="#a4262c")
        for name in ["Docling CLI", "RapidOCR", "EasyOCR", "Tesseract", "OnnxTR"]:
            self.status_tree.insert("", "end", values=(name, "Unknown", "Not checked yet"))

    def _build_run_section(self, parent) -> None:
        section = self._section(parent, "Run", 7)
        section.grid_columnconfigure(0, weight=1)

        command_entry = ttk.Entry(
            section,
            textvariable=self.command_preview_var,
            state="readonly",
        )
        command_entry.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        self._tooltip(command_entry, TOOLTIP_TEXT["command_preview"])

        self.run_button = ttk.Button(
            section,
            text="Run Batch Conversion",
            command=self._on_run_clicked,
        )
        self.run_button.grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Button(section, text="Check Extensions", command=self._check_extensions).grid(
            row=1, column=1, sticky="w", padx=(0, 8)
        )
        ttk.Button(section, text="Exit", command=self._on_close).grid(
            row=1, column=2, sticky="w", padx=(0, 16)
        )
        admin_check = ttk.Checkbutton(
            section,
            text="Run as Administrator",
            variable=self.run_as_admin_var,
        )
        admin_check.grid(row=1, column=3, sticky="w")
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
            )
        except Exception as exc:
            preview = f"Unable to build preview: {exc}"
        self.command_preview_var.set(preview)

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

    def _queue_done(self) -> None:
        self.log_queue.put(("done", None))

    def _queue_statuses(self, statuses) -> None:
        self.log_queue.put(("statuses", statuses))

    def _drain_log_queue(self) -> None:
        while True:
            try:
                kind, payload = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "done":
                self.running = False
                if self.run_button:
                    self.run_button.configure(state="normal")
            elif kind == "statuses":
                self._apply_statuses(payload)
        self.root.after(100, self._drain_log_queue)

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

        if self.portable_tesseract_var.get():
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
        self.running = True
        if self.run_button:
            self.run_button.configure(state="disabled")
        if selected_files is None:
            self._append_log("Starting batch conversion.")
        else:
            self._append_log(f"Starting conversion of {len(selected_files)} selected file(s).")

        args = (
            input_folder,
            output_folder,
            formats,
            selected_files,
            self._settings_from_vars(),
        )
        threading.Thread(target=self._run_batch, args=args, daemon=True).start()

    def _run_batch(
        self,
        input_folder: Path,
        output_folder: Path | None,
        formats: list[str],
        selected_files: list[Path] | None,
        settings: LauncherSettings,
    ) -> None:
        try:
            if selected_files is None:
                files = discover_input_files(input_folder)
                self._queue_log(f"Discovered {len(files)} supported input file(s).")
            else:
                files = selected_files
                self._queue_log(f"Using {len(files)} selected input file(s).")
            if not files:
                self._queue_log("No supported files were found or selected.")
                return

            plans = []
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

            for index, source in enumerate(files, start=1):
                destination_root = output_folder or source.parent
                destination = output_dir_for(
                    source,
                    input_folder,
                    destination_root,
                    settings.conversion_mode,
                )
                destination.mkdir(parents=True, exist_ok=True)
                plan = build_command_plan(
                    source=source,
                    output_dir=destination,
                    formats=formats,
                    ocr_engine=settings.ocr_engine,
                    allow_external_plugins=settings.allow_external_plugins,
                    portable_tesseract_enabled=settings.portable_tesseract_enabled,
                    portable_tesseract_path=settings.portable_tesseract_path,
                )
                plans.append(plan)
                self._queue_log(f"[{index}/{len(files)}] {source} -> {destination}")

            if settings.run_as_admin and not is_user_admin():
                exit_code = run_elevated_batch(plans, self._queue_log)
                self._queue_log(f"Elevated batch exited with code {exit_code}.")
                return

            failures = 0
            for index, plan in enumerate(plans, start=1):
                self._queue_log(f"Running [{index}/{len(plans)}]: {plan.preview}")
                started_at = time.time()
                output_lines: list[str] = []
                process = subprocess.Popen(
                    plan.command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(plan.output_dir),
                    env=plan.env,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                assert process.stdout is not None
                for line in process.stdout:
                    clean_line = line.rstrip()
                    output_lines.append(clean_line)
                    self._queue_log(clean_line)
                exit_code = process.wait()
                self._queue_log(f"Exit code: {exit_code}")
                if exit_code != 0:
                    output_text = "\n".join(output_lines)
                    if self._is_temp_cleanup_after_success(plan, formats, started_at, output_text):
                        self._queue_log(
                            "Warning: Docling wrote the expected outputs, then failed while "
                            "cleaning its temporary folder. Treating this conversion as complete."
                        )
                    else:
                        failures += 1

            if failures:
                self._queue_log(
                    f"Batch completed with {failures} failed conversion(s) out of {len(plans)}."
                )
            else:
                self._queue_log(f"Batch completed successfully: {len(plans)} file(s).")
        except Exception as exc:
            self._queue_log(f"ERROR: {exc}")
        finally:
            self._queue_done()

    def _is_temp_cleanup_after_success(
        self,
        plan,
        formats: list[str],
        started_at: float,
        output_text: str,
    ) -> bool:
        if "PermissionError" not in output_text or "tempfile.py" not in output_text:
            return False

        expected_paths = []
        for fmt in formats:
            suffix = FORMAT_OUTPUT_SUFFIXES.get(fmt)
            if suffix:
                expected_paths.append(plan.output_dir / f"{plan.source.stem}{suffix}")
        if not expected_paths:
            return False

        for path in expected_paths:
            if not path.exists():
                return False
            try:
                if path.stat().st_mtime < started_at - 2:
                    return False
            except OSError:
                return False
        return True

    def _check_extensions(self) -> None:
        self._append_log("Checking extension status.")

        def worker() -> None:
            statuses = check_all_dependencies()
            self._queue_statuses(statuses)
            for status in statuses:
                state = "OK" if status.ok else "Missing"
                self._queue_log(f"{status.name}: {state} - {status.detail}")

        threading.Thread(target=worker, daemon=True).start()

    def _check_docling_updates(self) -> None:
        self._append_log("Checking Docling version and update status.")

        def worker() -> None:
            self._queue_log(get_docling_version())
            code, output = check_package_updates(["docling", "docling-slim"])
            self._queue_log(output)
            self._queue_log(f"Docling update check exited with code {code}.")

        threading.Thread(target=worker, daemon=True).start()

    def _check_extension_updates(self) -> None:
        self._append_log("Checking extension / add-in update status.")

        def worker() -> None:
            packages = [
                "rapidocr-onnxruntime",
                "easyocr",
                "onnxtr",
                "docling-ocr-onnxtr",
                "tesserocr",
            ]
            code, output = check_package_updates(packages)
            self._queue_log(output)
            self._queue_log(f"Extension update check exited with code {code}.")

        threading.Thread(target=worker, daemon=True).start()

    def _show_how_to_use(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("How to Use Docling Launcher")
        window.geometry("680x520")
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

6. Pick an OCR engine. Auto is a good default for most conversions.

7. Turn on external plugins only when you intentionally want Docling to load installed plugin packages.

8. Use Portable Tesseract when tesseract.exe lives in a USB or standalone folder. Choose either the folder containing tesseract.exe or the parent install folder.

9. Use Check Extensions to confirm Docling and OCR components are visible.

10. Review the command preview. The run creates one command per chosen input file.

11. Click Run Batch Conversion or Run Selected Files. Watch the log for input selection, output targets, Docling output, exit codes, warnings, and errors.
"""
        text.insert("1.0", guide)
        text.configure(state="disabled")

    def _on_close(self) -> None:
        if self.running:
            if not messagebox.askyesno(
                APP_NAME,
                "A batch is still running. Close the launcher anyway?",
            ):
                return
        self._save_settings()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = DoclingLauncherApp(root)
    root.protocol("WM_DELETE_WINDOW", app._on_close)
    root.mainloop()
