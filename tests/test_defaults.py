"""Guards for 2026-09-21: formulas, charts and picture descriptions are on by default, a
settings file saved before is switched on once (and told so in the log), a file that
carries the version keeps every choice, and the describing instruction is refreshed only
when it is still an old default. Nothing of the owner's is touched (APPDATA overridden)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from docling_launcher import app as app_module, environment, updates  # noqa: E402
from docling_launcher.constants import DEFAULT_DESCRIBE_PROMPT, PREVIOUS_DESCRIBE_PROMPTS, SETTINGS_VERSION  # noqa: E402
from docling_launcher.settings import LauncherSettings  # noqa: E402
from test_launcher import FAKE_DOCLING  # noqa: E402


class DefaultTests(unittest.TestCase):
    def test_fresh_settings_describe_everything_but_charts(self):
        s = LauncherSettings()
        self.assertTrue(s.enrich_formula and s.describe_pictures and s.keep_pictures)
        self.assertFalse(s.enrich_chart, "the chart model invents values on engineering charts (owner, 2026-09-21)")
        self.assertEqual(s.settings_version, SETTINGS_VERSION)
        options = s.conversion_options()
        self.assertTrue(options.enrich_formula and options.describe_pictures)
        self.assertFalse(options.enrich_chart)

    def test_a_file_from_the_morning_loses_charts_once(self):
        s = LauncherSettings.from_dict({"settings_version": 2, "enrich_formula": True, "enrich_chart": True, "describe_pictures": True})
        self.assertFalse(s.enrich_chart)
        self.assertTrue(s.enrich_formula and s.describe_pictures)
        self.assertIn("Charts as tables is off", s.upgrade_note)
        self.assertNotIn("Formulas as LaTeX and picture descriptions are now on", s.upgrade_note, "that step was already done")
        self.assertEqual(s.settings_version, SETTINGS_VERSION)

    def test_chart_tables_get_their_warning(self):
        from docling_launcher.chart_note import mark_chart_tables
        from docling_launcher.constants import CHART_TABLE_NOTE
        text = "\n".join([
            "Figure 3", "", "![Image](a.png)", "", "A curve.", "", "Line chart", "",
            "| C1 | l |", "|---|---|", "| 0 | 1.0 |", "",
            "Tableau 3 Caractéristiques", "", "| Profil | C3 |", "|---|---|", "| U1 | 1,00 |", "",
            "Bar chart", "", "No table here.", "",
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.md"
            path.write_text(text, encoding="utf-8")
            self.assertEqual(mark_chart_tables(path), 1)
            marked = path.read_text(encoding="utf-8")
            self.assertEqual(marked.count(CHART_TABLE_NOTE), 1)
            self.assertLess(marked.index("| 0 | 1.0 |"), marked.index(CHART_TABLE_NOTE), "under the chart table")
            self.assertLess(marked.index(CHART_TABLE_NOTE), marked.index("Tableau 3"), "not under the real table")
            self.assertEqual(mark_chart_tables(path), 0, "never twice")
            self.assertEqual(path.read_text(encoding="utf-8"), marked)

    def test_a_file_from_before_is_switched_on_once_and_says_so(self):
        old = {"enrich_formula": False, "enrich_chart": False, "describe_pictures": False, "theme": "dark",
               "ocr_mode": "off", "describe_prompt": PREVIOUS_DESCRIBE_PROMPTS[0]}
        s = LauncherSettings.from_dict(old)
        self.assertTrue(s.enrich_formula and s.describe_pictures)
        self.assertFalse(s.enrich_chart)
        self.assertEqual((s.theme, s.ocr_mode), ("dark", "off"), "every other choice is kept")
        self.assertIn("as asked on 2026-09-21", s.upgrade_note)
        self.assertEqual(s.describe_prompt, DEFAULT_DESCRIBE_PROMPT, "an old default wording is refreshed")
        self.assertEqual(s.settings_version, SETTINGS_VERSION)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"APPDATA": tmp}):
            path = s.save()
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["settings_version"], SETTINGS_VERSION)
        self.assertNotIn("upgrade_note", saved)

    def test_a_file_with_the_version_keeps_its_choices(self):
        s = LauncherSettings.from_dict({"settings_version": SETTINGS_VERSION, "enrich_formula": False,
                                        "describe_pictures": False, "describe_prompt": "Say what the pipe is for."})
        self.assertFalse(s.enrich_formula)
        self.assertFalse(s.describe_pictures)
        self.assertEqual(s.upgrade_note, "")
        self.assertEqual(s.describe_prompt, "Say what the pipe is for.", "the owner's own wording is never replaced")

    def test_a_proof_run_never_writes_the_switch_on(self):
        """The exe's self-test found this: the switch-on note saved the owner's settings from
        inside the constructor, before main() could raise the self-test flag."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "appdata" / "DoclingLauncher").mkdir(parents=True)
            settings_file = home / "appdata" / "DoclingLauncher" / "settings.json"
            before = json.dumps({"enrich_formula": False, "theme": "light"})
            settings_file.write_text(before, encoding="utf-8")
            with mock.patch.dict(os.environ, {"DOCLING_EXE": str(FAKE_DOCLING), "DOCLING_CONVERT_TOOL": str(ROOT / "tests" / "fake_docling.py"),
                                              "APPDATA": str(home / "appdata"), "DOCLING_LAUNCHER_SELFTEST": str(home / "report.json")}), \
                 mock.patch.object(updates, "latest_versions", return_value={}), \
                 mock.patch.object(app_module, "check_models", return_value=[]), \
                 mock.patch.object(app_module.launcher_update, "check", return_value=""), \
                 mock.patch.object(app_module, "gpu_status", return_value=environment.DependencyStatus("GPU", False, "stub")):
                import tkinter as tk
                root = tk.Tk()
                root.withdraw()
                try:
                    app = app_module.DoclingLauncherApp(root)
                    root.update()
                    self.assertTrue(app._selftest)
                    self.assertIn("as asked on 2026-09-21", app.log_text.get("1.0", "end"), "the note is still shown")
                    self.assertEqual(settings_file.read_text(encoding="utf-8"), before, "but nothing is written")
                    app._save_settings()
                    self.assertEqual(settings_file.read_text(encoding="utf-8"), before, "not even on an explicit save")
                finally:
                    try:
                        app.job.terminate()
                    except Exception:
                        pass
                    root.destroy()

    def test_the_window_logs_the_switch_on_and_writes_the_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "appdata" / "DoclingLauncher").mkdir(parents=True)
            settings_file = home / "appdata" / "DoclingLauncher" / "settings.json"
            settings_file.write_text(json.dumps({"enrich_formula": False, "describe_pictures": False, "theme": "light"}), encoding="utf-8")
            with mock.patch.dict(os.environ, {"DOCLING_EXE": str(FAKE_DOCLING), "DOCLING_CONVERT_TOOL": str(ROOT / "tests" / "fake_docling.py"),
                                              "APPDATA": str(home / "appdata")}), \
                 mock.patch.object(updates, "latest_versions", return_value={}), \
                 mock.patch.object(app_module, "check_models", return_value=[]), \
                 mock.patch.object(app_module.launcher_update, "check", return_value=""), \
                 mock.patch.object(app_module, "gpu_status", return_value=environment.DependencyStatus("GPU", False, "stub")):
                import tkinter as tk
                root = tk.Tk()
                root.withdraw()
                try:
                    app = app_module.DoclingLauncherApp(root)
                    root.update()
                    log = app.log_text.get("1.0", "end")
                    self.assertIn("as asked on 2026-09-21", log)
                    self.assertTrue(app.enrich_formula_var.get() and app.describe_pictures_var.get())
                    saved = json.loads(settings_file.read_text(encoding="utf-8"))
                    self.assertEqual(saved["settings_version"], SETTINGS_VERSION, "written down, so it happens once")
                    self.assertTrue(saved["enrich_formula"] and saved["describe_pictures"])
                    self.assertFalse(saved["enrich_chart"])
                    self.assertEqual(saved["theme"], "light")
                finally:
                    try:
                        app.job.terminate()
                    except Exception:
                        pass
                    root.destroy()


if __name__ == "__main__":
    unittest.main()
