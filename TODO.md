# Docling Launcher — status board

One line per item. ✅ done · 🔴 open bug · 🟡 partly done · 📋 deferred by the owner · 💡 idea, not planned.

## ✅ Done — 2026-09-12

- ✅ One-click **Update** of Docling and its OCR add-ins, with a restore point and **Go back**
- ✅ Quiet update check at every start (one request, ~1–3 s, in the background); **Check now** button; Updates table (Component · Installed · Latest · Status)
- ✅ Header shows the installed Docling version
- ✅ Run as Administrator crashed at once in every exe ever built — fixed; switched off in the owner's settings
- ✅ One Docling start per output folder instead of per file (~14 s saved per file)
- ✅ **Stop** button; closing the window ends Docling and pip (Windows job object — nothing outlives the launcher)
- ✅ Per-file result from the files actually written, not the exit code; failed files named; total time
- ✅ Sound/video: converted through the speech pipeline when Whisper is present, otherwise skipped with one log line
- ✅ Input list matches Docling's own (EPUB, DOC, PPT, XLS, ODT/ODS/ODP, EML, LaTeX, …)
- ✅ Tesseract status honours the portable folder; table headers left-aligned
- ✅ Mouse wheel over the log scrolls only the log; no timer runs while idle
- ✅ "Read text in pictures and scans (OCR)" tick box, on by default; engine + portable Tesseract hidden when off
- ✅ One exe `dist\DoclingLauncher.exe` with the Docling duck icon; Desktop + Start-menu shortcuts (pin from Start)
- ✅ Docling environment rebuilt on Python 3.12 with speech + video (`.venv`); old 3.14 kept as `.venv314_old`
- ✅ 24 guards in `tests/` (real buttons, stand-in Docling)

## 📋 Deferred — layout (owner: "update button + fixes first")

- 📋 The Run button is below the fold at every window size; the log takes half the window
- 📋 Format tick boxes scattered across the width; labels far from their fields (column 0 stretches)
- 📋 Old grey "clam" skin — the native Windows look would be the beautiful choice
- 📋 Mac-only OCR engine `ocrmac` offered on Windows; `kserve`/`nemotron` need servers
- 📋 Portable Tesseract shown even when the engine is not Tesseract (now hidden only when OCR is off)

## 🔴 Open

- 🔴 `.venv314_old` — delete once the owner confirms the 3.12 folder (1.9 GB)

## 💡 Ideas (suggestions only — each says what it costs)

- 💡 Drag & drop files/folders onto the window — small; a Tk drop needs the `tkinterdnd2` package bundled in the exe
- 💡 Progress bar + per-file result table (✓/✗, seconds) + "Open output folder" — medium; the data already exists in the log
- 💡 "Only convert new or changed files" (skip when output is newer than input) — small
- 💡 Docling options the app hides: OCR language, force OCR, image export mode, enrichments (formula/code/picture), CPU vs GPU, threads, speech model size — small each, but every one needs its "only when relevant" rule
- 💡 Presets ("French books", "Scans") — medium
- 💡 Retry failed files at the end — small
- 💡 The launcher updating **itself** — needs a home on the internet (GitHub releases); medium
- 💡 Snapshots folder never pruned — keep the last 5; tiny
