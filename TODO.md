# Docling Launcher — status board

One line per item. ✅ done · 🔴 open bug · 🟡 partly done · 📋 deferred by the owner · 💡 idea, not planned.

## ✅ Done — 2026-09-13, round 6 (who said what, done properly)

- ✅ **Best speaker separation** (`assets/speakers_tool.py`): pyannote segmentation-3.0 + WeSpeaker ResNet34-LM in ONNX (sherpa-onnx's conversions, MIT/Apache, no account), both on the GPU through onnxruntime-gpu; features by `kaldi-native-fbank` (identical to sherpa's, checked); spectral clustering with the eigenvalue gap for the head count. The owner's 54-minute meeting: Docling's built-in said 2 speakers (silhouette 0.13); this finds **4** (eigenvalues 0 · 0.04 · 0.11 · 0.12 · then 0.44), 95 s, run *beside* Whisper so it adds no wait
- ✅ **Speakers word by word** (`convert_tool.py assign_speakers_by_word`): a sentence is cut where the speaker changes; "oui, oui" no longer vanishes into the presenter's block
- ✅ **Language spoken** (Settings → Technical documents) told to Whisper. Carrying the previous window's text is now explicitly off — Docling's `None` already meant off (the meeting came out 99.85 % identical), and real carrying lost 14 s of speech in a 4-minute test
- ✅ Settings: engine (best / Docling's built-in), people speaking (when known), language; rows shown only while "Who said what" is ticked; presets carry them; `whisper_large` offered with an honest note (4-5x slower, not better on the meeting)
- ✅ Model row "Who-said-what models" in Updates (downloaded from GitHub releases, 33 MB, into `%LOCALAPPDATA%\DoclingLauncher\models\speakers`); environment row "Who said what (best)"
- ✅ Rejected with numbers: a punctuated French prompt for Whisper (punctuation went from 55 to 24 of 110 segments); Whisper large-v3 (74 s vs 16 s on 4 min, similar text); beam search 5 (lowercase, unpunctuated output); pyannote's own threshold clustering on this recording (1 group at its tuned threshold, 17 at 0.7). The transcript's words themselves are unchanged: Whisper covered 45.6 of the 46.7 minutes of speech pyannote hears, no gaps — what was wrong was who said them
- ✅ 75 guards (`tests/test_speakers.py` added)

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
- 🔴 **Driver patches to revisit** when Docling's command line gains them: `--launcher-language` (Whisper `language`), `condition_on_previous_text=False`, the speaker engine (`convert_tool._patch_speakers`)
- 🟡 **Head count on short clips**: the eigenvalue gap is right on the 54-minute meeting and 2 of 4 sample clips under a minute (a 34-s two-voice clip came out as 3, a 57-s four-voice clip as 3); "People speaking" fixes it when known. Docling's built-in and sherpa's own pipeline did worse on the same clips

## 📋 Deferred by the owner

- (none — the layout work was done in round 4)

## 💡 Ideas (suggestions only — each says what it costs)

- 💡 Docling's vision engine (`--pipeline vlm`, granite-docling-258M) as a second opinion — measured 2026-09-13: 129 s for two pages against 16 s, same words, on the card. Not offered; ask if a hard layout ever needs it
- 💡 Windows Developer Mode would let the model cache use links (not needed: links are off and files are moved into place)
