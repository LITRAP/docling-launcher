"""Guards for the "What's in these documents?" strip (2026-09-21, the owner's idea): plain-
word tick boxes on the Convert tab that ARE the settings, what the launcher finds in the
chosen files, the time estimate, and what it learns from a batch. Same conventions as
test_launcher.py; nothing appears on screen and nothing of the owner's is touched."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from docling_launcher import estimate  # noqa: E402
from docling_launcher.estimate import Findings, Speed, describe_duration, estimate_seconds, findings_from_probe, learn  # noqa: E402
from test_launcher import WindowFixture, _pump_until, _settle  # noqa: E402


class EstimateTests(unittest.TestCase):
    def test_findings_read_the_probe(self):
        files = [Path("a.pdf"), Path("scan.pdf"), Path("talk.mp3"), Path("notes.docx"), Path("photo.png"), Path("odd.pdf")]
        probe = {files[0]: {"pages": 68, "text_chars": 6609}, files[1]: {"pages": 4, "text_chars": 0},
                 files[2]: {"seconds": 3233.1}}
        found = findings_from_probe(files, probe)
        self.assertEqual((found.files, found.pdfs, found.pages, found.scanned_pages, found.scanned_pdfs), (6, 3, 72, 4, 1))
        self.assertEqual((found.media, round(found.media_seconds), found.images, found.others, found.unknown_pdfs), (1, 3233, 1, 1, 1))
        self.assertEqual(found.summary(), "72 pages in 3 PDFs · 4 scanned · 1 picture file · 1 recording (54 min) · 1 other document")
        self.assertEqual(Findings().summary(), "No files chosen yet.")
        self.assertTrue(findings_from_probe(files, probe, capped=True).summary().endswith("(and more)"))

    def test_the_estimate_matches_what_was_measured(self):
        """The 68-page standard: plain 41 s, formulas + charts 508 s, 33 descriptions 421 s;
        the 54-minute meeting 377 s. The estimate must land within a third of each."""
        standard = Findings(files=1, pdfs=1, pages=68)
        plain = estimate_seconds(standard, ocr=True, formulas=False, charts=False, describe=False, speakers=True)
        self.assertLess(abs(plain - 41) / 41, 0.34, plain)
        rich = estimate_seconds(standard, ocr=True, formulas=True, charts=True, describe=False, speakers=True)
        self.assertLess(abs(rich - 508) / 508, 0.34, rich)
        everything = estimate_seconds(standard, ocr=True, formulas=True, charts=True, describe=True, speakers=True)
        self.assertLess(abs(everything - (508 + 421)) / 929, 0.34, everything)
        meeting = Findings(files=1, media=1, media_seconds=3233)
        spoken = estimate_seconds(meeting, ocr=True, formulas=True, charts=True, describe=True, speakers=True)
        self.assertLess(abs(spoken - 377) / 377, 0.34, spoken)
        self.assertGreater(estimate_seconds(standard, ocr=True, formulas=False, charts=True, describe=False, speakers=True),
                           estimate_seconds(standard, ocr=True, formulas=True, charts=False, describe=False, speakers=True),
                           "charts are the expensive tick")
        self.assertEqual(estimate_seconds(standard, ocr=True, formulas=True, charts=True, describe=True, speakers=True, speed=Speed(factor=2.0)),
                         2 * everything, "the machine factor scales everything")

    def test_durations_read_as_about(self):
        self.assertEqual(describe_duration(41), "about 40 s")
        self.assertEqual(describe_duration(508), "about 8 min")
        self.assertEqual(describe_duration(4200), "about 1 h 10 min")
        line = estimate.estimate_line(Findings(files=1, pdfs=1, pages=68), ocr=True, formulas=True, charts=True, describe=True, speakers=True)
        self.assertIn("with what's ticked", line)
        self.assertIn("text only", line)
        quiet = estimate.estimate_line(Findings(files=1, pdfs=1, pages=68), ocr=True, formulas=False, charts=False, describe=False, speakers=True)
        self.assertNotIn("text only", quiet, "nothing to compare with when nothing is ticked")
        self.assertEqual(estimate.estimate_line(Findings(), ocr=True, formulas=True, charts=True, describe=True, speakers=True), "")

    def test_learning_is_gentle_and_bounded(self):
        speed = Speed()
        slower = learn(speed, estimated=100, actual=200)
        self.assertGreater(slower.factor, 1.0)
        self.assertLess(slower.factor, 1.5, "a third of the way, not all of it")
        self.assertEqual(learn(speed, estimated=5, actual=200).factor, 1.0, "a trivial batch teaches nothing")
        self.assertEqual(learn(speed, estimated=100, actual=5).factor, 1.0)
        wild = Speed(factor=19.0)
        self.assertLessEqual(learn(wild, estimated=100, actual=100000).factor, 20.0)
        pictures = learn(speed, estimated=100, actual=100, pages=68, pictures=33)
        self.assertGreater(pictures.pictures_per_page, 0.4)
        self.assertLess(pictures.pictures_per_page, 0.5, "moves a third of the way towards 33/68")
        self.assertEqual(learn(speed, estimated=100, actual=100, pages=2, pictures=9).pictures_per_page, speed.pictures_per_page, "two pages prove nothing")
        self.assertEqual(Speed.from_dict({"factor": "nonsense"}).factor, 1.0)
        self.assertEqual(Speed.from_dict({"factor": 99}).factor, 20.0)
        self.assertEqual(Speed.from_dict(Speed(factor=1.3).to_dict()).factor, 1.3)


class StripTests(WindowFixture):
    def test_the_strip_ticks_are_the_settings(self):
        app = self.app
        app.enrich_formula_var.set(False)
        app.enrich_chart_var.set(False)
        app.contents_boxes["contents_formulas"].invoke()
        self.assertTrue(app.enrich_formula_var.get(), "the strip's box and the Settings box share one variable")
        options = app._settings_from_vars().conversion_options()
        self.assertTrue(options.enrich_formula)
        self.assertFalse(options.enrich_chart)

    def test_scanned_pages_tick_follows_and_drives_the_ocr_mode(self):
        app = self.app
        app.ocr_mode_var.set("auto")
        app._update_preview()
        self.assertTrue(app.ocr_tick_var.get())
        app.ocr_tick_var.set(False)
        app._take_ocr_tick()
        self.assertEqual(app.ocr_mode_var.get(), "off")
        app.ocr_tick_var.set(True)
        app._take_ocr_tick()
        self.assertEqual(app.ocr_mode_var.get(), "auto", "ticking from off means decided per file")
        app.ocr_mode_var.set("always")
        app._update_preview()
        self.assertTrue(app.ocr_tick_var.get())
        app.ocr_tick_var.set(True)
        app._take_ocr_tick()
        self.assertEqual(app.ocr_mode_var.get(), "always", "a whole-page choice made in Settings stays")
        app.ocr_mode_var.set("off")
        app._update_preview()
        self.assertFalse(app.ocr_tick_var.get())

    def test_everything_and_text_only(self):
        app = self.app
        for variable in (app.enrich_formula_var, app.enrich_chart_var, app.describe_pictures_var, app.video_speakers_var):
            variable.set(False)
        app.ocr_mode_var.set("off")
        app._contents_everything()
        self.assertTrue(all(v.get() for v in (app.enrich_formula_var, app.enrich_chart_var, app.describe_pictures_var, app.video_speakers_var)))
        self.assertEqual(app.ocr_mode_var.get(), "auto")
        self.assertTrue(app.ocr_tick_var.get())
        app._contents_text_only()
        self.assertFalse(app.enrich_formula_var.get() or app.enrich_chart_var.get() or app.describe_pictures_var.get())
        self.assertTrue(app.video_speakers_var.get(), "speakers are not a text ability: left alone")
        self.assertEqual(app.ocr_mode_var.get(), "auto", "OCR left alone too")

    def test_findings_and_estimate_follow_the_chosen_files(self):
        app = self.app
        _settle(self.root, app)
        sample = self.home / "sample"
        sample.mkdir()
        for name in ("Standard.pdf", "Scan of the plan.pdf", "Meeting.mp4", "Notes.docx"):
            (sample / name).write_bytes(b"%PDF-1.4 stand-in" if name.endswith(".pdf") else b"x")
        app.input_folder_var.set(str(sample))
        app.convert_all_files_var.set(True)
        app._sync_input_scope_state()
        self.assertTrue(_pump_until(self.root, lambda: app._findings is not None and app._findings.files == 4, 15))
        self.assertEqual(app.findings_var.get(), "6 pages in 2 PDFs · 3 scanned · 1 recording (10 min) · 1 other document")
        self.assertIn("with what's ticked", app.estimate_var.get())
        with_charts = app.estimate_var.get()
        self.assertIn("text only", with_charts)
        app._contents_text_only()
        app._update_preview()
        self.assertNotEqual(app.estimate_var.get(), with_charts, "the line follows the ticks")
        self.assertNotIn("text only", app.estimate_var.get(), "nothing left to compare with")
        seconds = lambda charts: estimate_seconds(app._findings, ocr=True, formulas=True, charts=charts, describe=True, speakers=True, speed=app.speed)
        self.assertGreater(seconds(True) - seconds(False), 30, "six pages of charts cost over half a minute")
        # only the chosen files, when the scope is narrowed
        app.convert_all_files_var.set(False)
        app._take_selected_files([sample / "Meeting.mp4"], sample)
        self.assertTrue(_pump_until(self.root, lambda: app._findings is not None and app._findings.files == 1, 15))
        self.assertEqual(app.findings_var.get(), "1 recording (10 min)")
        app.selected_input_files = []
        app._sync_input_scope_state()
        self.assertTrue(_pump_until(self.root, lambda: app._findings is not None and app._findings.files == 0, 15))
        self.assertEqual(app.findings_var.get(), "No files chosen yet.")
        self.assertEqual(app.estimate_var.get(), "")

    def test_a_batch_records_its_estimate_and_keeps_the_speed_in_the_settings(self):
        app = self.app
        _settle(self.root, app)
        src, out = self.home / "in", self.home / "out"
        src.mkdir()
        out.mkdir()
        (src / "a.pdf").write_bytes(b"%PDF-1.4 stand-in")
        app.input_folder_var.set(str(src))
        app.output_folder_var.set(str(out))
        app.convert_all_files_var.set(True)
        app._contents_text_only()
        app.describe_pictures_var.set(False)
        app._on_run_clicked()
        self.assertTrue(_pump_until(self.root, lambda: app._last_report is not None and not app.active_jobs, 30))
        self.assertGreater(app._batch_estimate, 0.0, "the batch measured itself against the estimate")
        self.assertEqual(app._batch_pages, 3)
        self.assertEqual(app.speed.factor, 1.0, "a three-page stand-in batch is too small to teach anything")
        saved = json.loads((self.home / "appdata" / "DoclingLauncher" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["speed"], app.speed.to_dict())


if __name__ == "__main__":
    unittest.main()
