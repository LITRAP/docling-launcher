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
        for flag in ("--enrich-formula", "--enrich-code", "--enrich-chart-extraction", "--enrich-picture-description"):
            self.assertIn(flag, plan.command, flag)

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
        self.assertEqual(groups[0], (out / "sub", [wrapper]))
        self.assertEqual(groups[1], (out, [root / "a.pdf"]))

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
    """The direct-Docling driver: the launcher's two model choices, the chart pairing rule."""

    def test_command_goes_through_the_driver_with_both_choices(self):
        plan = docling_cli.build_command_plan(
            [Path("a.pdf")], Path("o"),
            ConversionOptions(describe_pictures=True, describe_model="better", enrich_chart=True),
        )
        self.assertTrue(plan.command[1].endswith("convert_tool.py"), plan.command[:3])
        self.assertEqual(plan.command[plan.command.index("--describe-model") + 1], "better")
        self.assertEqual(plan.command[plan.command.index("--chart-model") + 1], "2b")
        self.assertIn("convert", plan.command)
        self.assertTrue(plan.preview.startswith("docling convert"), plan.preview)
        self.assertIn("described by the better model, charts by the 2b model", plan.preview)

    def test_chart_pairing_rule(self):
        C = ConversionOptions
        self.assertEqual(docling_cli.chart_model_for(C(enrich_chart=True)), "v4")
        self.assertEqual(docling_cli.chart_model_for(C(enrich_chart=True, describe_pictures=True, describe_model="small")), "v4")
        self.assertEqual(docling_cli.chart_model_for(C(enrich_chart=True, describe_pictures=True, describe_model="better")), "2b")

    def test_driver_hands_over_to_doclings_own_command_line(self):
        """The driver strips its options, swaps the defaults, then runs Docling's app()."""
        tool = ROOT / "src" / "docling_launcher" / "assets" / "convert_tool.py"
        code = (
            "import sys, runpy; sys.argv=['x']; mod = runpy.run_path(%r, run_name='tool'); "
            "mod['apply_choices']('better', '2b'); "
            "from docling.datamodel import pipeline_options as po; "
            "p = po.PdfPipelineOptions(); print(p.picture_description_options.repo_id, p.chart_extraction_options.model.value); "
            "print(po.ConvertPipelineOptions().picture_description_options.repo_id)"
        ) % str(tool)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        lines = [l for l in out.stdout.splitlines() if "granite" in l]
        self.assertEqual(lines[0], "ibm-granite/granite-vision-3.3-2b granite-vision")
        self.assertEqual(lines[1], "ibm-granite/granite-vision-3.3-2b")

    def test_model_rows_follow_the_active_choice(self):
        S = models.ModelStatus
        rows = [
            S("small", "a/small", "main", "describe_pictures:small", 0.5, None, None, None, None, "missing"),
            S("better", "a/better", "main", "describe_pictures:better", 6.0, None, None, None, None, "missing"),
            S("v4", "a/v4", "main", "enrich_chart:v4", 8.0, None, None, None, None, "missing"),
            S("2b", "a/2b", "main", "enrich_chart:2b", 6.2, None, None, None, None, "missing"),
        ]
        options = ConversionOptions(describe_pictures=True, describe_model="better", enrich_chart=True)

        def enabled(ability):
            name, _, choice = (ability or "").partition(":")
            if name == "describe_pictures":
                return options.describe_pictures and options.describe_model == choice
            if name == "enrich_chart":
                return options.enrich_chart and docling_cli.chart_model_for(options) == choice
            return True
        self.assertEqual([m.label for m in models.model_targets(rows, enabled)], ["better", "2b"])
