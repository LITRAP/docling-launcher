"""What is in the chosen files, and how long the ticked abilities will take on this machine.

The Convert tab's "What's in these documents?" strip (2026-09-21, the owner's idea) shows
plain-word tick boxes for the abilities and, beside them, what the launcher found in the
files (pages, scanned pages, recordings) and an estimate of the time - so the price of
each tick is visible before Run is pressed.

The estimate is a sum of per-unit costs seeded from measurements on the owner's machine
(RTX A4000, 2026-09-21, a 68-page standard and a 54-minute meeting), multiplied by a
machine factor the launcher learns from its own batches (actual / estimated, smoothed).
It is an "about"; it says so.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .constants import MEDIA_INPUT_EXTENSIONS

SCAN_TEXT_CHARS = 50  # fewer characters on the first pages than this: a scan (docling_cli agrees)

# Seconds per unit on the reference machine, GPU in use (the 68-page standard: plain 41 s,
# with formulas 82 s, with formulas and charts 508 s; 33 descriptions 421 s; five OCR pages
# 5.8 s; the 54-minute meeting 377 s with speakers beside Whisper).
START_SECONDS = 10.0              # Docling's own start and the layout model, once per batch
SECONDS_PER_PAGE = 0.45           # layout, tables, text
SECONDS_PER_OCR_PAGE = 1.2        # whole-page OCR
SECONDS_PER_FORMULA_PAGE = 0.6    # formula & code model
SECONDS_PER_CHART_PAGE = 6.3      # the 8 GB chart model - the expensive tick
SECONDS_PER_PICTURE = 13.0        # the better describing model, per picture
DESCRIBE_START_SECONDS = 20.0     # loading that model, once per batch
PICTURES_PER_PAGE = 0.5           # until the launcher has seen this machine's documents
SECONDS_PER_MEDIA_SECOND = 0.12   # Whisper turbo with speakers beside it
SECONDS_PER_OTHER_FILE = 2.0      # Word, PowerPoint, Excel, HTML ... without a page count


@dataclass
class Findings:
    files: int = 0
    pdfs: int = 0
    pages: int = 0
    scanned_pages: int = 0        # pages of PDFs that carry no text layer
    scanned_pdfs: int = 0
    images: int = 0               # picture files (always OCR)
    media: int = 0
    media_seconds: float = 0.0
    others: int = 0               # Word, PowerPoint, Excel, HTML, ...
    unknown_pdfs: int = 0         # could not be looked at
    capped: bool = False          # more files than were looked at

    def summary(self) -> str:
        """One line in plain words: '68 pages · 2 scanned · 1 recording (54 min)'."""
        parts = []
        if self.pdfs:
            parts.append(f"{self.pages} page{'s' if self.pages != 1 else ''} in {self.pdfs} PDF{'s' if self.pdfs != 1 else ''}")
            if self.scanned_pages:
                parts.append(f"{self.scanned_pages} scanned")
        if self.images:
            parts.append(f"{self.images} picture file{'s' if self.images != 1 else ''}")
        if self.media:
            minutes = int(round(self.media_seconds / 60))
            parts.append(f"{self.media} recording{'s' if self.media != 1 else ''} ({minutes} min)")
        if self.others:
            parts.append(f"{self.others} other document{'s' if self.others != 1 else ''}")
        if not parts:
            return "No files chosen yet."
        text = " · ".join(parts)
        if self.capped:
            text += " (and more)"
        return text


def findings_from_probe(files: list[Path], probe: dict[Path, dict], capped: bool = False) -> Findings:
    """Turn the driver's probe rows ({'kind', 'pages', 'text_chars', 'seconds'}) into Findings."""
    found = Findings(files=len(files), capped=capped)
    for path in files:
        row = probe.get(path) or {}
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            found.pdfs += 1
            pages = row.get("pages")
            chars = row.get("text_chars")
            if pages is None:
                found.unknown_pdfs += 1
                continue
            found.pages += int(pages)
            if chars is not None and chars < SCAN_TEXT_CHARS:
                found.scanned_pages += int(pages)
                found.scanned_pdfs += 1
        elif suffix in MEDIA_INPUT_EXTENSIONS:
            found.media += 1
            found.media_seconds += float(row.get("seconds") or 0.0)
        elif suffix in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"):
            found.images += 1
        else:
            found.others += 1
    return found


@dataclass
class Speed:
    """What the launcher has learned about this machine."""
    factor: float = 1.0                     # actual / estimated, smoothed over batches
    pictures_per_page: float = PICTURES_PER_PAGE

    def to_dict(self) -> dict:
        return {"factor": self.factor, "pictures_per_page": self.pictures_per_page}

    @classmethod
    def from_dict(cls, data) -> "Speed":
        speed = cls()
        if isinstance(data, dict):
            try:
                speed.factor = min(20.0, max(0.05, float(data.get("factor", 1.0))))
                speed.pictures_per_page = min(10.0, max(0.0, float(data.get("pictures_per_page", PICTURES_PER_PAGE))))
            except (TypeError, ValueError):
                pass
        return speed


def estimate_seconds(found: Findings, *, ocr: bool, formulas: bool, charts: bool, describe: bool,
                     speakers: bool, speed: Speed | None = None) -> float:
    """Seconds for the found files with the given abilities, before the machine factor."""
    speed = speed or Speed()
    seconds = START_SECONDS + found.pages * SECONDS_PER_PAGE + found.others * SECONDS_PER_OTHER_FILE
    seconds += found.unknown_pdfs * 10 * SECONDS_PER_PAGE  # a PDF that could not be read: guess ten pages
    if ocr:
        seconds += found.scanned_pages * SECONDS_PER_OCR_PAGE + found.images * SECONDS_PER_OCR_PAGE
    if formulas:
        seconds += found.pages * SECONDS_PER_FORMULA_PAGE
    if charts:
        seconds += found.pages * SECONDS_PER_CHART_PAGE
    if describe and (found.pages or found.others or found.images or found.media):
        seconds += DESCRIBE_START_SECONDS + found.pages * speed.pictures_per_page * SECONDS_PER_PICTURE
    seconds += found.media_seconds * SECONDS_PER_MEDIA_SECOND * (1.0 if speakers else 0.85)
    return seconds * speed.factor


def describe_duration(seconds: float) -> str:
    """'about 15 min', 'about 40 s', 'about 1 h 10 min'."""
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"about {max(5, int(round(seconds / 5.0)) * 5)} s"
    minutes = int(round(seconds / 60))
    if minutes < 60:
        return f"about {minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"about {hours} h" + (f" {rest} min" if rest else "")


def estimate_line(found: Findings, *, ocr: bool, formulas: bool, charts: bool, describe: bool,
                  speakers: bool, speed: Speed | None = None) -> str:
    """The strip's second line: 'about 15 min with what's ticked · about 2 min text only'."""
    if not found.files:
        return ""
    full = estimate_seconds(found, ocr=ocr, formulas=formulas, charts=charts, describe=describe, speakers=speakers, speed=speed)
    plain = estimate_seconds(found, ocr=ocr, formulas=False, charts=False, describe=False, speakers=speakers, speed=speed)
    if not (formulas or charts or describe):
        return f"{describe_duration(full)} with what's ticked"
    return f"{describe_duration(full)} with what's ticked · {describe_duration(plain)} text only"


def learn(speed: Speed, estimated: float, actual: float, pages: int = 0, pictures: int | None = None) -> Speed:
    """After a batch: move the machine factor a third of the way towards what really
    happened (both times over 20 s, so a trivial batch teaches nothing), and the pictures
    per page likewise when the describe pass counted them."""
    new = Speed(speed.factor, speed.pictures_per_page)
    if estimated >= 20 and actual >= 20:
        ratio = min(20.0, max(0.05, actual / estimated))
        new.factor = min(20.0, max(0.05, speed.factor * (ratio ** (1 / 3))))
    if pictures is not None and pages >= 5:
        seen = pictures / pages
        new.pictures_per_page = min(10.0, max(0.0, speed.pictures_per_page * 2 / 3 + seen / 3))
    return new
