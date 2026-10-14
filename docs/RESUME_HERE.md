# Resume here — the state of the Docling Launcher

**Snapshot, not a diary.** When the state changes, REWRITE this block; history belongs in
`git log`, the board in `TODO.md`, the durable facts in `docs/KNOWLEDGE.md`.

*Last rewritten: 2026-09-24. Version 1.5.4, released. 92 guards, all green.*

---

## 0 · What this is

A Windows desktop front end for `docling convert`, written for **one owner who is not a
programmer**. They convert technical documentation (standards, plans: tables, formulas,
figures) and meeting recordings (who said what). Everything the app can do must be
explainable in one plain sentence, and the results must be complete enough that a
converted document can be dropped into a chat without costing extra work.

| | |
|---|---|
| Repo | `LITRAP/docling-launcher` (**public**; no personal data in it) |
| App | `dist\DoclingLauncher.exe`, one file, icon embedded; Desktop + Start-menu shortcuts |
| Docling's environment | `.venv` beside the project — Python 3.12, Docling 2.126, torch +cu130 (RTX A4000 16 GB), onnxruntime-gpu 1.30, Whisper, kaldi-native-fbank |
| Releases | v1.4.0 · v1.5.1 · v1.5.2 · v1.5.3 · **v1.5.4** (current) |
| Guards | 92 (`tests/`), real widgets on a withdrawn window, stand-in Docling |

## 1 · Where things stand

Everything the owner has asked for is built and released. Rounds 1–9 are listed in
`TODO.md` with what each one did; the measurements behind the decisions are in
`docs/KNOWLEDGE.md`.

The last three rounds, in one line each:

- **7 (2026-09-21)** — formulas and picture descriptions on by default; a settings file
  from before is switched on once (`SETTINGS_VERSION`), with a line in the log.
- **8** — the **"What's in these documents?"** strip on the Convert tab: the abilities in
  plain words, what the launcher found in the chosen files, and about how long the run
  will take with what is ticked (`estimate.py`, learns this machine's speed).
- **9** — **charts off by default** and a warning line under every chart table: the chart
  model invents values on engineering charts (checked on three figures of a standard).

## 2 · Open, and why

| | |
|---|---|
| 🔴 Pins to lift when upstream fixes them | `transformers<5.8` (the chart model's bundled legacy code) · `setuptools<80` (resemblyzer imports `pkg_resources`). Both in `constants.UPGRADE_PINS` and `build_exe.ps1` |
| 🔴 Workarounds to remove | the MKV wrapper for sound files (`media.py` + `assets/media_tool.py`) when Docling separates speakers for audio; the driver's speech and speaker patches (`assets/convert_tool.py`) when its command line exposes the language and the diarization engine |
| 🟡 Head count on a laptop-microphone meeting | the engine finds four voices in a three-person meeting (the listener's short interjections cluster apart). "People speaking" fixes it when known; a microphone on the table is the real fix. Five ways to do it automatically were tried and rejected — see `docs/KNOWLEDGE.md` |
| 💡 Rejected, do not re-propose without new evidence | Docling's own vision pipeline (129 s vs 16 s for the same pages) · a punctuated prompt for Whisper (punctuation halved) · beam search 5 (lowercase, unpunctuated) · whisper large-v3 (4.6× slower, no better) · transcribing each speaker turn separately (twice the time, words cut at the seams, hallucinations on short pieces) |

## 3 · How to work on it

Read `.claude/skills/docling-launcher/SKILL.md` (or the identical rules in `CLAUDE.md`)
before touching anything. The short version:

```powershell
.venv\Scripts\python.exe -m unittest discover tests      # 92 guards, ~65 s
powershell -NoProfile -ExecutionPolicy Bypass -File build_exe.ps1
$env:DOCLING_LAUNCHER_SELFTEST="$env:TEMP\st.json"; .\dist\DoclingLauncher.exe   # proof run, no window
.venv\Scripts\python.exe tools\snap_window.py <folder> light|dark                # pictures of every tab
powershell -NoProfile -ExecutionPolicy Bypass -File tools\release.ps1 -SkipBuild # tag + publish
```

**Nothing is reported as working until it has been built, driven and looked at.** The exe
cannot be rebuilt while the launcher is open — the build script says so loudly.

## 4 · What the owner decided (do not re-litigate)

| When | Decision |
|---|---|
| 2026-09-12 | One exe with an icon and shortcuts; the old ones deleted. Update = Docling **and** its OCR add-ins together, checked once quietly at every start |
| 2026-09-12 | Move Docling's environment to Python 3.12 — after a side-by-side run proved nothing was lost |
| 2026-09-13 | Sound files travel through Docling's video road so speakers can be separated; switch back the day Docling does it natively |
| 2026-09-13 | The launcher's repository is public; the update key stays in Settings for a private future |
| 2026-09-21 | Everything that can be written into the Markdown is written by default — "each piece of information easily and quickly retrievable" |
| 2026-09-21 | …except charts: off by default, and every chart table carries a warning that its numbers were read from a picture |
| 2026-09-21 | The "what's in these documents" question lives as a **permanent strip** above Run, not as a welcome pop-up with "don't show again" |
