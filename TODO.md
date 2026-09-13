# Docling Launcher — status board

One line per item. ✅ done · 🔴 open bug · 🟡 partly done · 📋 deferred by the owner · 💡 idea, not planned.

## ✅ Done — 2026-09-13, round 5 (everything from the idea tables)

- ✅ Keep the PC awake during a batch · time left in the status bar · Windows notification when a long batch ends · look follows Windows (system / light / dark)
- ✅ **Watch this folder** — Windows reports new files (no polling); a batch runs by itself once the folder is quiet; a batch in progress is finished first
- ✅ **Queue** — several folders with their own output folder and preset, run one after another; survives a restart
- ✅ Chunks for AI (`--to chunks`) · **Web page…** by address · OCR languages (`--ocr-lang`, proven on RapidOCR and EasyOCR) · describing instruction editable with Reset
- ✅ **Save report…** (Markdown table with links) · **Name speakers…** (labels → names in the batch's transcripts) · scene log for videos ("At mm:ss" above each frame, from Docling's JSON)
- ✅ 'Convert with Docling' on Explorer's right-click menu (current user; the launcher takes the folder as its argument)
- ✅ **Reference check** — a built-in two-page paper + scan converted after every update and compared with the last good run (words, table rows, scan, time); a bad run warns and never becomes the baseline
- ✅ **OCR on the graphics card** — onnxruntime-gpu 1.30 (CUDA 13, matching torch cu130): whole-page OCR of five pages 5.8 s instead of ~19 s; the updater removes a stray processor edition
- ✅ Repository public → self-update needs no key (the key field stays for a private future) · Jules repository made private at the owner's request
- ✅ 58 guards

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

## 📋 Deferred by the owner

- (none — the layout work was done in round 4)

## 💡 Ideas (suggestions only — each says what it costs)

- 💡 Docling's vision engine (`--pipeline vlm`, granite-docling-258M) as a second opinion — measured 2026-09-13: 129 s for two pages against 16 s, same words, on the card. Not offered; ask if a hard layout ever needs it
- 💡 Windows Developer Mode would let the model cache use links (not needed: links are off and files are moved into place)
