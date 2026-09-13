"""Runs INSIDE Docling's environment: the launcher's road into Docling, with what the
command line lacks.

    python convert_tool.py convert [--launcher-speakers best|docling] [--launcher-people N]
                                   [--launcher-language xx] <docling args...>
        Docling's own command line, unchanged (its flags, files and names), after the
        launcher's own flags, which reach into Docling where its command line cannot:
        --launcher-language  the language Whisper is told instead of guessing from the
                             first 30 seconds (a file that opens with silence or music
                             is otherwise guessed wrong, whole);
        --launcher-speakers  "best" replaces Docling's speaker separation with the
                             pyannote 3 pipeline in speakers_tool.py (started while
                             Whisper still transcribes, so it costs no extra wait), and
                             assigns speakers word by word instead of sentence by sentence;
        --launcher-people    how many people speak, when known (both engines).
        Whisper is also told, explicitly, not to feed each window its previous text. Docling
        passes None there, which Whisper already treats as "off" (checked 2026-09-13: the
        same 54-minute meeting came out 99.85 % identical either way); with real carrying
        a 4-minute test lost 14 seconds of speech, so the choice is now written down.

    python convert_tool.py probe <files...>
        One JSON line per file: {"file", "kind", "pages", "text_chars"} — whether a PDF
        carries a text layer, so the launcher can decide where OCR is needed.

    python convert_tool.py describe --model better|small --threads N <markdown files...>
        Describes every picture linked from the Markdown files with Docling's own describing
        model, run directly on the saved PNGs, and writes the text under each picture.
        Prints "described <n>/<total>" as it goes and "DONE <pictures> <files>" at the end.

Why a separate describe pass (2026-09-12): Docling's command line cannot choose the
describing model; inside its pipeline the better model (6 GB) and the chart model (8 GB)
fill a 16 GB card together (11 minutes for nine pages); and its video pipeline never
describes frames at all. Run afterwards on the pictures Docling saved, the describer has
the card to itself, every picture of every format gets its text, and the large chart
model stays. Shipped inside the exe as an asset; a single file with no launcher imports.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

DESCRIBE_PROMPT = (
    "Describe this figure for a technical reader in a few precise sentences: what it shows, "
    "the axes or labels, the key values or components, and what it means. If it contains "
    "text, quote the important text. Do not speculate beyond what is visible."
)
DESCRIBE_MODELS = {
    "better": "ibm-granite/granite-vision-3.3-2b",
    "small": "HuggingFaceTB/SmolVLM-256M-Instruct",
}
IMAGE_LINE = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)\s*$")
BATCH = 4


# ----------------------------------------------------------------------------- probe

def probe(files: list[str]) -> None:
    for name in files:
        path = Path(name)
        row = {"file": name, "kind": path.suffix.lower().lstrip("."), "pages": None, "text_chars": None}
        if path.suffix.lower() == ".pdf":
            try:
                import pypdfium2 as pdfium
                pdf = pdfium.PdfDocument(str(path))
                pages = len(pdf)
                chars = 0
                # The first pages tell: a scan has none, a digital document has hundreds.
                for index in range(min(pages, 5)):
                    page = pdf[index]
                    text = page.get_textpage().get_text_range()
                    chars += len(text.strip())
                    page.close()
                pdf.close()
                row["pages"], row["text_chars"] = pages, chars
            except Exception as exc:
                row["error"] = str(exc)[:200]
        print(json.dumps(row), flush=True)


# ----------------------------------------------------------------------------- describe

def _cached(repo: str) -> bool:
    """Is the model's main revision in the local cache, with its weights?"""
    from huggingface_hub.constants import HF_HUB_CACHE
    folder = Path(HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))
    ref = folder / "refs" / "main"
    if not ref.is_file():
        return False
    snapshot = folder / "snapshots" / ref.read_text(encoding="utf-8").strip()
    return snapshot.is_dir() and any(snapshot.glob("*.safetensors")) and not any((folder / "blobs").glob("*.incomplete"))


def _image_path(link: str, markdown: Path) -> Path | None:
    link = link.strip()
    if link.startswith("file:"):
        candidate = Path(url2pathname(unquote(urlparse(link).path)))
        if candidate.is_file():
            return candidate
        # "file:///C:/x" parses to "/C:/x" on Windows
        stripped = Path(unquote(urlparse(link).path).lstrip("/"))
        return stripped if stripped.is_file() else None
    candidate = (markdown.parent / unquote(link)).resolve()
    return candidate if candidate.is_file() else None


def describe(model_name: str, threads: int, files: list[str], prompt: str = "") -> int:
    from PIL import Image
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.pipeline_options import PictureDescriptionVlmOptions
    from docling.models.stages.picture_description.picture_description_vlm_model import (
        PictureDescriptionVlmModel,
    )

    jobs: list[tuple[Path, list[tuple[int, Path]]]] = []  # (markdown, [(line index, image)])
    for name in files:
        markdown = Path(name)
        if not markdown.is_file():
            continue
        lines = markdown.read_text(encoding="utf-8").splitlines()
        found = []
        for index, line in enumerate(lines):
            match = IMAGE_LINE.match(line)
            if match:
                image = _image_path(match.group(1), markdown)
                if image:
                    found.append((index, image))
        if found:
            jobs.append((markdown, found))
    total = sum(len(found) for _, found in jobs)
    print(f"describing {total} picture(s) in {len(jobs)} file(s) with the {model_name} model", flush=True)
    if not total:
        print("DONE 0 0", flush=True)
        return 0

    repo = DESCRIBE_MODELS[model_name]
    if _cached(repo):
        # Docling's own downloader would fetch the WHOLE repository (SmolVLM ships 3 GB of
        # other runtimes' formats). The files this machine loads are already here: offline.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
    options = PictureDescriptionVlmOptions(repo_id=repo, prompt=prompt.strip() or DESCRIBE_PROMPT)
    # A mild brake on repeats: the 2B model can stutter on busy figures otherwise.
    options.generation_config.update({"max_new_tokens": 320, "repetition_penalty": 1.15})
    started = time.time()
    model = PictureDescriptionVlmModel(
        enabled=True, enable_remote_services=False, artifacts_path=None, options=options,
        accelerator_options=AcceleratorOptions(device="auto", num_threads=threads),
    )
    print(f"describing model ready on {model.device} in {time.time() - started:.0f} s", flush=True)

    done = 0
    for markdown, found in jobs:
        lines = markdown.read_text(encoding="utf-8").splitlines()
        texts: dict[int, str] = {}
        for start in range(0, len(found), BATCH):
            chunk = found[start:start + BATCH]
            images = []
            for _, image in chunk:
                with Image.open(image) as picture:
                    images.append(picture.convert("RGB"))
            for (index, _), text in zip(chunk, model._annotate_images(images)):
                clean = re.sub(r"<end_of_utteranc?e?>?", "", text).strip()
                if clean:
                    texts[index] = clean
                done += 1
            print(f"described {done}/{total}", flush=True)
        if texts:
            output = []
            for index, line in enumerate(lines):
                output.append(line)
                if index in texts:
                    output.extend(["", texts[index]])
            markdown.write_text("\n".join(output) + "\n", encoding="utf-8")
    print(f"DONE {done} {len(jobs)}", flush=True)
    return 0


# ----------------------------------------------------------------------------- speech

def _patch_speech(language: str) -> None:
    """Every Whisper preset Docling's command line can pick: the language, and no carrying
    of the previous window's text, said explicitly (see the module docstring)."""
    from docling.datamodel import asr_model_specs as specs
    from docling.datamodel.pipeline_options_asr_model import InlineAsrNativeWhisperOptions
    for name in dir(specs):
        preset = getattr(specs, name)
        if isinstance(preset, InlineAsrNativeWhisperOptions):
            preset.condition_on_previous_text = False
            if language:
                preset.language = language


def _patch_speakers(engine: str, people: int) -> None:
    """Docling's video pipeline calls diarize() after Whisper and assign_speakers() on
    whole sentences; both are replaced on the pipeline module, which imported them by name."""
    import threading
    from docling.pipeline import video_pipeline
    from docling.utils import speaker_diarization as original

    started: dict[str, threading.Thread] = {}
    answers: dict[str, object] = {}

    def best(wav_path):
        """speakers_tool on the WAV -> Docling's DiarizationResult."""
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import speakers_tool
        turns, found = speakers_tool.diarize(Path(wav_path), people or None, log=lambda line: print(line, flush=True))
        return original.DiarizationResult(
            segments=[original.SpeakerSegment(a, b, who) for a, b, who in turns],
            num_speakers=found,
            speaker_ids=sorted({who for _, _, who in turns}),
        )

    def run_early(wav_path):
        try:
            answers[str(wav_path)] = best(wav_path)
        except Exception as exc:  # reported by diarize() below, on the pipeline's thread
            answers[str(wav_path)] = exc

    extract = video_pipeline._extract_audio

    def extract_and_start(video_path, wav_path):
        ok = extract(video_path, wav_path)
        if ok and engine == "best":
            thread = threading.Thread(target=run_early, args=(wav_path,), daemon=True, name="speakers")
            started[str(wav_path)] = thread
            thread.start()
        return ok

    def diarize(wav_path, num_speakers=None, accelerator_device="auto"):
        key = str(wav_path)
        if key in started:
            started.pop(key).join()
            answer = answers.pop(key)
            if isinstance(answer, Exception):
                raise answer
            return answer
        if engine == "best":
            return best(wav_path)
        return original.diarize(wav_path, num_speakers=people or num_speakers, accelerator_device=accelerator_device)

    video_pipeline._extract_audio = extract_and_start
    video_pipeline.diarize = diarize
    video_pipeline.assign_speakers = assign_speakers_by_word


def assign_speakers_by_word(items, diarization):
    """Docling's assign_speakers gives a whole sentence the speaker who overlaps it most,
    so "oui, oui" from the listener vanishes into the presenter's block. Here every word
    goes to the speaker talking at its midpoint and a sentence is cut where the speaker
    changes; a lone word under 0.3 s between two runs of the same speaker stays with them
    (Whisper's word times are about that precise). Sentences without word times keep
    Docling's rule."""
    segments = sorted(diarization.segments, key=lambda s: s.start_time) if diarization and diarization.segments else []
    if not segments:
        return items
    out = []
    for item in items:
        words = [w for w in (item.words or []) if w.start_time is not None and w.end_time is not None]
        if not words:
            out.append(_by_overlap(item, segments))
            continue
        labels = []
        previous = None
        for word in words:
            previous = _speaker_at((word.start_time + word.end_time) / 2, segments, previous)
            labels.append(previous)
        labels = _smooth(words, labels)
        start = 0
        for index in range(1, len(words) + 1):
            if index == len(words) or labels[index] != labels[start]:
                run = words[start:index]
                text = "".join(w.text for w in run).strip()
                if text:
                    # Whisper gives a stray word no length at times; Docling refuses a
                    # zero-length item (and the word with it), so give it 10 ms.
                    end = max(run[-1].end_time, run[0].start_time + 0.01)
                    out.append(item.model_copy(update={
                        "text": text, "start_time": run[0].start_time, "end_time": end,
                        "speaker": labels[start], "words": run,
                    }))
                start = index
    return out


def _speaker_at(moment, segments, previous):
    covering = [s for s in segments if s.start_time <= moment <= s.end_time]
    if covering:
        if previous and any(s.speaker == previous for s in covering):
            return previous
        return max(covering, key=lambda s: s.end_time - s.start_time).speaker
    # Between turns (or in a gap the segmentation closed): the nearest turn within a
    # second, else whoever was speaking - never a word without a speaker.
    nearest = min(segments, key=lambda s: min(abs(s.start_time - moment), abs(s.end_time - moment)))
    if min(abs(nearest.start_time - moment), abs(nearest.end_time - moment)) <= 1.0:
        return nearest.speaker
    return previous or nearest.speaker


def _smooth(words, labels):
    labels = list(labels)
    for i in range(1, len(labels) - 1):
        if labels[i - 1] == labels[i + 1] != labels[i] and words[i].end_time - words[i].start_time < 0.3:
            labels[i] = labels[i - 1]
    return labels


def _by_overlap(item, segments):
    start = item.start_time or 0.0
    end = item.end_time or start
    best_speaker, best_overlap = None, 0.0
    for s in segments:
        overlap = max(0.0, min(end, s.end_time) - max(start, s.start_time))
        if overlap > best_overlap:
            best_speaker, best_overlap = s.speaker, overlap
    return item.model_copy(update={"speaker": best_speaker}) if best_speaker else item


# ----------------------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    command, rest = argv[0], argv[1:]
    if command == "convert":
        engine, people, language = "", 0, ""
        while rest and rest[0].startswith("--launcher-"):
            flag = rest.pop(0)
            value = rest.pop(0) if rest else ""
            if flag == "--launcher-speakers":
                engine = value
            elif flag == "--launcher-people":
                people = int(value or 0)
            elif flag == "--launcher-language":
                language = value
        if any(arg in ("--asr-model", "--video-diarization") for arg in rest) or language:
            _patch_speech(language)
        if "--video-diarization" in rest and (engine or people):
            _patch_speakers(engine, people)
        sys.argv = ["docling", "convert", *rest]
        from docling.cli.main import app
        app()
        return 0
    if command == "probe":
        probe(rest)
        return 0
    if command == "describe":
        model_name, threads, prompt = "better", 8, ""
        while rest and rest[0].startswith("--"):
            flag = rest.pop(0)
            if flag == "--model" and rest:
                model_name = rest.pop(0)
            elif flag == "--threads" and rest:
                threads = int(rest.pop(0))
            elif flag == "--prompt" and rest:
                prompt = rest.pop(0)
        if model_name not in DESCRIBE_MODELS:
            print(f"unknown describing model {model_name}")
            return 2
        return describe(model_name, threads, rest, prompt)
    print(f"convert_tool: unknown command {command}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
