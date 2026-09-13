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

    def test_looks_cycle_system_light_dark(self):
        _settle(self.root, self.app)
        seen = [self.app.theme_var.get()]
        for _ in range(3):
            self.app._toggle_theme()
            seen.append(self.app.theme_var.get())
        self.assertEqual(seen[0], seen[3], "three presses come back to the start")
        self.assertEqual(set(seen[:3]), {"system", "light", "dark"})
        self.assertIn(self.app._effective_theme(), ("light", "dark"))
        self.assertEqual(self.app._settings_from_vars().theme, self.app.theme_var.get())

    def test_ocr_languages_and_chunks_reach_the_command(self):
        _settle(self.root, self.app)
        self.app.ocr_mode_var.set("always")
        self.app.ocr_lang_var.set(" fr, en ")
        self.app.format_vars["chunks"].set(True)
        self.app._update_preview()
        preview = self.app.command_preview_var.get()
        self.assertIn("--ocr-lang fr,en", preview)
        self.assertIn("--to chunks", preview)
        from docling_launcher.docling_cli import expected_outputs
        self.assertEqual([p.name for p in expected_outputs(Path("a.pdf"), Path("o"), ["chunks"])], ["a.chunks.jsonl"])

    def test_prompt_is_kept_and_reset(self):
        _settle(self.root, self.app)
        self.app.describe_prompt_text.delete("1.0", "end")
        self.app.describe_prompt_text.insert("1.0", "Describe the drawing for an engineer.")
        self.app._take_prompt()
        self.assertEqual(self.app._settings_from_vars().describe_prompt, "Describe the drawing for an engineer.")
        self.app._reset_prompt()
        self.assertEqual(self.app._settings_from_vars().describe_prompt, app_module.DEFAULT_DESCRIBE_PROMPT)

    def test_speaker_names_replace_labels_in_transcripts(self):
        _settle(self.root, self.app)
        transcript = self.home / "meeting.md"
        transcript.write_text("# meeting\n\n**Speaker 1** (00:00)  \nHello.\n\n**Speaker 2** (00:05)  \nHi.\n", encoding="utf-8")
        changed = self.app._apply_speaker_names([transcript], {"Speaker 1": "Anna", "Speaker 2": ""})
        self.assertEqual(changed, 1)
        text = transcript.read_text(encoding="utf-8")
        self.assertIn("**Anna** (00:00)", text)
        self.assertIn("**Speaker 2** (00:05)", text, "an empty name keeps the label")

    def test_report_after_a_batch_and_time_left(self):
        src, out = self._prepare_batch(mode="flat")
        _settle(self.root, self.app)
        self.app.skip_converted_var.set(False)
        self.assertEqual(str(self.app.report_button.cget("state")), "disabled")
        self._run_and_wait()
        self.assertEqual(str(self.app.report_button.cget("state")), "normal")
        target = self.home / "report.md"
        with mock.patch.object(app_module.filedialog, "asksaveasfilename", return_value=str(target)):
            self.app._save_report()
        text = target.read_text(encoding="utf-8")
        self.assertIn("| a.pdf | . | converted |", text)
        self.assertIn("[a.md](", text)


if __name__ == "__main__":
    unittest.main()


class WatchQueueTests(WindowFixture):
    def _wait_batch(self, timeout=40):
        self.assertTrue(_pump_until(self.root, lambda: "batch" not in self.app.active_jobs and not self.app._pumping, timeout))

    def test_watched_folder_converts_new_files_by_itself(self):
        src, out = self._prepare_batch(mode="flat")
        _settle(self.root, self.app)
        with mock.patch.object(app_module, "speech_available", return_value=False):
            self.app.watch_folder_var.set(True)
            self.app._sync_watcher()
            self.assertIsNotNone(self.app._watcher)
            self.assertIn("Watching", self.log())
            (src / "new.pdf").write_bytes(b"%PDF")
            # the watcher settles for 5 s, then the batch runs by itself
            self.assertTrue(_pump_until(self.root, lambda: "New files in the watched folder" in self.log(), 15))
            self._wait_batch()
        self.assertTrue((out / "new.md").exists())
        self.assertIn("Batch completed successfully", self.log())
        self.app.watch_folder_var.set(False)
        self.app._sync_watcher()
        self.assertIsNone(self.app._watcher)

    def test_queue_runs_folders_one_after_another(self):
        src, out = self._prepare_batch(mode="flat")
        second = self.home / "in2"
        second.mkdir()
        (second / "z.pdf").write_bytes(b"%PDF")
        out2 = self.home / "out2"
        _settle(self.root, self.app)
        self.app.skip_converted_var.set(False)
        self.app.queue_entries = [
            {"input": str(src), "output": str(out), "mode": "flat", "preset": ""},
            {"input": str(second), "output": str(out2), "mode": "flat", "preset": ""},
        ]
        with mock.patch.object(app_module, "speech_available", return_value=False):
            self.app._queue_running = True
            self.app._run_next_in_queue()
            self.assertTrue(_pump_until(self.root, lambda: "Queue finished." in self.log(), 60))
            self._wait_batch()
        self.assertTrue((out / "a.md").exists())
        self.assertTrue((out2 / "z.md").exists())
        self.assertEqual(self.app.queue_entries, [])
        self.assertFalse(self.app._queue_running)

    def test_scene_times_are_stamped_from_the_json(self):
        from docling_launcher import media
        markdown = self.home / "clip.md"
        markdown.write_text("![Image](clip_artifacts/frame_a.png)\n\ntext\n\n![Image](clip_artifacts/frame_b.png)\n", encoding="utf-8")
        json_path = self.home / "clip.json"
        json_path.write_text('{"pictures": [{"source": [{"start_time": 4.9}], "image": {"uri": "C:/x/clip_artifacts/frame_a.png"}},'
                             ' {"source": [{"start_time": 65.2}], "image": {"uri": "C:/x/clip_artifacts/frame_b.png"}}]}', encoding="utf-8")
        times = media.scene_times(json_path)
        self.assertEqual(media.add_scene_times(markdown, times), 2)
        text = markdown.read_text(encoding="utf-8")
        self.assertIn("**At 00:04**\n\n![Image](clip_artifacts/frame_a.png)", text)
        self.assertIn("**At 01:05**\n\n![Image](clip_artifacts/frame_b.png)", text)

    def test_reference_check_records_then_compares(self):
        from docling_launcher import safety
        _settle(self.root, self.app)
        first = safety.Measurement(1000, 12, 17, 20.0, "2.126.0")
        worse = safety.Measurement(600, 12, 17, 21.0, "2.127.0")
        with mock.patch.object(safety, "run_reference", return_value=first):
            self.app._run_reference_check("2.126.0")
            _pump_until(self.root, lambda: not self.app._pumping, 5)
            self.root.update()
        self.assertEqual(self.app.settings.reference_baseline["words"], 1000)
        self.assertIn("Reference recorded", self.log())
        with mock.patch.object(safety, "run_reference", return_value=worse), \
             mock.patch.object(app_module.messagebox, "showwarning") as warn:
            self.app._run_reference_check("2.127.0")
            _pump_until(self.root, lambda: not self.app._pumping, 5)
            self.root.update()
        self.assertIn("words 1000 -> 600", self.log())
        self.assertEqual(self.app.settings.reference_baseline["words"], 1000, "a bad run does not become the baseline")
        self.assertTrue(warn.called)
