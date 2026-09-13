"""The update safety check: after Docling or a model is updated, convert a known document
set and compare with how it went before. Docling 2.126 made text PDFs three times slower
without a word of warning; this is the launcher noticing such a thing before the owner
converts a thousand pages.

The set: two pages of a scientific paper (table, pie chart, figures) and a rendered scan
(OCR). What is measured: words in the Markdown, table rows, and seconds. The first run
becomes the baseline; every later run is compared with it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import shutil
import tempfile
import time
from typing import Callable

from .assets import asset_path
from .docling_cli import ConversionOptions, ProcessJob, build_command_plan, stream_process, tidy_docling_line


@dataclass(frozen=True)
class Measurement:
    words: int
    table_rows: int
    scan_words: int
    seconds: float
    docling: str

    def to_dict(self) -> dict:
        return asdict(self)


def run_reference(log: Callable[[str], None], job: ProcessJob | None, docling_version: str) -> Measurement | None:
    """Convert the reference set into a throw-away folder with a fixed, plain set of options
    (OCR on for the scan, off for the paper, no enrichments), and measure."""
    pdf, scan = asset_path("reference.pdf"), asset_path("reference_scan.png")
    if not pdf.exists() or not scan.exists():
        log("The reference documents are missing from this build.")
        return None
    folder = Path(tempfile.mkdtemp(prefix="docling_reference_"))
    try:
        started = time.time()
        options = ConversionOptions(formats=("md",), ocr_mode="auto", keep_pictures=False)
        paper = build_command_plan([pdf], folder, options, ocr=False)
        code = stream_process(paper.command, paper.env, log, job=job, cwd=folder, tidy=tidy_docling_line)
        if code != 0:
            log(f"Reference paper failed (exit code {code}).")
            return None
        image = build_command_plan([scan], folder, options, ocr=True)
        code = stream_process(image.command, image.env, log, job=job, cwd=folder, tidy=tidy_docling_line)
        if code != 0:
            log(f"Reference scan failed (exit code {code}).")
            return None
        seconds = time.time() - started
        paper_md = (folder / f"{pdf.stem}.md").read_text(encoding="utf-8", errors="replace")
        scan_md = (folder / f"{scan.stem}.md").read_text(encoding="utf-8", errors="replace")
        return Measurement(
            words=len(paper_md.split()),
            table_rows=sum(1 for line in paper_md.splitlines() if line.startswith("|")),
            scan_words=len(scan_md.split()),
            seconds=round(seconds, 1),
            docling=docling_version,
        )
    except OSError as exc:
        log(f"Reference check could not read its results: {exc}")
        return None
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def compare(baseline: dict, now: Measurement) -> tuple[bool, str]:
    """(fine?, sentence). Words within 5 %, the same table rows, the scan still read, and no
    more than twice the time count as fine."""
    problems = []
    words_before = int(baseline.get("words", 0) or 0)
    if words_before and abs(now.words - words_before) > 0.05 * words_before:
        problems.append(f"words {words_before} -> {now.words}")
    if int(baseline.get("table_rows", 0) or 0) != now.table_rows:
        problems.append(f"table rows {baseline.get('table_rows')} -> {now.table_rows}")
    if int(baseline.get("scan_words", 0) or 0) and now.scan_words < 0.8 * int(baseline["scan_words"]):
        problems.append(f"scan words {baseline.get('scan_words')} -> {now.scan_words}")
    before_s = float(baseline.get("seconds", 0) or 0)
    if before_s and now.seconds > 2 * before_s:
        problems.append(f"time {before_s:.0f} s -> {now.seconds:.0f} s")
    if problems:
        return False, "Reference check after the update: " + "; ".join(problems) + ". Consider Go back."
    return True, (f"Reference check: as before ({now.words} words, {now.table_rows} table rows, "
                  f"scan read, {now.seconds:.0f} s; was {before_s:.0f} s with Docling {baseline.get('docling', '?')}).")
