# Docling Launcher

Windows Tkinter desktop launcher for batch `docling convert` runs, with one-click updates of
Docling itself.

`TODO.md` is the status board: what is done, what is open, what was deferred and why.

## Layout of the project

| Path | What |
|---|---|
| `src/docling_launcher/` | the app. `app.py` window · `docling_cli.py` command building, one process per output folder, job object · `updates.py` version check, upgrade, restore points · `environment.py` extension status · `admin.py` elevated run |
| `.venv/` | **Docling's environment** — Python 3.12, Docling + OCR add-ins + speech/video (Whisper). The launcher finds `.venv\Scripts\docling.exe` next to the project and updates *this* folder |
| `.venv314_old/` | the previous environment (Python 3.14, Docling 2.115) kept as a fallback until the owner says delete. Its `Scripts\*.exe` stubs embed the old path and no longer start; `python.exe` inside it still works |
| `tests/` | `python -m unittest discover tests -v` — real widgets on a withdrawn window, a stand-in `docling.exe` (`fake_docling.cmd`) |
| `build_exe.ps1` | builds `dist\DoclingLauncher.exe` (icon embedded) and the Desktop / Start-menu shortcuts |

## Updates

At start the launcher reads the installed versions from `.venv` (no process, ~90 ms) and asks
PyPI once, in the background, whether Docling or an OCR add-in is newer (~1–3 s). If so the
header shows `2.126.0 available · Update`. **Update** = `pip freeze` to
`%APPDATA%\DoclingLauncher\snapshots\<date>.txt`, then `pip install --upgrade` of the
outdated packages, streamed into the log. **Go back** = `pip install -r <snapshot>`.

## Why Python 3.12 (2026-09-12)

Docling's speech library (Whisper) has no build for Python 3.14 yet, so audio and video could
not be converted. Measured with the same Docling on both: 3.12 costs ~1.5 s per Docling start
and nothing per page. Docling 2.126 itself is 2–3× slower than 2.115 on text PDFs with
pictures because its default OCR now reads picture regions — hence the "Read text in pictures
and scans (OCR)" tick box; off adds `--no-ocr` and is as fast as 2.115.

## Input selection

By default every supported file in the input folder and its subfolders is converted. Clear
**Convert every supported file in this folder** to enable **Select Files...**. Sound and video
files are converted through Docling's speech pipeline; if Whisper is missing they are skipped
with one log line.

## Build

```powershell
.\build_exe.ps1            # clean build + shortcuts
.\build_exe.ps1 -NoShortcuts
```

The icon is the Docling project's own logo (MIT, `docling-project/docling`, `docs/assets/logo.png`).
