"""A stand-in for docling.exe: same arguments, same log lines, writes the same output
files — but instantly, and with an optional per-file delay so Stop can be tested.

Started through fake_docling.cmd (Windows runs a .cmd through cmd.exe), which is what
the DOCLING_EXE override points at during the tests."""
import json
import os
import sys
import time
from pathlib import Path

SUFFIXES = {"md": ".md", "json": ".json", "html": ".html", "text": ".txt",
            "doclang": ".dclg.xml", "doctags": ".doctags", "vtt": ".vtt", "dclx": ".dclx"}


def main(argv: list[str]) -> int:
    if argv and argv[0] == "probe":
        # a "scan" in the name means no text layer; everything else is digital
        for name in argv[1:]:
            chars = 0 if "scan" in Path(name).name.lower() else 500
            print(json.dumps({"file": name, "kind": "pdf", "pages": 3, "text_chars": chars}), flush=True)
        return 0
    if argv and argv[0] == "describe":
        rest = list(argv[1:])
        while rest and rest[0].startswith("--"):
            rest = rest[2:]
        total = 0
        for name in rest:
            path = Path(name)
            lines = path.read_text(encoding="utf-8").splitlines()
            out = []
            for line in lines:
                out.append(line)
                if line.startswith("![Image]("):
                    total += 1
                    out.extend(["", f"(description {total})"])
                    print(f"described {total}/{total}", flush=True)
            path.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"DONE {total} {len(rest)}", flush=True)
        return 0
    assert argv[0] == "convert", argv
    formats: list[str] = []
    sources: list[Path] = []
    output = Path(".")
    it = iter(argv[1:])
    WITH_VALUE = {"--ocr-engine", "--image-export-mode", "--asr-model", "--num-threads",
                  "--video-sampling-mode", "--video-frame-interval", "--ocr-mode", "--device",
                  "--launcher-speakers", "--launcher-people", "--launcher-language"}
    marker = os.environ.get("FAKE_DOCLING_FAIL_ONCE_MARKER")
    for arg in it:
        if arg == "--to":
            formats.append(next(it))
        elif arg == "--output":
            output = Path(next(it))
        elif arg in WITH_VALUE:
            next(it)
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
            if marker and not Path(marker).exists():
                # fail once, then succeed: the retry must catch it
                Path(marker).write_text("failed once")
                print(f"2026-09-12 10:00:00,000\tERROR\tdocling.document_converter: Could not convert {source.name}", flush=True)
                continue
            if not marker:
                print(f"2026-09-12 10:00:00,000\tERROR\tdocling.document_converter: Could not convert {source.name}", flush=True)
                continue
        if "md" in formats and source.suffix == ".pdf":
            # a picture reference, so the describe pass has something to describe
            (output / f"{source.stem}.md").write_text(f"# {source.stem}\n\n![Image]({source.stem}.png)\n\ntext\n", encoding="utf-8")
            (output / f"{source.stem}.png").write_bytes(b"png")
            for fmt in formats:
                if fmt != "md":
                    (output / f"{source.stem}{SUFFIXES[fmt]}").write_text(f"converted {source.name}", encoding="utf-8")
            print(f"2026-09-12 10:00:00,000\tINFO\tdocling.document_converter: Finished converting document {source.name} in 0.01 sec.", flush=True)
            continue
        for fmt in formats:
            (output / f"{source.stem}{SUFFIXES[fmt]}").write_text(f"converted {source.name}", encoding="utf-8")
        print(f"2026-09-12 10:00:00,000\tINFO\tdocling.document_converter: Finished converting document {source.name} in 0.01 sec.", flush=True)
    print(f"Processed {len(sources)} docs, of which 0 failed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
