# Docling Launcher — status board

One line per item. ✅ done · 🔴 open bug · 🟡 partly done · 📋 deferred by the owner · 💡 idea, not planned.

## ✅ Done — 2026-09-12, round 4 (smart engine, new window, self-update)

- ✅ **Descriptions as a pass of their own** (`convert_tool.py describe`): Docling's describing model run on the saved PNGs after the conversion — charts keep the large model, nothing shares the card, video frames get described too. 6 pictures in ~1 min on the GPU
- ✅ **OCR decided per file** ("Automatic"): each PDF is probed for a text layer (~50 ms); scans and images get OCR, digital documents do not; "Always, whole page" and "Off" remain
- ✅ **Skip files already converted** (outputs newer than the source) · **Retry failed files once** · restore points pruned to the last five
- ✅ **New window**: Windows 11 look (sv_ttk, light and dark), tabs Convert / Settings / Updates / Log, Run bar always visible with progress and status, results table (file · folder · result · time; double-click opens the folder), "Open output folder", presets in the header, drag & drop from Explorer through Windows' own message (no extra package), engine and portable-Tesseract rows only when they apply, Mac-only OCR engine hidden
- ✅ **Launcher self-update** (`launcher_update.py`): checks the GitHub releases of LITRAP/docling-launcher (private → needs the update key in Settings → Launcher), downloads the exe, swaps it after exit, keeps the previous copy until the new one starts. `tools/release.ps1` publishes a version
- ✅ Model rows carry Docling's **pinned revision** (the chart model is pinned to a commit; deleting it cost a 10-minute re-download once); a pinned model is never "newer"; cleanup keeps the pinned copy
- ✅ 50 guards (`tests/`): skip-done, retry, OCR per file, describe pass, drop, presets, theme, results table, plus everything before

## ✅ Done — 2026-09-12, rounds 1–3

- ✅ One-click **Update** of Docling, add-ins and AI models with dates, restore point, **Go back**; header shows the version; GPU edition kept across updates
- ✅ Technical documents: pictures kept, formulas as LaTeX, charts as tables, better picture descriptions (granite-vision 2B), who said what (speakers), speech model choice (turbo)
- ✅ Run as Administrator fixed; one Docling start per folder; **Stop**; nothing outlives the window; honest per-file results; audio through the video road for speakers
- ✅ Docling environment on Python 3.12 with GPU torch, speech + video (`.venv`); old 3.14 kept as `.venv314_old`; one exe with the duck icon; shortcuts

## 🔴 Open / watch

- 🔴 **Pins to lift when Docling fixes them** (`constants.UPGRADE_PINS`, `build_exe.ps1`, README): `transformers<5.8` (chart model's bundled code) and `setuptools<80` (resemblyzer needs `pkg_resources`)
- 🔴 **Workaround to remove** when Docling exposes speaker separation for audio and puts speakers in Markdown: `media.py` + `assets/media_tool.py`
- 🟡 The private repository needs an update key for self-update (How to use → Updates says where it comes from). Making the repository public would remove that step
- 🟡 RapidOCR runs on the CPU (onnxruntime without CUDA); `onnxruntime-gpu` would speed scans up — not installed because it must match the CUDA version exactly

## 📋 Deferred by the owner

- (none — the layout work was done in round 4)

## 💡 Ideas (suggestions only — each says what it costs)

- 💡 "What is on screen" in words for videos: Docling saves frames at scene changes as pictures and the describe pass already describes them — a per-frame timestamp in the text would make it a scene log; small
- 💡 OCR language choice (`--ocr-lang`) for non-English scans — small
- 💡 Per-document prompt for descriptions (manuals vs papers vs drawings) — small
- 💡 A "Convert" entry in Explorer's right-click menu — small (a registry entry pointing at the exe with the folder as argument)
- 💡 Windows Developer Mode would let the model cache use links (not needed: links are off and files are moved into place)
