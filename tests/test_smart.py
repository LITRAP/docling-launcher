"""Guards for the launcher's own judgement: skip what is done, retry what failed, decide
OCR per file, describe pictures afterwards, take drops, keep presets, fill the results
table. Same withdrawn-window fixture as test_launcher.py."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_launcher import WindowFixture, _pump_until, _settle  # noqa: E402
from docling_launcher import app as app_module, dragdrop  # noqa: E402


class SmartBatchTests(WindowFixture):
    def _run_and_wait(self):
        with mock.patch.object(app_module, "speech_available", return_value=False):
            self.app.run_button.invoke()
            self.assertTrue(_pump_until(self.root, lambda: "batch" not in self.app.active_jobs, 40))
        _pump_until(self.root, lambda: not self.app._pumping, 5)

    def _results(self) -> dict[str, tuple[str, str]]:
        tree = self.app.results_tree
        return {tree.item(i, "values")[0]: tree.item(i, "values")[2:4] for i in tree.get_children()}

    def test_skips_what_is_already_converted_and_says_so(self):
        src, out = self._prepare_batch(mode="flat")
        _settle(self.root, self.app)
        self.app.skip_converted_var.set(True)
        self._run_and_wait()
        first = self._results()
        self.assertEqual(first["a.pdf"][0], "converted")
        self.assertEqual(first["song.mp3"][0], "skipped — no speech library")
        # second run: everything is already there and newer than the sources
        self.app.log_text.configure(state="normal"); self.app.log_text.delete("1.0", "end"); self.app.log_text.configure(state="disabled")
        self._run_and_wait()
        self.assertIn("Skipped 3 file(s) already converted", self.log())
        self.assertIn("Nothing to convert.", self.log())
        self.assertEqual(self._results()["b.docx"][0], "already converted")
        # touch a source: only that one is converted again
        time.sleep(1.1)
        (src / "a.pdf").write_bytes(b"%PDF-new")
        self._run_and_wait()
        self.assertIn("1 file(s) in 1 Docling run(s)", self.log())

    def test_a_failure_is_retried_once_and_then_counted_as_done(self):
        src, out = self._prepare_batch(mode="flat")
        _settle(self.root, self.app)
        self.app.skip_converted_var.set(False)
        marker = self.home / "failed_once.marker"
        with mock.patch.dict(os.environ, {"FAKE_DOCLING_FAIL_STEM": "b", "FAKE_DOCLING_FAIL_ONCE_MARKER": str(marker)}):
            self._run_and_wait()
        text = self.log()
        self.assertIn("Retrying 1 failed file(s).", text)
        self.assertIn("Batch completed successfully: 3 file(s)", text)
        self.assertEqual(self._results()["b.docx"][0], "converted")
        self.assertTrue(marker.exists())

    def test_ocr_is_decided_per_file_and_scans_get_their_own_run(self):
        src, out = self._prepare_batch(mode="flat")
        (src / "scan.pdf").write_bytes(b"%PDF")
        _settle(self.root, self.app)
        self.app.skip_converted_var.set(False)
        self.app.ocr_mode_var.set("auto")
        self._run_and_wait()
        text = self.log()
        self.assertIn("OCR decided per file: 1 scanned PDF(s) will be read with OCR, 2 digital PDF(s) without.", text)
        self.assertIn("4 file(s) in 2 Docling run(s)", text)
        self.assertEqual(self._results()["scan.pdf"][0], "converted")

    def test_pictures_are_described_in_a_pass_of_their_own(self):
        src, out = self._prepare_batch(mode="flat")
        _settle(self.root, self.app)
        self.app.skip_converted_var.set(False)
        self.app.describe_pictures_var.set(True)
        self.app.describe_model_var.set("better")
        self._run_and_wait()
        text = self.log()
        self.assertIn("Describing pictures in 3 file(s) with the better model.", text)
        self.assertIn("(description 1)", (out / "a.md").read_text(encoding="utf-8"))
        self.assertIn("(description", (out / "c.md").read_text(encoding="utf-8"))
        self.assertIn("Batch completed successfully", text)
        self.assertEqual(self.app.progress_var.get(), 1.0)

    def test_results_table_and_progress_follow_the_batch(self):
        src, out = self._prepare_batch(mode="mirror")
        _settle(self.root, self.app)
        self.app.skip_converted_var.set(False)
        self._run_and_wait()
        rows = self._results()
        self.assertEqual(rows["a.pdf"][0], "converted")
        self.assertEqual(rows["c.pdf"][0], "converted")
        self.assertTrue(rows["a.pdf"][1].endswith(" s"), rows["a.pdf"])
        self.assertTrue(self.app.status_var.get().startswith("Done:"), self.app.status_var.get())
        where = {self.app.results_tree.item(i, "values")[0]: self.app.results_tree.item(i, "values")[1] for i in self.app.results_tree.get_children()}
        self.assertEqual(where["c.pdf"], "sub")

    def test_a_dropped_folder_and_dropped_files(self):
        src, out = self._prepare_batch()
        _settle(self.root, self.app)
        dragdrop.simulate_drop(self.root, [src / "sub"])
        _pump_until(self.root, lambda: self.app.input_folder_var.get() == str(src / "sub"), 5)
        self.assertEqual(self.app.input_folder_var.get(), str(src / "sub"))
        self.assertTrue(self.app.convert_all_files_var.get())
        dragdrop.simulate_drop(self.root, [src / "a.pdf", src / "sub" / "c.pdf"])
        _pump_until(self.root, lambda: len(self.app.selected_input_files) == 2, 5)
        self.assertEqual(self.app.input_folder_var.get(), str(src))
        self.assertFalse(self.app.convert_all_files_var.get())
        self.assertEqual([p.name for p in self.app.selected_input_files], ["a.pdf", "c.pdf"])
        self.assertEqual(str(self.app.run_button.cget("text")), "Run selected files")

    def test_presets_carry_how_not_where(self):
        _settle(self.root, self.app)
        self.app.input_folder_var.set(r"C:\somewhere")
        self.app.enrich_formula_var.set(True)
        self.app.ocr_mode_var.set("off")
        with mock.patch.object(app_module.simpledialog, "askstring", return_value="Technical"):
            self.app._save_preset()
        self.assertIn("Technical", self.app.settings.presets)
        self.assertNotIn("input_folder", self.app.settings.presets["Technical"])
        self.app.enrich_formula_var.set(False)
        self.app.ocr_mode_var.set("auto")
        self.app.input_folder_var.set(r"C:\elsewhere")
        self.app._apply_preset("Technical")
        self.assertTrue(self.app.enrich_formula_var.get())
        self.assertEqual(self.app.ocr_mode_var.get(), "off")
        self.assertEqual(self.app.input_folder_var.get(), r"C:\elsewhere", "folders are not part of a preset")
        self.assertEqual(self.app.ocr_display_var.get().split(" ")[0], "Off")

    def test_dark_and_light(self):
        _settle(self.root, self.app)
        before = self.app.theme_var.get()
        self.app._toggle_theme()
        self.assertNotEqual(self.app.theme_var.get(), before)
        self.assertEqual(self.app._settings_from_vars().theme, self.app.theme_var.get())
        self.app._toggle_theme()
        self.assertEqual(self.app.theme_var.get(), before)


if __name__ == "__main__":
    unittest.main()
