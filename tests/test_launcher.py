"""Guards for the Docling Launcher. Run with:

    .venv\\Scripts\\python.exe -m unittest discover tests -v

§1  planning   — one Docling run per output folder, split under Windows' command limit
§2  updates    — version ordering, restore points, the update table's contents
§3  hands      — the real window (withdrawn, never shown), real buttons, a stand-in Docling
§4  admin      — the elevated path builds a valid process call (the fault every exe had)

The window tests never appear on screen: the root is withdrawn before anything is built.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docling_launcher import admin, app as app_module, docling_cli, environment, models, updates  # noqa: E402
from docling_launcher.docling_cli import ConversionOptions  # noqa: E402
from docling_launcher.constants import MEDIA_INPUT_EXTENSIONS  # noqa: E402

FAKE_DOCLING = ROOT / "tests" / "fake_docling.cmd"


def _settle(root: tk.Tk, app, timeout: float = 15.0) -> None:
    """Let the start-up update check (scheduled 400 ms after the window exists) fire and
    finish, so a test starts from the same quiet state the owner sees after opening."""
    deadline = time.time() + 0.6
    while time.time() < deadline:
        root.update()
        time.sleep(0.02)
    assert _pump_until(root, lambda: not app._pumping and not app.active_jobs, timeout)


def _pump_until(root: tk.Tk, condition, timeout: float = 15.0) -> bool:
    """Turn the Tk event loop by hand until `condition()` holds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        root.update()
        if condition():
            return True
        time.sleep(0.02)
    return False


# ----------------------------------------------------------------------------- §1 planning

class PlanningTests(unittest.TestCase):
    def test_one_run_per_output_folder_in_every_mode(self):
        root = Path(r"C:\in")
        files = [root / "a.pdf", root / "b.pdf", root / "sub" / "c.pdf", root / "sub" / "deep" / "d.pdf"]
        out = Path(r"D:\out")
        mirror = docling_cli.group_sources(files, root, out, "mirror")
        self.assertEqual([str(d) for d, _ in mirror], [r"D:\out", r"D:\out\sub", r"D:\out\sub\deep"])
        self.assertEqual([len(s) for _, s in mirror], [2, 1, 1])
        flat = docling_cli.group_sources(files, root, out, "flat")
        self.assertEqual(len(flat), 1)
        self.assertEqual(len(flat[0][1]), 4)
        beside = docling_cli.group_sources(files, root, out, "beside")
        self.assertEqual([str(d) for d, _ in beside], [r"C:\in", r"C:\in\sub", r"C:\in\sub\deep"])

    def test_long_groups_split_under_the_windows_command_limit(self):
        root = Path(r"C:\in")
        files = [root / (f"{'x' * 200}_{i}.pdf") for i in range(400)]
        plans = docling_cli.build_batch_plans(files, root, Path(r"D:\out"), "flat", ConversionOptions())
        self.assertGreater(len(plans), 1)
        self.assertEqual(sum(len(p.sources) for p in plans), 400)
        for plan in plans:
            self.assertLessEqual(len(plan.preview), docling_cli.MAX_COMMAND_CHARS + 300)

    def test_verbose_flag_and_all_sources_in_the_command(self):
        plan = docling_cli.build_command_plan([Path("a.pdf"), Path("b.pdf")], Path("out"), ConversionOptions(formats=("md", "json"), allow_external_plugins=True))
        self.assertIn("-v", plan.command)
        self.assertIn("a.pdf", plan.command)
        self.assertIn("b.pdf", plan.command)
        self.assertEqual(plan.command[-2:], ["--output", "out"])

    def test_expected_outputs_use_doclings_real_names(self):
        outs = docling_cli.expected_outputs(Path("report.final.pdf"), Path("o"), ["md", "text", "doclang"])
        self.assertEqual([p.name for p in outs], ["report.final.md", "report.final.txt", "report.final.dclg.xml"])

    def test_converted_ok_needs_every_output_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            started = time.time()
            (out / "a.md").write_text("x")
            self.assertFalse(docling_cli.converted_ok(Path("a.pdf"), out, ["md", "json"], started))
            (out / "a.json").write_text("x")
            self.assertTrue(docling_cli.converted_ok(Path("a.pdf"), out, ["md", "json"], started))
            os.utime(out / "a.json", (started - 100, started - 100))
            self.assertFalse(docling_cli.converted_ok(Path("a.pdf"), out, ["md", "json"], started))

    def test_docling_log_lines_are_tidied(self):
        line = "2026-09-12 10:10:49,109\tINFO\tdocling.document_converter: Finished converting document a.md in 0.03 sec."
        self.assertEqual(docling_cli.tidy_docling_line(line), "Finished converting document a.md in 0.03 sec.")
        warn = "2026-09-12 10:10:49,126\tWARNING\tdocling_core.types.doc.document: Parameter x is deprecated"
        self.assertEqual(docling_cli.tidy_docling_line(warn), "WARNING: Parameter x is deprecated")
        self.assertEqual(docling_cli.tidy_docling_line("plain text"), "plain text")


# ----------------------------------------------------------------------------- §2 updates

class UpdateTests(unittest.TestCase):
    def test_version_ordering_reads_like_a_person(self):
        k = updates.version_key
        self.assertGreater(k("2.126.0"), k("2.99.0"))
        self.assertGreater(k("2.126.0"), k("2.115.0"))
        self.assertLess(k("1.0rc1"), k("1.0"))
        self.assertEqual(k("7.19.1"), k("7.19.1"))

    def test_status_words(self):
        S = updates.PackageStatus
        self.assertEqual(S("Docling", "docling", "2.115.0", "2.126.0").state, "Update available")
        self.assertEqual(S("Docling", "docling", "2.126.0", "2.126.0").state, "Up to date")
        self.assertEqual(S("Docling", "docling", "2.126.0", None).state, "Could not check")
        self.assertEqual(S("Docling", "docling", None, "2.126.0").state, "Not installed")
        self.assertTrue(S("Docling", "docling", "2.115.0", "2.126.0").update_available)
        self.assertFalse(S("Docling", "docling", "2.126.0", "2.115.0").update_available)

    def test_installed_versions_read_from_the_real_environment(self):
        found = updates.installed_versions(["docling", "no-such-package-xyz"])
        self.assertIsNotNone(found["docling"])
        self.assertIsNone(found["no-such-package-xyz"])

    def test_restore_point_is_the_newest_snapshot_that_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "2026-09-01_100000.txt").write_text("docling==2.100.0\nnumpy==2.0\n")
            (folder / "2026-09-10_100000.txt").write_text("docling==2.115.0\nnumpy==2.0\n")
            (folder / "2026-09-11_100000.txt").write_text("docling==2.126.0\n")
            with mock.patch.object(updates, "snapshot_dir", return_value=folder), \
                 mock.patch.object(updates, "installed_versions", return_value={"docling": "2.126.0"}):
                point = updates.restore_point()
                self.assertEqual(point, (folder / "2026-09-10_100000.txt", "2.115.0"))
            with mock.patch.object(updates, "snapshot_dir", return_value=folder), \
                 mock.patch.object(updates, "installed_versions", return_value={"docling": "2.100.0"}):
                # newest that differs from the CURRENT version, not just the newest file
                self.assertEqual(updates.restore_point()[1], "2.126.0")
            self.assertEqual(updates.snapshot_label(folder / "2026-09-10_100000.txt"), "2026-09-10 at 10:00")

    def test_check_updates_lists_only_installed_packages(self):
        statuses = updates.check_updates(online=False)
        names = [s.name for s in statuses]
        self.assertIn("docling", names)
        self.assertNotIn("tesserocr", names)  # not installed here → not a row
        self.assertTrue(all(s.latest is None for s in statuses))


# ----------------------------------------------------------------------------- §3 hands

class HandsTests(unittest.TestCase):
    """Real widgets, real button presses, a withdrawn window, a stand-in Docling."""

    @classmethod
    def setUpClass(cls):
        FAKE_DOCLING.write_text(f'@"{sys.executable}" "{ROOT / "tests" / "fake_docling.py"}" %*\r\n')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {
            "DOCLING_EXE": str(FAKE_DOCLING),
            "APPDATA": str(self.home / "appdata"),
            "FAKE_DOCLING_DELAY": "0",
        })
        self.env.start()
        (self.home / "appdata" / "DoclingLauncher").mkdir(parents=True)
        self.no_network = mock.patch.object(updates, "latest_versions", return_value={})
        self.no_network.start()
        self.no_models = mock.patch.object(app_module, "check_models", return_value=[])
        self.no_models.start()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = app_module.DoclingLauncherApp(self.root)
        self.root.update()

    def tearDown(self):
        try:
            self.app.job.terminate()
            self.root.destroy()
        finally:
            self.no_models.stop()
            self.no_network.stop()
            self.env.stop()
            self.tmp.cleanup()

    def log(self) -> str:
        return self.app.log_text.get("1.0", "end")

    def pending_timers(self) -> list[str]:
        return [t for t in self.root.tk.call("after", "info") if t]

    # --- idle cost -----------------------------------------------------------------------

    def test_idle_means_no_timer_at_all(self):
        # The quiet start-up check fires once, runs, and the pump must then STOP.
        _settle(self.root, self.app)
        self.root.update()
        self.assertFalse(self.app._pumping)
        self.assertEqual(self.app.active_jobs, set())
        self.assertEqual(self.pending_timers(), [], "nothing may run while nothing is happening")

    # --- update buttons ------------------------------------------------------------------

    def test_update_button_only_when_there_is_an_update(self):
        _settle(self.root, self.app)
        self.assertFalse(self.app.update_button.winfo_manager(), "hidden when nothing is newer")
        self.assertEqual(self.app.update_status_var.get(), "")
        self.assertTrue(self.app.docling_version_var.get().startswith("Docling "))

        newer = [updates.PackageStatus("Docling", "docling", "2.115.0", "2.126.0"),
                 updates.PackageStatus("EasyOCR", "easyocr", "1.7.2", "1.7.2")]
        self.app._apply_update_statuses(newer, quiet=True)
        self.assertTrue(self.app.update_button.winfo_manager(), "shown the moment one exists")
        self.assertEqual(self.app.update_status_var.get(), "2.126.0 available")
        rows = [self.app.updates_tree.item(i, "values") for i in self.app.updates_tree.get_children()]
        self.assertEqual(rows[0], ("Docling", "2.115.0", "—", "2.126.0", "—", "Update available"))
        self.assertEqual(rows[1], ("EasyOCR", "1.7.2", "—", "1.7.2", "—", "Up to date"))
        self.assertEqual(int(self.app.updates_tree.cget("height")), 3)

    def test_go_back_only_when_a_restore_point_differs(self):
        _settle(self.root, self.app)
        self.assertFalse(self.app.go_back_button.winfo_manager())
        folder = updates.snapshot_dir()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "2026-09-10_100000.txt").write_text("docling==1.0.0\n")
        self.app._apply_update_statuses(updates.check_updates(online=False), quiet=True)
        self.assertTrue(self.app.go_back_button.winfo_manager())
        self.assertEqual(self.app.go_back_button.cget("text"), "Go back to Docling 1.0.0")

    def test_check_now_reports_offline_honestly(self):
        _settle(self.root, self.app)
        self.app.check_updates_button.invoke()
        _settle(self.root, self.app)
        self.assertIn("Could not reach the package index", self.log())
        rows = [self.app.updates_tree.item(i, "values") for i in self.app.updates_tree.get_children()]
        self.assertTrue(all(r[-1] == "Could not check" for r in rows))

    # --- the batch -----------------------------------------------------------------------

    def _prepare_batch(self, mode="mirror"):
        src = self.home / "in"
        (src / "sub").mkdir(parents=True)
        (src / "a.pdf").write_bytes(b"%PDF")
        (src / "b.docx").write_bytes(b"docx")
        (src / "sub" / "c.pdf").write_bytes(b"%PDF")
        (src / "song.mp3").write_bytes(b"mp3")
        out = self.home / "out"
        self.app.input_folder_var.set(str(src))
        self.app.output_folder_var.set(str(out))
        self.app.mode_var.set(mode)
        self.app.run_as_admin_var.set(False)
        return src, out

    def test_batch_runs_once_per_folder_and_skips_media_without_whisper(self):
        src, out = self._prepare_batch()
        _settle(self.root, self.app)
        with mock.patch.object(app_module, "speech_available", return_value=False):
            self.app.run_button.invoke()
            self.assertTrue(self.app.stop_button.winfo_manager(), "Stop appears while running")
            self.assertEqual(str(self.app.run_button.cget("state")), "disabled")
            self.assertTrue(_pump_until(self.root, lambda: "batch" not in self.app.active_jobs, 30))
        text = self.log()
        self.assertIn("Skipped 1 sound/video file(s)", text)
        self.assertIn("3 file(s) in 2 Docling run(s)", text)
        self.assertIn("Batch completed successfully: 3 file(s)", text)
        self.assertTrue((out / "a.md").exists())
        self.assertTrue((out / "b.md").exists())
        self.assertTrue((out / "sub" / "c.md").exists())
        self.assertFalse((out / "song.md").exists())
        self.assertIn("Finished converting document a.pdf", text)  # Docling's own progress, tidied
        self.assertNotIn("\tINFO\t", text)
        _pump_until(self.root, lambda: not self.app._pumping, 5)
        self.assertFalse(self.app.stop_button.winfo_manager(), "Stop goes away when nothing runs")
        self.assertEqual(self.pending_timers(), [])

    def test_batch_converts_media_when_whisper_is_there(self):
        src, out = self._prepare_batch(mode="flat")
        _settle(self.root, self.app)
        with mock.patch.object(app_module, "speech_available", return_value=True):
            self.app.run_button.invoke()
            self.assertTrue(_pump_until(self.root, lambda: "batch" not in self.app.active_jobs, 30))
        self.assertIn("4 file(s) in 2 Docling run(s)", self.log())  # documents, then the sound file on its own
        self.assertTrue((out / "song.md").exists())

    def test_a_failed_file_is_named_and_counted(self):
        src, out = self._prepare_batch()
        _settle(self.root, self.app)
        with mock.patch.dict(os.environ, {"FAKE_DOCLING_FAIL_STEM": "b"}), \
             mock.patch.object(app_module, "speech_available", return_value=False):
            self.app.run_button.invoke()
            self.assertTrue(_pump_until(self.root, lambda: "batch" not in self.app.active_jobs, 30))
        text = self.log()
        self.assertIn("Failed: " + str(src / "b.docx"), text)
        self.assertIn("2 converted, 1 failed", text)

    def test_stop_kills_docling_and_keeps_finished_files(self):
        src, out = self._prepare_batch(mode="flat")
        _settle(self.root, self.app)
        with mock.patch.dict(os.environ, {"FAKE_DOCLING_DELAY": "3"}), \
             mock.patch.object(app_module, "speech_available", return_value=False):
            self.app.run_button.invoke()
            self.assertTrue(_pump_until(self.root, lambda: "Processing document a.pdf" in self.log(), 20))
            pressed = time.time()
            self.app.stop_button.invoke()
            self.assertTrue(_pump_until(self.root, lambda: "batch" not in self.app.active_jobs, 20))
            self.assertLess(time.time() - pressed, 3.0, "a 3-second-per-file Docling died at once")
        text = self.log()
        self.assertIn("Stopped.", text)
        self.assertNotIn("Batch completed", text)
        self.assertFalse(list(out.glob("*.md")) and (out / "c.md").exists())

    def test_closing_the_window_kills_docling(self):
        src, out = self._prepare_batch(mode="flat")
        _settle(self.root, self.app)
        with mock.patch.dict(os.environ, {"FAKE_DOCLING_DELAY": "30"}), \
             mock.patch.object(app_module, "speech_available", return_value=False), \
             mock.patch.object(app_module.messagebox, "askyesno", return_value=True):
            self.app.run_button.invoke()
            self.assertTrue(_pump_until(self.root, lambda: "Processing document a.pdf" in self.log(), 20))
            pids = _descendants_of(os.getpid())
            self.assertTrue(pids, "the stand-in Docling is running")
            self.app._on_close()
            deadline = time.time() + 5
            while time.time() < deadline and any(_alive(p) for p in pids):
                time.sleep(0.1)
            self.assertFalse(any(_alive(p) for p in pids), "nothing outlives the window")
        self.root = tk.Tk()  # tearDown needs something to destroy
        self.root.withdraw()

    # --- extension status honours the portable folder ------------------------------------

    def test_tesseract_status_looks_where_the_run_looks(self):
        portable = self.home / "tess"
        portable.mkdir()
        (portable / "tesseract.exe").write_bytes(b"MZ")
        env = docling_cli.environment_for_run(True, str(portable), use_launcher_temp=False)
        with mock.patch.object(environment.shutil, "which", wraps=environment.shutil.which):
            status = environment.check_dependency("Tesseract", ("tesseract",), env)
        self.assertTrue(status.ok)
        self.assertEqual(Path(status.detail), portable / "tesseract.exe")


def _descendants_of(pid: int) -> list[int]:
    """Every process below `pid` (the .cmd's cmd.exe and the python it starts)."""
    rows = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId) $($_.ParentProcessId)\" }"],
        capture_output=True, text=True).stdout.splitlines()
    parent_of = {}
    for row in rows:
        parts = row.split()
        if len(parts) == 2:
            parent_of[int(parts[0])] = int(parts[1])
    found, frontier = set(), {pid}
    while frontier:
        children = {p for p, parent in parent_of.items() if parent in frontier and p not in found}
        found |= children
        frontier = children
    return sorted(found)


def _alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


# ----------------------------------------------------------------------------- §4 admin

class AdminTests(unittest.TestCase):
    def test_elevated_batch_builds_a_valid_process_call(self):
        """Every exe ever built passed capture_output= to Popen, which Popen rejects, so
        'Run as Administrator' died before asking Windows anything."""
        plan = docling_cli.build_command_plan([Path("a.pdf")], Path("out"), ConversionOptions())
        recorded = {}
        real_popen = subprocess.Popen  # admin.subprocess IS this module; keep the original

        class FakeProcess:
            returncode = 0
            def poll(self): return 0
            def communicate(self): return ("", "")

        def fake_popen(*args, **kwargs):
            recorded.update(kwargs)
            # The same keywords must be accepted by the real Popen — this is exactly the
            # call that used to raise TypeError before Windows was even asked.
            real = real_popen(["cmd", "/c", "exit 0"], **kwargs)
            real.communicate()
            return FakeProcess()

        with mock.patch.object(admin.subprocess, "Popen", side_effect=fake_popen):
            code = admin.run_elevated_batch([plan], lambda _m: None)
        self.assertEqual(code, 0)
        self.assertNotIn("capture_output", recorded)
        self.assertIn("stdout", recorded)


if __name__ == "__main__":
    unittest.main()


# ----------------------------------------------------------------------------- §5 OCR switch

class OcrSwitchTests(unittest.TestCase):
    def test_off_means_no_ocr_and_no_engine(self):
        on = docling_cli.build_command_plan([Path("a.pdf")], Path("o"), ConversionOptions(ocr_engine="rapidocr", use_ocr=True))
        off = docling_cli.build_command_plan([Path("a.pdf")], Path("o"), ConversionOptions(ocr_engine="rapidocr", use_ocr=False))
        self.assertIn("--ocr-engine", on.command)
        self.assertNotIn("--no-ocr", on.command)
        self.assertIn("--no-ocr", off.command)
        self.assertNotIn("--ocr-engine", off.command)


class OcrSwitchHandsTests(HandsTests):
    """The engine row and the Portable Tesseract section exist only while OCR is on."""

    def test_engine_and_tesseract_follow_the_switch(self):
        _settle(self.root, self.app)
        self.assertTrue(self.app.use_ocr_var.get())
        for widget in self.app.ocr_dependent_widgets:
            self.assertTrue(widget.winfo_manager(), "shown while OCR is on")
        self.app.use_ocr_var.set(False)
        self.app._sync_ocr_state()
        for widget in self.app.ocr_dependent_widgets:
            self.assertFalse(widget.winfo_manager(), "hidden while OCR is off")
        self.assertIn("--no-ocr", self.app.command_preview_var.get())
        self.assertNotIn("--ocr-engine", self.app.command_preview_var.get())
        self.app.use_ocr_var.set(True)
        self.app._sync_ocr_state()
        for widget in self.app.ocr_dependent_widgets:
            self.assertTrue(widget.winfo_manager(), "back the moment OCR is on again")
        self.assertIn("--ocr-engine", self.app.command_preview_var.get())
        self.assertTrue(self.app._settings_from_vars().use_ocr)

    # the inherited HandsTests run again here with the same fixture; that is fine but slow,
    # so only this class's own test is kept:
    for _name in list(HandsTests.__dict__):
        if _name.startswith("test_"):
            locals()[_name] = None


# ----------------------------------------------------------------------------- §6 honest log

class HonestLogTests(unittest.TestCase):
    def test_an_empty_output_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            started = time.time()
            (out / "a.md").write_text("")  # Docling: "Markdown export produced empty output"
            self.assertFalse(docling_cli.converted_ok(Path("a.pdf"), out, ["md"], started))
            (out / "a.md").write_text("# a")
            self.assertTrue(docling_cli.converted_ok(Path("a.pdf"), out, ["md"], started))

    def test_chatter_is_dropped_and_document_lines_stay(self):
        tab = "\t"
        stamp = "2026-09-12 10:10:49,109"
        for noise in (
            f"{stamp}{tab}INFO{tab}docling.models.factories: Loading plugin 'docling_defaults'",
            f"{stamp}{tab}INFO{tab}httpx: HTTP Request: GET https://huggingface.co/x \"HTTP/1.1 200 OK\"",
            f"{stamp}{tab}INFO{tab}docling.cli.main: paths: [WindowsPath('C:/x/a.pdf')]",
            f"{stamp}{tab}INFO{tab}docling.cli.main: writing Markdown output to C:/x/a.md",
            f"{stamp}{tab}INFO{tab}docling.utils.hf_model_download: Fetching model docling-project/x",
        ):
            self.assertIsNone(docling_cli.tidy_docling_line(noise), noise)
        for kept, expected in (
            (f"{stamp}{tab}INFO{tab}docling.pipeline.base_pipeline: Processing document a.pdf", "Processing document a.pdf"),
            (f"{stamp}{tab}INFO{tab}docling.cli.main: Processed 3 docs, of which 1 failed", "Processed 3 docs, of which 1 failed"),
            (f"{stamp}{tab}ERROR{tab}docling.cli.main: Markdown export produced empty output for scan.png", "ERROR: Markdown export produced empty output for scan.png"),
            ("[00:00.000 --> 00:06.260]  Hello.", "[00:00.000 --> 00:06.260]  Hello."),
        ):
            self.assertEqual(docling_cli.tidy_docling_line(kept), expected)

    def test_progress_bars_keep_only_their_final_state(self):
        seen: list[str] = []
        code = docling_cli.stream_process(
            [sys.executable, "-c", "import sys; sys.stdout.write('Loading:  10%' + chr(13) + 'Loading:  60%' + chr(13) + 'Loading: 100%' + chr(10)); print('done')"],
            None, seen.append,
        )
        self.assertEqual(code, 0)
        self.assertEqual(seen, ["Loading: 100%", "done"])
