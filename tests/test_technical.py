"""Guards for the technical-document abilities, the speaker transcript, the model table
and the update dates. Same conventions as test_launcher.py; nothing appears on screen."""
from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docling_launcher import app as app_module, docling_cli, media, models, updates  # noqa: E402
from docling_launcher.constants import INPUT_FORMAT_GROUPS, MODELS, SUPPORTED_INPUT_EXTENSIONS  # noqa: E402
from docling_launcher.docling_cli import ConversionOptions  # noqa: E402


class TechnicalOptionsTests(unittest.TestCase):
    def test_each_ability_is_one_flag(self):
        base = ConversionOptions(keep_pictures=False)
        plan = docling_cli.build_command_plan([Path("a.pdf")], Path("o"), base)
        for flag in ("--image-export-mode", "--enrich-formula", "--enrich-code", "--enrich-chart-extraction",
                     "--enrich-picture-description", "--asr-model", "--video-diarization"):
            self.assertNotIn(flag, plan.command, flag)
        self.assertIn("--num-threads", plan.command)
        full = ConversionOptions(keep_pictures=True, enrich_formula=True, enrich_chart=True, describe_pictures=True)
        plan = docling_cli.build_command_plan([Path("a.pdf")], Path("o"), full)
        self.assertEqual(plan.command[plan.command.index("--image-export-mode") + 1], "referenced")
        for flag in ("--enrich-formula", "--enrich-code", "--enrich-chart-extraction"):
            self.assertIn(flag, plan.command, flag)
        self.assertNotIn("--enrich-picture-description", plan.command, "descriptions are a pass of their own")
        self.assertIn("then pictures described by the better model", plan.preview)

    def test_media_gets_speech_flags_and_vtt_only_when_media_is_present(self):
        options = ConversionOptions(speech_model="turbo", video_speakers=True)
        docs = docling_cli.build_command_plan([Path("a.pdf")], Path("o"), options)
        self.assertNotIn("--asr-model", docs.command)
        self.assertNotIn("--video-diarization", docs.command)
        self.assertNotIn("vtt", docs.command)
        plan = docling_cli.build_command_plan([Path("talk.mp3"), Path("clip.mp4")], Path("o"), options)
        self.assertEqual(plan.command[plan.command.index("--asr-model") + 1], "whisper_turbo")
        self.assertIn("--video-diarization", plan.command)
        self.assertEqual(plan.command[plan.command.index("--video-sampling-mode") + 1], "scene")
        self.assertIn("vtt", plan.command, "speakers live only in the subtitle output")
        quiet = docling_cli.build_command_plan([Path("talk.mp3")], Path("o"), ConversionOptions(video_speakers=False))
        self.assertNotIn("--video-diarization", quiet.command)
        self.assertNotIn("vtt", quiet.command)

    def test_stand_ins_keep_the_sources_output_folder(self):
        root, out = Path(r"C:\in"), Path(r"D:\out")
        files = [root / "sub" / "talk.mp3", root / "a.pdf"]
        wrapper = Path(r"C:\temp\wrap\x\talk.mkv")
        groups = docling_cli.group_sources(files, root, out, "mirror", {files[0]: wrapper})
        self.assertEqual(groups[0], (out / "sub", True, [wrapper]))
        self.assertEqual(groups[1], (out, True, [root / "a.pdf"]))

    def test_transcript_by_speaker(self):
        vtt = ("WEBVTT\n\n00:00:00.000 --> 00:00:03.000\n<v SPEAKER_01>Good morning.\n\n"
               "00:00:03.500 --> 00:00:05.000\n<v SPEAKER_01>Let us begin.\n\n"
               "00:01:05.000 --> 00:01:09.000\n<v SPEAKER_00>Thank you.\n")
        text = media.speakers_markdown(vtt, "meeting")
        self.assertEqual(text.splitlines()[0], "# meeting")
        self.assertIn("**Speaker 1** (00:00)  \nGood morning. Let us begin.", text)
        self.assertIn("**Speaker 2** (01:05)  \nThank you.", text)
        self.assertIsNone(media.speakers_markdown("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nno voices\n", "x"))

    def test_input_format_table_matches_what_is_picked_up(self):
        listed = {"." + ext.strip() for _, types, _ in INPUT_FORMAT_GROUPS for ext in types.split(",")}
        self.assertEqual(listed, SUPPORTED_INPUT_EXTENSIONS, "the table the owner reads must equal the filter")

    def test_how_to_use_covers_every_ability(self):
        text = "\n".join(line for _, line in app_module.HOW_TO_USE)
        for phrase in ("Keep pictures", "Formulas as LaTeX", "Charts as tables", "Describe each picture",
                       "Who said what", "Speech model", "OCR", "Update", "Go back", "Stop", "Mirror", "Beside"):
            self.assertIn(phrase, text, phrase)


class ModelTests(unittest.TestCase):
    TOOL = ROOT / "src" / "docling_launcher" / "assets" / "models_tool.py"

    def _run(self, cache: Path, *args) -> list[dict]:
        env = dict(os.environ, HF_HUB_CACHE=str(cache), HF_HUB_OFFLINE="1")
        out = subprocess.run([sys.executable, str(self.TOOL), *args], capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        return [json.loads(line) for line in out.stdout.splitlines() if line.startswith("{")]

    def test_installed_missing_and_half_downloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            repo = cache / "models--acme--good"
            (repo / "refs").mkdir(parents=True)
            (repo / "refs" / "main").write_text("abcdef1234567890")
            (repo / "snapshots" / "abcdef1234567890").mkdir(parents=True)
            (repo / "snapshots" / "abcdef1234567890" / "model.safetensors").write_bytes(b"x")
            (repo / "blobs").mkdir()
            half = cache / "models--acme--half"
            (half / "refs").mkdir(parents=True)
            (half / "refs" / "main").write_text("1111111111111111")
            (half / "snapshots" / "1111111111111111").mkdir(parents=True)
            (half / "snapshots" / "1111111111111111" / "config.json").write_text("{}")
            (half / "blobs").mkdir()
            (half / "blobs" / "deadbeef.incomplete").write_bytes(b"...")
            spec = json.dumps([["Good", "acme/good", "main", 0.1], ["Half", "acme/half", "main", 1.0],
                               ["None", "acme/none", "main", 2.0]])
            rows = {r["repo"]: r for r in self._run(cache, "check-offline", spec, "-")}
            self.assertEqual(rows["acme/good"]["state"], "unchecked")
            self.assertEqual(rows["acme/good"]["installed_sha"], "abcdef1234567890")
            self.assertIsNotNone(rows["acme/good"]["installed_on"])
            self.assertEqual(rows["acme/half"]["state"], "missing", "a download in progress is not installed")
            self.assertEqual(rows["acme/none"]["state"], "missing")

    def test_targets_are_newer_models_and_missing_ones_that_are_needed(self):
        S = models.ModelStatus
        rows = [
            S("Layout", "a/layout", "main", None, 0.2, "s", "d", "s", "d", "current"),
            S("Formula", "a/formula", "main", "enrich_formula", 0.6, None, None, "s", "d", "missing"),
            S("Chart", "a/chart", "main", "enrich_chart", 8.0, None, None, "s", "d", "missing"),
            S("Pictures", "a/pic", "main", "describe_pictures", 0.5, "old", "d", "new", "d2", "newer"),
        ]
        enabled = {"enrich_formula": True, "enrich_chart": False}
        picked = models.model_targets(rows, lambda ability: ability is None or enabled.get(ability, False))
        self.assertEqual([m.label for m in picked], ["Formula", "Pictures"])
        self.assertEqual(rows[2].state_text(needed=False), "Not downloaded (8.0 GB)")
        self.assertEqual(rows[1].state_text(needed=True), "Not downloaded (0.6 GB) — needed by a ticked ability")

    def test_model_table_matches_the_installed_docling(self):
        """The repos and revisions in constants.MODELS must be the ones Docling really loads."""
        by_repo = {repo: (revision, gb) for _, repo, revision, _, gb in MODELS}
        from docling.datamodel.pipeline_options import LayoutOptions, smolvlm_picture_description
        from docling.models.stages.code_formula.code_formula_model import CodeFormulaModel
        from docling.models.stages.table_structure.table_structure_model import TableStructureModel
        from docling.models.stages.chart_extraction.granite_vision import ChartExtractionModelGraniteVisionV4
        self.assertIn(LayoutOptions().model_spec.repo_id, by_repo)
        self.assertIn(smolvlm_picture_description.repo_id, by_repo)
        self.assertIn(ChartExtractionModelGraniteVisionV4._model_repo_id, by_repo)
        self.assertIn(CodeFormulaModel._model_repo_folder.replace("--", "/"), by_repo)
        self.assertIn(TableStructureModel._model_repo_folder.replace("--", "/"), by_repo)
        table_src = inspect.getsource(TableStructureModel)
        self.assertIn(f'revision="{by_repo["docling-project/docling-models"][0]}"', table_src)
        # the chart model is pinned to a commit; deleting any other copy is safe, deleting this one is not
        self.assertEqual(by_repo[ChartExtractionModelGraniteVisionV4._model_repo_id][0],
                         ChartExtractionModelGraniteVisionV4._model_repo_revision)


class UpdateDateTests(unittest.TestCase):
    def test_installed_info_carries_a_date(self):
        info = updates.installed_info(["docling"])["docling"]
        self.assertIsNotNone(info)
        version, when = info
        self.assertRegex(when, r"^\d{4}-\d{2}-\d{2}$")

    def test_gpu_tag(self):
        self.assertEqual(updates.gpu_tag("2.14.0+cu130"), "cu130")
        self.assertIsNone(updates.gpu_tag("2.14.0+cpu"))
        self.assertIsNone(updates.gpu_tag(None))


if __name__ == "__main__":
    unittest.main()


class DriverTests(unittest.TestCase):
    """The direct-Docling driver: every run goes through it; OCR is decided per file."""

    def test_command_goes_through_the_driver(self):
        plan = docling_cli.build_command_plan([Path("a.pdf")], Path("o"), ConversionOptions())
        self.assertTrue(plan.command[1].endswith(("convert_tool.py", "fake_docling.py")), plan.command[:3])
        self.assertEqual(plan.command[2], "convert")
        self.assertTrue(plan.preview.startswith("docling convert"), plan.preview)

    def test_ocr_is_decided_per_file_in_auto_mode(self):
        C = ConversionOptions
        chars = {Path("scan.pdf"): 0, Path("digital.pdf"): 900}
        self.assertTrue(docling_cli.ocr_wanted(Path("scan.pdf"), C(ocr_mode="auto"), chars))
        self.assertFalse(docling_cli.ocr_wanted(Path("digital.pdf"), C(ocr_mode="auto"), chars))
        self.assertTrue(docling_cli.ocr_wanted(Path("unknown.pdf"), C(ocr_mode="auto"), chars), "unknown -> read it")
        self.assertTrue(docling_cli.ocr_wanted(Path("photo.jpg"), C(ocr_mode="auto"), chars))
        self.assertFalse(docling_cli.ocr_wanted(Path("report.docx"), C(ocr_mode="auto"), chars))
        self.assertTrue(docling_cli.ocr_wanted(Path("digital.pdf"), C(ocr_mode="always"), chars))
        self.assertFalse(docling_cli.ocr_wanted(Path("scan.pdf"), C(ocr_mode="off"), chars))
        # the decision becomes a separate Docling run per folder
        root, out = Path(r"C:\in"), Path(r"D:\out")
        files = [root / "scan.pdf", root / "digital.pdf", root / "photo.jpg"]
        plans = docling_cli.build_batch_plans(files, root, out, "flat", C(ocr_mode="auto"), None, {files[0]: 0, files[1]: 900})
        self.assertEqual(len(plans), 2)
        by_ocr = {("--no-ocr" not in p.command): sorted(s.name for s in p.sources) for p in plans}
        self.assertEqual(by_ocr[True], ["photo.jpg", "scan.pdf"])
        self.assertEqual(by_ocr[False], ["digital.pdf"])

    def test_already_converted_means_fresh_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "a.pdf"
            source.write_bytes(b"%PDF")
            self.assertFalse(docling_cli.already_converted(source, folder, ["md"]))
            (folder / "a.md").write_text("# a")
            self.assertTrue(docling_cli.already_converted(source, folder, ["md"]))
            os.utime(folder / "a.md", (1, 1))  # older than the source
            self.assertFalse(docling_cli.already_converted(source, folder, ["md"]))

    def test_model_rows_follow_the_active_choice(self):
        S = models.ModelStatus
        rows = [
            S("small", "a/small", "main", "describe_pictures:small", 0.5, None, None, None, None, "missing"),
            S("better", "a/better", "main", "describe_pictures:better", 6.0, None, None, None, None, "missing"),
            S("chart", "a/chart", "main", "enrich_chart", 8.0, None, None, None, None, "missing"),
        ]

        def enabled(ability):
            name, _, choice = (ability or "").partition(":")
            if name == "describe_pictures":
                return choice == "better"
            return name == "enrich_chart"
        self.assertEqual([m.label for m in models.model_targets(rows, enabled)], ["better", "chart"])
