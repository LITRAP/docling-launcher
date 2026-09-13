"""Guards for "who said what", round 6 (2026-09-13): the driver flags, the settings, the
window rows that appear only when the tick box is on, the word-by-word speaker
assignment, the pyannote-style grouping in assets/speakers_tool.py, and the model row.
Same conventions as test_launcher.py; nothing appears on screen and nothing of the
owner's is touched (APPDATA and the model folder are overridden)."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from docling_launcher import docling_cli, models, settings as settings_module  # noqa: E402
from docling_launcher.constants import MODELS, SPEAKER_ENGINES, SPEECH_LANGUAGES  # noqa: E402
from docling_launcher.docling_cli import ConversionOptions  # noqa: E402
from test_launcher import WindowFixture  # noqa: E402

ASSETS = ROOT / "src" / "docling_launcher" / "assets"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ASSETS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FlagTests(unittest.TestCase):
    """The driver is told the language, the engine and the head count - for media only."""

    def test_media_carries_the_launcher_flags_first(self):
        options = ConversionOptions(speech_language="fr", video_speakers=True, speaker_engine="best", speaker_count=4)
        plan = docling_cli.build_command_plan([Path("meeting.mp4")], Path("o"), options)
        after_convert = plan.command[plan.command.index("convert") + 1:plan.command.index("convert") + 7]
        self.assertEqual(after_convert, ["--launcher-language", "fr", "--launcher-speakers", "best", "--launcher-people", "4"])
        self.assertIn("--video-diarization", plan.command)
        docs = docling_cli.build_command_plan([Path("a.pdf")], Path("o"), options)
        self.assertFalse(any(arg.startswith("--launcher-") for arg in docs.command), "documents never see them")

    def test_defaults_send_the_engine_but_no_count_and_no_language(self):
        plan = docling_cli.build_command_plan([Path("talk.mp3")], Path("o"), ConversionOptions())
        self.assertIn("--launcher-speakers", plan.command)
        self.assertEqual(plan.command[plan.command.index("--launcher-speakers") + 1], "best")
        self.assertNotIn("--launcher-people", plan.command)
        self.assertNotIn("--launcher-language", plan.command)
        quiet = docling_cli.build_command_plan([Path("talk.mp3")], Path("o"), ConversionOptions(video_speakers=False, speech_language="en"))
        self.assertNotIn("--launcher-speakers", quiet.command)
        self.assertEqual(quiet.command[quiet.command.index("--launcher-language") + 1], "en")

    def test_settings_normalise_the_new_fields(self):
        raw = {"speaker_engine": "magic", "speaker_count": "abc", "speech_language": "klingon"}
        loaded = settings_module.LauncherSettings.from_dict(raw) if hasattr(settings_module.LauncherSettings, "from_dict") else None
        if loaded is None:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["APPDATA"] = tmp
                (Path(tmp) / "DoclingLauncher").mkdir()
                (Path(tmp) / "DoclingLauncher" / "settings.json").write_text(json.dumps(raw), encoding="utf-8")
                loaded = settings_module.LauncherSettings.load()
        self.assertEqual(loaded.speaker_engine, "best")
        self.assertEqual(loaded.speaker_count, 0)
        self.assertEqual(loaded.speech_language, "")
        options = loaded.conversion_options()
        self.assertEqual((options.speaker_engine, options.speaker_count, options.speech_language), ("best", 0, ""))

    def test_every_language_and_engine_has_a_label(self):
        self.assertEqual(SPEECH_LANGUAGES[0][0], "", "the first choice is the guess")
        self.assertTrue(all(name for _, name in SPEECH_LANGUAGES))
        self.assertEqual([e for e, _ in SPEAKER_ENGINES], ["best", "docling"])


class WordAssignmentTests(unittest.TestCase):
    """The driver's assign_speakers_by_word, on stand-in items shaped like Docling's."""

    class Word:
        def __init__(self, text, start, end):
            self.text, self.start_time, self.end_time = text, start, end

    class Item:
        def __init__(self, text, start, end, words=None, speaker=None):
            self.text, self.start_time, self.end_time, self.words, self.speaker = text, start, end, words, speaker

        def model_copy(self, update):
            copy = WordAssignmentTests.Item(self.text, self.start_time, self.end_time, self.words, self.speaker)
            for key, value in update.items():
                setattr(copy, key, value)
            return copy

    class Segment:
        def __init__(self, start, end, speaker):
            self.start_time, self.end_time, self.speaker = start, end, speaker

    class Diarization:
        def __init__(self, segments):
            self.segments = segments

    def setUp(self):
        self.tool = _load("convert_tool")

    def test_a_sentence_is_cut_where_the_speaker_changes(self):
        W, I, S = self.Word, self.Item, self.Segment
        words = [W(" On", 0.0, 0.3), W(" a", 0.3, 0.5), W(" décidé.", 0.5, 1.0), W(" Oui,", 1.2, 1.5), W(" oui.", 1.5, 1.9),
                 W(" Mais", 2.1, 2.4), W(" ici", 2.4, 2.8)]
        item = I("On a décidé. Oui, oui. Mais ici", 0.0, 2.8, words)
        turns = self.Diarization([S(0.0, 1.05, "SPEAKER_00"), S(1.1, 2.0, "SPEAKER_01"), S(2.05, 3.0, "SPEAKER_00")])
        out = self.tool.assign_speakers_by_word([item], turns)
        self.assertEqual([(o.speaker, o.text) for o in out],
                         [("SPEAKER_00", "On a décidé."), ("SPEAKER_01", "Oui, oui."), ("SPEAKER_00", "Mais ici")])
        self.assertEqual((out[1].start_time, out[1].end_time), (1.2, 1.9))

    def test_a_lone_short_word_stays_with_its_neighbours(self):
        W, I, S = self.Word, self.Item, self.Segment
        words = [W(" Les", 0.0, 0.3), W(" axes", 0.3, 0.5), W(" sont", 0.5, 0.7), W(" là.", 0.7, 1.0)]
        # the segmentation flickers to the other voice for one 0.2 s word
        turns = self.Diarization([S(0.0, 0.5, "SPEAKER_00"), S(0.5, 0.7, "SPEAKER_01"), S(0.7, 1.0, "SPEAKER_00")])
        out = self.tool.assign_speakers_by_word([I("Les axes sont là.", 0.0, 1.0, words)], turns)
        self.assertEqual([(o.speaker, o.text) for o in out], [("SPEAKER_00", "Les axes sont là.")])

    def test_words_in_a_gap_go_to_the_nearest_turn_and_never_lose_their_speaker(self):
        W, I, S = self.Word, self.Item, self.Segment
        words = [W(" Bon.", 0.0, 0.4), W(" Alors", 3.0, 3.3), W(" voilà.", 3.3, 3.8)]
        turns = self.Diarization([S(0.0, 0.5, "SPEAKER_00"), S(3.5, 4.0, "SPEAKER_01")])
        out = self.tool.assign_speakers_by_word([I("Bon. Alors voilà.", 0.0, 3.8, words)], turns)
        self.assertEqual([(o.speaker, o.text) for o in out], [("SPEAKER_00", "Bon."), ("SPEAKER_01", "Alors voilà.")])
        self.assertTrue(all(o.speaker for o in out))

    def test_a_cut_inside_a_phrase_moves_back_to_the_phrase_start(self):
        """The owner's meeting at 0:33: the listener began "parce que si je ne trompe pas"
        over the presenter's last words; the voice change was heard only from "trompe"."""
        W, I, S = self.Word, self.Item, self.Segment
        words = [W(" donc", 30.7, 30.9), W(" on", 30.9, 31.0), W(" cote", 31.0, 31.4), W(" d'après", 31.4, 31.8),
                 W(" ces", 31.8, 32.0), W(" axes", 32.0, 32.4),
                 W(" parce", 32.4, 32.6), W(" que", 32.6, 32.8), W(" si", 32.8, 33.0), W(" je", 33.0, 33.3), W(" ne", 33.3, 33.6),
                 W(" trompe", 33.6, 33.9), W(" pas", 33.9, 34.1), W(" avant", 34.1, 34.5), W(" mes", 34.5, 34.8), W(" vacances", 34.8, 35.5)]
        self.tool.PHRASE_STARTS.clear()
        self.tool.PHRASE_STARTS.update({id(words[0]), id(words[6])})  # Whisper's phrases began at "donc" and "parce"
        turns = self.Diarization([S(25.6, 33.6, "SPEAKER_00"), S(33.6, 37.8, "SPEAKER_02")])
        out = self.tool.assign_speakers_by_word([I("...", 30.7, 35.5, words)], turns)
        self.assertEqual([(o.speaker, o.text) for o in out],
                         [("SPEAKER_00", "donc on cote d'après ces axes"), ("SPEAKER_02", "parce que si je ne trompe pas avant mes vacances")])
        # too far back to be the same phrase: the cut stays where the voice changed
        self.tool.PHRASE_STARTS.clear()
        self.tool.PHRASE_STARTS.add(id(words[0]))
        out = self.tool.assign_speakers_by_word([I("...", 30.7, 35.5, words)], turns)
        self.assertEqual(out[0].text, "donc on cote d'après ces axes parce que si je ne")
        # a short interjection between the phrase start and the change is not swallowed
        self.tool.PHRASE_STARTS.update({id(words[6])})
        turns = self.Diarization([S(25.6, 32.8, "SPEAKER_00"), S(32.8, 33.3, "SPEAKER_01"), S(33.3, 37.8, "SPEAKER_02")])
        out = self.tool.assign_speakers_by_word([I("...", 30.7, 35.5, words)], turns)
        self.assertEqual([o.speaker for o in out], ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"])
        self.tool.PHRASE_STARTS.clear()

    def test_a_word_without_length_keeps_ten_milliseconds(self):
        W, I, S = self.Word, self.Item, self.Segment
        words = [W(" Voilà.", 5.0, 5.0)]  # Whisper does this now and then; Docling refuses end == start
        turns = self.Diarization([S(4.0, 6.0, "SPEAKER_01")])
        out = self.tool.assign_speakers_by_word([I("Voilà.", 5.0, 5.0, words)], turns)
        self.assertEqual(len(out), 1)
        self.assertGreater(out[0].end_time, out[0].start_time)

    def test_without_word_times_docling_rule_stands(self):
        I, S = self.Item, self.Segment
        turns = self.Diarization([S(0.0, 1.0, "SPEAKER_00"), S(1.0, 4.0, "SPEAKER_01")])
        out = self.tool.assign_speakers_by_word([I("Une phrase entière.", 0.5, 3.0, words=None)], turns)
        self.assertEqual([(o.speaker, o.text) for o in out], [("SPEAKER_01", "Une phrase entière.")])
        self.assertEqual(self.tool.assign_speakers_by_word(["x"], self.Diarization([])), ["x"], "no turns: untouched")


class GroupingTests(unittest.TestCase):
    """assets/speakers_tool.py without its models: the grouping and the time line."""

    def setUp(self):
        try:
            import numpy  # noqa: F401
            import sklearn  # noqa: F401
        except ImportError:
            self.skipTest("numpy/scikit-learn are Docling's; the tool runs in its environment")
        self.tool = _load("speakers_tool")

    def _voices(self, count, per_voice, seed=1):
        import numpy as np
        rng = np.random.default_rng(seed)
        centres = rng.normal(size=(count, 32))
        shared = rng.normal(size=32) * 3  # the "room": one strong component in every fingerprint
        vectors = [shared + centres[k] + rng.normal(scale=0.35, size=32) for k in range(count) for _ in range(per_voice)]
        return np.array(vectors, dtype="float32"), [k for k in range(count) for _ in range(per_voice)]

    def test_the_number_of_voices_is_found_and_the_groups_are_right(self):
        from sklearn.metrics import adjusted_rand_score
        for count in (1, 2, 3, 4):
            vectors, truth = self._voices(count, 60)
            labels = self.tool.cluster(vectors)
            self.assertEqual(len(set(labels.tolist())), count, f"{count} voices")
            self.assertGreater(adjusted_rand_score(truth, labels), 0.95)

    def test_a_known_head_count_is_honoured_and_labels_start_at_first_speaker(self):
        vectors, _ = self._voices(3, 40)
        labels = self.tool.cluster(vectors, num_speakers=2)
        self.assertEqual(len(set(labels.tolist())), 2)
        self.assertEqual(labels[0], 0, "SPEAKER_00 is whoever speaks first")
        self.assertEqual(len(self.tool.cluster(vectors[:2])), 2)
        self.assertEqual(len(set(self.tool.cluster(vectors[:2]).tolist())), 1, "too few fingerprints: one voice")

    def test_window_verdicts_become_turns_per_speaker(self):
        import numpy as np

        class Seg:  # the few numbers turns() reads from the segmentation model
            step, field_step, field, sample_rate = 16000, 270, 991, 16000

            def frame_time(self, frame):
                return (frame * self.field_step + self.field / 2) / self.sample_rate

        seg = Seg()
        frames = 589
        activity = np.zeros((3, frames, 3), dtype=np.float32)
        activity[:, : frames // 2, 0] = 1     # local voice 0 speaks the first half of every window
        activity[:, frames // 2:, 1] = 1      # local voice 1 the second half
        pairs = [(w, j) for w in range(3) for j in range(2)]
        labels = np.array([0, 1] * 3)
        turns = self.tool.turns(activity, pairs, labels, seg, total_samples=12 * 16000)
        speakers = sorted({who for _, _, who in turns})
        self.assertEqual(speakers, ["SPEAKER_00", "SPEAKER_01"])
        self.assertTrue(all(b - a >= self.tool.MIN_DURATION_ON for a, b, _ in turns))
        self.assertTrue(all(0 <= a < b <= 12.5 for a, b, _ in turns), turns)

    def test_models_present_needs_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.assertFalse(self.tool.models_present(folder))
            (folder / self.tool.SEGMENTATION_FILE).write_bytes(b"x")
            self.assertFalse(self.tool.models_present(folder))
            (folder / self.tool.EMBEDDING_FILE).write_bytes(b"x")
            self.assertTrue(self.tool.models_present(folder))


class ModelRowTests(unittest.TestCase):
    """The who-said-what models have a row of their own, checked offline without the hub."""

    def test_the_row_exists_and_follows_the_best_engine(self):
        row = next((m for m in MODELS if m[1] == "speakers:pyannote3"), None)
        self.assertIsNotNone(row)
        self.assertEqual(row[3], "video_speakers:best")
        status = models.ModelStatus(row[0], row[1], row[2], row[3], row[4], "pyannote3+wespeaker", "2026-09-13", None, None, "current")
        self.assertEqual(status.installed_text, "pyannote3+wespeaker")

    def test_models_tool_reports_missing_then_present(self):
        python = docling_cli.resolve_python()
        if not python:
            self.skipTest("Docling's python is not here")
        spec = json.dumps([["Who said what", "speakers:pyannote3", "release", 0.03]])
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, DOCLING_LAUNCHER_SPEAKER_MODELS=tmp, PYTHONIOENCODING="utf-8")
            out = subprocess.run([str(python), str(ASSETS / "models_tool.py"), "check-offline", spec, "-"],
                                 capture_output=True, text=True, env=env, timeout=120)
            row = json.loads(out.stdout.strip().splitlines()[-1])
            self.assertEqual(row["state"], "missing", out.stdout + out.stderr)
            for name in ("pyannote-segmentation-3.0.onnx", "wespeaker-resnet34-LM.onnx"):
                (Path(tmp) / name).write_bytes(b"0" * 2048)
            out = subprocess.run([str(python), str(ASSETS / "models_tool.py"), "check-offline", spec, "-"],
                                 capture_output=True, text=True, env=env, timeout=120)
            row = json.loads(out.stdout.strip().splitlines()[-1])
            self.assertEqual(row["state"], "current")
            self.assertEqual(row["installed_sha"], "pyannote3+wespeaker")
            self.assertTrue(row["installed_on"])


class WindowTests(WindowFixture):
    """The rows appear only while "Who said what" is ticked; presets carry the choices."""

    def test_engine_and_count_rows_follow_the_tick_box(self):
        app = self.app
        app.video_speakers_var.set(True)
        app._sync_speakers_state()
        self.assertTrue(app.speaker_engine_box.winfo_manager(), "engine row shown while ticked")
        self.assertTrue(app.speaker_count_box.winfo_manager())
        app.video_speakers_var.set(False)
        app._sync_speakers_state()
        self.assertFalse(app.speaker_engine_box.winfo_manager(), "hidden, not greyed, when it cannot matter")
        self.assertFalse(app.speaker_count_box.winfo_manager())
        app.video_speakers_var.set(True)
        app._sync_speakers_state()
        self.assertTrue(app.speaker_engine_box.winfo_manager(), "and back")

    def test_choices_reach_the_command_and_the_saved_settings(self):
        app = self.app
        app.video_speakers_var.set(True)
        app.speaker_engine_var.set("docling")
        app.speaker_count_var.set(3)
        app.speech_language_var.set("fr")
        options = app._settings_from_vars().conversion_options()
        self.assertEqual((options.speaker_engine, options.speaker_count, options.speech_language), ("docling", 3, "fr"))
        self.assertTrue(app._ability_enabled("video_speakers:docling"))
        self.assertFalse(app._ability_enabled("video_speakers:best"), "the best engine's models are not needed now")
        app.speaker_engine_var.set("best")
        self.assertTrue(app._ability_enabled("video_speakers:best"))
        app.video_speakers_var.set(False)
        self.assertFalse(app._ability_enabled("video_speakers:best"), "unticked: no engine needs its models")


if __name__ == "__main__":
    unittest.main()
