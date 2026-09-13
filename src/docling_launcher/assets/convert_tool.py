"""Runs INSIDE Docling's environment: the launcher's road into Docling, with what the
command line lacks.

    python convert_tool.py convert <docling args...>
        Docling's own command line, unchanged (its flags, files and names).

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


# ----------------------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    command, rest = argv[0], argv[1:]
    if command == "convert":
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
