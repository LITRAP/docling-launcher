---
name: docling-launcher
description: Work on the owner's Docling Launcher (E:\DoclingLauncherApp) — the Windows front end for `docling convert`. Use for anything about converting their documents or recordings (formulas, charts, picture descriptions, OCR, who said what, speakers, transcripts), about the launcher's window, settings, updates, models, estimates or releases, and whenever a converted .md file of theirs looks wrong or incomplete. Read before changing code, building the exe, or answering why a conversion produced what it produced.
---

# Working on the Docling Launcher

**Read first:** `E:\DoclingLauncherApp\docs\RESUME_HERE.md` (state, what is open, what the
owner decided) · `docs/KNOWLEDGE.md` (measurements, model behaviour, traps) · `CLAUDE.md`
(the standing rules — plain words, build-drive-look, never steal the screen, defaults are
the owner's call, measure before claiming). `TODO.md` is the board.

This file is the **procedure**: what to run, in what order, and what has to be true before
anything is called done.

## The map, in one table

| Where | What |
|---|---|
| `src/docling_launcher/app.py` | the window. Tabs Convert · Settings · Updates · Log; the "What's in these documents?" strip lives at the bottom of the Convert tab |
| `…/docling_cli.py` | builds every command (`ConversionOptions`), one Docling process per output folder, `probe_files`, the job object that kills children |
| `…/estimate.py` | what is in the chosen files and how long the ticked abilities take; learns this machine's speed |
| `…/settings.py` | `LauncherSettings`, `SETTINGS_VERSION`, the one-time upgrade steps |
| `…/chart_note.py` · `media.py` · `safety.py` · `watcher.py` · `windows.py` | after-steps on the Markdown · sound/video road and transcript by speaker · the reference check · folder watching · keep-awake, toast, theme, Explorer menu |
| `…/assets/*.py` | run **inside `.venv`**, import nothing from the package, ship inside the exe: `convert_tool` (the one road into Docling + describe pass + the speech/speaker patches), `speakers_tool` (pyannote 3 pipeline), `models_tool` (model check/download), `media_tool` (audio→MKV) |
| `tests/` | 92 guards; `fake_docling.py` stands in for Docling, `WindowFixture` gives a withdrawn real window |
| `tools/snap_window.py` · `tools/release.ps1` | pictures of every tab · tag, push, publish |

## The loop

```powershell
cd E:\DoclingLauncherApp

# 1. guards first — write the new one BEFORE the change when touching shared behaviour
.venv\Scripts\python.exe -m unittest discover tests            # ~65 s, must end OK
.venv\Scripts\python.exe -m unittest tests.test_contents       # one file while iterating

# 2. build (fails loudly if the launcher is open — close it, do not work around it)
powershell -NoProfile -ExecutionPolicy Bypass -File build_exe.ps1

# 3. drive the built exe without a window on their screen
$env:DOCLING_LAUNCHER_SELFTEST = "$env:TEMP\selftest.json"
.\dist\DoclingLauncher.exe ; Start-Sleep 10 ; Get-Content $env:TEMP\selftest.json

# 4. look at anything they will see
.venv\Scripts\python.exe tools\snap_window.py C:\...\snaps light
.venv\Scripts\python.exe tools\snap_window.py C:\...\snaps\dark dark
#    then Read the .png files and actually read them

# 5. ship
git add -A ; git commit    # full prose: found, measured, decided
git push origin master
powershell -NoProfile -ExecutionPolicy Bypass -File tools\release.ps1 -SkipBuild
```

⚠ Before the self-test, copy `%APPDATA%\DoclingLauncher\settings.json` aside and compare
afterwards. It must be **byte-identical** — a proof run never writes the owner's settings.

## Trying something on a real document

Work in the scratch folder, never in their output folder, and hand them a **new file
beside** the old one when the result is good:

```powershell
$env:HF_HUB_DISABLE_SYMLINKS = "1" ; $env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe src\docling_launcher\assets\convert_tool.py convert `
    --to md --image-export-mode referenced --enrich-formula --enrich-code --no-ocr `
    --num-threads 8 "<file.pdf>" --output "<scratch>"
.venv\Scripts\python.exe src\docling_launcher\assets\convert_tool.py describe `
    --model better --threads 8 "<scratch>\<file>.md"
```

For media, add `--launcher-language fr --launcher-speakers best [--launcher-people N]`
before Docling's own flags, plus `--asr-model whisper_turbo --video-diarization
--video-sampling-mode scene --to vtt`.

**Always time it** (`Measure-Command`, or two `date +%s` around it) and put the number in
`docs/KNOWLEDGE.md`; `estimate.py`'s seeds and its guard depend on those numbers staying
honest.

## When the owner says a converted file is wrong

Look at the file and at the picture before theorising:

1. `grep -c "formula-not-decoded"` — formulas were off (or the formula model missing).
2. A picture line with no paragraph under it — descriptions were off; a paragraph that is
   nonsense is the 2 B model's limit, not a bug.
3. A table under "Line chart" / "Bar chart" — that is the **chart model's reading of a
   picture**, not a document table. Open the PNG in `<name>_artifacts` and check it.
   It invents values on engineering charts; every such table carries a warning line.
4. A transcript that changes speaker every sentence — that is Docling's built-in
   separation; the "best" engine plus a known head count is the answer.

Then check their `settings.json` before changing code: an ability that was simply off is
the commonest cause, and the fix is a default (see rule 4 in `CLAUDE.md`), not a patch.

## Adding an ability — the checklist

1. `ConversionOptions` field → flag in `build_command_plan` → tick box in the window
   (Settings, and in the strip if it is something the owner would say about a *document*)
   → `LauncherSettings` field → tooltip → the "How to use" text.
2. Show it only where it can matter (hidden, not greyed) and keep the layout from
   shifting when it hides.
3. If it needs a model: a row in `constants.MODELS` with its **pinned revision** and the
   ability that needs it, so Update can fetch and replace it.
4. If it costs time: a seed in `estimate.py` **measured**, not guessed.
5. Guards in `tests/`, in the same commit. Then the loop above.
