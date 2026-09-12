# Docling Launcher — status board

One line per item. ✅ done · 🔴 open bug · 🟡 partly done · 📋 deferred by the owner · 💡 idea, not planned.

## ✅ Done — 2026-09-12, round 2 (technical documents, models, dates)

- ✅ Updates table: **Installed on** and **Released** columns beside every component; AI models listed with the packages
- ✅ "Also update the AI models" tick box — Update replaces models that have a newer version on the hub and downloads missing ones a ticked ability needs; the old copy is deleted through the model library's own cache manager
- ✅ **Technical documents** section: Keep pictures (PNGs beside the output, linked) · Formulas as LaTeX + code blocks · Charts as tables of values · Describe each picture · Who said what (speakers) · Speech model choice (turbo = best)
- ✅ GPU edition of the AI library installed (RTX A4000 in use); Update puts the GPU edition back if a new Docling drags in the CPU one
- ✅ Tables proven on a 12-column paper table; pie/line charts proven as value tables; formulas proven as LaTeX; two-voice recording proven as a transcript by speaker
- ✅ "Reads: PDF, Word, …" line under the input folder + **All input types…** table (kind · file types · note)
- ✅ How to Use rewritten: purpose, five steps, every setting in plain words
- ✅ Models load only while a conversion runs — proven with GPU memory before/during/after (3.4 GB → 15.6 GB → 3.3 GB)
- ✅ Sound files get speaker separation through the video road (wrapped without re-encoding); documents and media run in separate Docling processes
- ✅ 38 guards in `tests/` (real window, stand-in Docling, model cache with a half-finished download, the model table checked against Docling's own source)

## ✅ Done — 2026-09-12, round 1

- ✅ One-click **Update** of Docling and its OCR add-ins, restore point, **Go back**; quiet check at start; header shows the version
- ✅ Run as Administrator fixed; one Docling start per output folder; **Stop**; nothing outlives the window; honest per-file results
- ✅ Sound/video through the speech pipeline; input list = Docling's own; OCR on/off tick box; one exe with the duck icon; shortcuts
- ✅ Docling environment on Python 3.12 with speech + video (`.venv`); old 3.14 kept as `.venv314_old`

## 🔴 Open / watch

- 🔴 **Pins to lift when Docling fixes them** (both in `constants.UPGRADE_PINS`, `build_exe.ps1`, README): `transformers<5.8` — Docling 2.126 loads the chart model through its bundled legacy code, which transformers 5.8+ rejects (`create_causal_mask(cache_position=)`); `setuptools<80` — resemblyzer (speakers) imports `pkg_resources`. When an Update stops because a pin and a new Docling cannot both hold, re-test and lift.
- 🔴 **Workaround to remove when Docling exposes speaker separation for audio and puts speakers in Markdown**: `media.py` + `assets/media_tool.py` (audio wrapped as video; transcript by speaker written from the VTT). Owner's decision 2026-09-12.
- 🔴 `.venv314_old` — delete once the owner confirms (1.7 GB)
- 🟡 The chart model (8 GB) needs most of the 16 GB card; with Windows' own ~3–5 GB it fits but loaded slowly once (9 min) while the card was busier. If that recurs: Docling's smaller chart model (2b) is not selectable from the command line yet.
- 🟡 Picture descriptions come from the small model and are rough (as warned). A better one (granite-vision, 6 GB) exists but Docling's command line cannot choose it.

## 📋 Deferred — layout (owner: "update button + fixes first")

- 📋 The Run button is below the fold at every window size; the log takes half the window
- 📋 Format tick boxes scattered across the width; labels far from their fields (column 0 stretches)
- 📋 Old grey "clam" skin — the native Windows look would be the beautiful choice
- 📋 Mac-only OCR engine `ocrmac` offered on Windows; `kserve`/`nemotron` need servers
- 📋 Portable Tesseract shown even when the engine is not Tesseract (now hidden only when OCR is off)

## 💡 Ideas (suggestions only — each says what it costs)

- 💡 Drive Docling through its Python API instead of the command line (a `convert_tool.py` beside the two tools): unlocks the better picture-description model, the smaller chart model, scene descriptions for video ("what is on screen"), OCR modes. Medium; the command preview would then show settings, not a command
- 💡 Windows Developer Mode would let the model cache use links again (not needed now that links are off; files are moved into place)
- 💡 Drag & drop files/folders onto the window — small; needs `tkinterdnd2` bundled
- 💡 Progress bar + per-file result table (✓/✗, seconds) + "Open output folder" — medium
- 💡 "Only convert new or changed files" — small
- 💡 Presets ("French books", "Scans", "Technical manual") — medium
- 💡 Retry failed files at the end — small
- 💡 The launcher updating **itself** — needs a home on the internet (GitHub releases); medium
- 💡 Snapshots folder never pruned — keep the last 5; tiny
