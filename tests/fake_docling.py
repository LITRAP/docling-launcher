"""A stand-in for docling.exe: same arguments, same log lines, writes the same output
files — but instantly, and with an optional per-file delay so Stop can be tested.

Started through fake_docling.cmd (Windows runs a .cmd through cmd.exe), which is what
the DOCLING_EXE override points at during the tests."""
import os
import sys
import time
from pathlib import Path

SUFFIXES = {"md": ".md", "json": ".json", "html": ".html", "text": ".txt",
            "doclang": ".dclg.xml", "doctags": ".doctags", "vtt": ".vtt", "dclx": ".dclx"}


def main(argv: list[str]) -> int:
    assert argv[0] == "convert", argv
    formats: list[str] = []
    sources: list[Path] = []
    output = Path(".")
    it = iter(argv[1:])
    for arg in it:
        if arg == "--to":
            formats.append(next(it))
        elif arg == "--ocr-engine":
            next(it)
        elif arg == "--output":
            output = Path(next(it))
        elif arg.startswith("-"):
            continue
        else:
            sources.append(Path(arg))
    delay = float(os.environ.get("FAKE_DOCLING_DELAY", "0"))
    fail = os.environ.get("FAKE_DOCLING_FAIL_STEM", "")
    for source in sources:
        print(f"2026-09-12 10:00:00,000\tINFO\tdocling.document_converter: Processing document {source.name}", flush=True)
        time.sleep(delay)
        if source.stem == fail:
            print(f"2026-09-12 10:00:00,000\tERROR\tdocling.document_converter: Could not convert {source.name}", flush=True)
            continue
        for fmt in formats:
            (output / f"{source.stem}{SUFFIXES[fmt]}").write_text(f"converted {source.name}", encoding="utf-8")
        print(f"2026-09-12 10:00:00,000\tINFO\tdocling.document_converter: Finished converting document {source.name} in 0.01 sec.", flush=True)
    print(f"Processed {len(sources)} docs, of which 0 failed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
