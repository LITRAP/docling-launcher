# What was learned building this

Facts that cost time to find. Everything here was measured or read from source, not
assumed; where a number is quoted, the machine is the owner's (Windows 11, RTX A4000
16 GB, Docling 2.126, torch 2.14+cu130) and the date is when it was measured.

---

## 1 · What each ability costs (2026-09-21, GPU in use)

Measured on a 68-page engineering standard (33 figures, 50 formulas) and a 54-minute
meeting recording. These are the numbers `estimate.py` is seeded with.

| Run | Time |
|---|---|
| The standard, text and tables only | **41 s** |
| …plus formulas as LaTeX | **82 s** (formulas are cheap: ~0.6 s a page) |
| …plus charts as tables | **508 s** (the chart model is ~6.3 s **a page**, whether or not the page has a chart) |
| Describing its 33 pictures (separate pass) | **421 s** (~13 s a picture) — 625 s with the older, looser instruction |
| Whole-page OCR, five pages | 5.8 s on the GPU vs ~19 s on the processor |
| The meeting, transcript + speakers | **377 s** (speaker separation runs beside Whisper and adds no wait) |

Inside the speaker separation of that meeting: segmentation 15 s, 6 097 voice
fingerprints 50 s (**300 s** before they were bucketed and batched), grouping 9–36 s.

`estimate.py` multiplies these by a **machine factor** it learns from each batch
(`actual / estimated`, a third of the way, only when both exceed 20 s, bounded 0.05–20)
and by a learned **pictures per page**. Both live in `settings.speed`.

## 2 · What the models actually do

**The chart model** (`ibm-granite/granite-vision-4.1-4b`, 8 GB, pinned to a commit)
turns a chart into a table of values. Checked against the pictures on three figures of
the standard:

| Figure | Verdict |
|---|---|
| One smooth curve, linear axes | roughly right |
| A nomogram: thirty curves, log scales, two vertical axes | **invented** — every row carried `Q = 14.0`, which is the worked-example value *printed on the figure* |
| A curve whose vertical axis runs downwards | **invented** |

So: **off by default**, a tick for reports with simple bar/pie/line charts, and every
table it writes gets `CHART_TABLE_NOTE` under it (`chart_note.mark_chart_tables`, run
after Docling, idempotent, real document tables untouched).

**The describing model** (`ibm-granite/granite-vision-3.3-2b`, 6 GB) writes a few
sentences under each picture. It is small: it reads diagrams and simple charts usefully
and misreads busy ones. Its instruction is in `constants.DEFAULT_DESCRIBE_PROMPT` —
"two to four sentences, quote text exactly, a logo is a logo, do not guess what
abbreviations stand for". The loose earlier wording had it explain the standards body's
initials as a completely different organisation and write a paragraph per logo.
`PREVIOUS_DESCRIBE_PROMPTS` lets a stale default be refreshed; a wording the owner typed
themselves is never replaced.

**The formula model** is cheap and reliable: without it every formula in the Markdown is
a `<!-- formula-not-decoded -->` placeholder — which is exactly how the owner discovered
that these abilities were off by default (2026-09-21).

## 3 · Who said what

`assets/speakers_tool.py` is pyannote 3.1's pipeline in ONNX, because Docling's own
separation (Resemblyzer on fixed 1.5-second windows, head count by silhouette) reported
"2 speakers" with a silhouette of 0.13 on the owner's meeting and changed speaker almost
every sentence.

- **Models**: `pyannote-segmentation-3.0` + `wespeaker-resnet34-LM`, ONNX conversions
  from the sherpa-onnx project's GitHub releases (MIT / Apache, no account, 33 MB), kept
  in `%LOCALAPPDATA%\DoclingLauncher\models\speakers`, downloaded by `models_tool.py`.
- **Features must match sherpa's recipe exactly**: samples × 32768, 80 mel bins from
  20 Hz to Nyquist − 400, dither 0, `snip_edges=False`, **no** cepstral mean subtraction.
  With CMN the fingerprints are unrecognisable (cosine 0.09); with the right recipe they
  match sherpa's own to six decimals.
- **onnxruntime on the GPU needs `ort.preload_dlls()` first**, or the CUDA provider
  cannot find `cublasLt` and silently falls back to the processor.
- **The CUDA provider re-plans the network for every new input length** (44 ms a run
  instead of 3). Cut the features to fifths of a second, stretch anything under half a
  second, batch by length: 46 s instead of 300 s, fingerprints still cosine 0.997.
- **Grouping**: spectral clustering on mean-centred unit vectors, the eigenvalue gap
  decides the count. pyannote's own centroid-linkage threshold collapsed to one group on
  this recording and exploded into seventeen a hair away.
- **Speakers are assigned word by word**, and a cut inside a Whisper phrase snaps back to
  the phrase's start (`_snap_to_phrases`) — the owner confirmed the case: a listener
  began a question over the presenter's last words and the voice change was only heard
  four words in.
- **Whisper**: turbo is the best in practice here. Its `condition_on_previous_text=None`
  already means *off* (the whole meeting came out 99.85 % identical when set explicitly);
  the language is worth telling it, because it guesses from the first 30 seconds only.
- **The head count is the hard part.** On a laptop microphone across a room, one person's
  short interjections ("oui, oui") and their sentences form two voice groups: a
  three-person meeting reads as four. Tried and rejected: counting on utterances over
  1 / 1.5 / 2 s (still four), over 3 s (three, but then the third person starts eleven
  minutes early), merging by raw similarity (would merge the presenter with the third
  person), merging by overlap in time (42 s of "one person talking over themselves").
  **"People speaking" is the answer**; a microphone on the table is the real fix.

## 4 · Docling internals this depends on

Everything goes through `assets/convert_tool.py`, which runs inside `.venv` and calls
`docling.cli.main.app()` unchanged — plus what the command line cannot say:

| Flag | What it reaches into |
|---|---|
| `--launcher-language xx` | sets `language` on every `InlineAsrNativeWhisperOptions` preset (the CLI has no such flag) and `condition_on_previous_text=False` |
| `--launcher-speakers best\|docling` | replaces `diarize`, `assign_speakers` and `_extract_audio` **on `docling.pipeline.video_pipeline`** (it imported them by name), so the separation starts beside Whisper |
| `--launcher-people N` | a known head count for either engine |

Picture descriptions are **not** asked of Docling: its pipeline would put the describing
model (6 GB) and the chart model (8 GB) on the card together — eleven minutes for nine
pages — and it never describes video frames. They are a pass of their own afterwards,
run on the PNGs the Markdown links.

Model revisions are **pinned** in `constants.MODELS`, because Docling pins the chart
model to a commit and a cleanup that deleted it cost an 8 GB re-download.

## 5 · Traps, each paid for once

1. **A worker thread must never read a Tk variable.** Tk refuses off its own thread, the
   exception was swallowed, and the new strip simply stayed empty. Pass plain values in.
2. **Anything that saves settings from inside the window's constructor runs before
   `main()` can raise the self-test flag.** The first 1.5.2 self-test wrote the owner's
   real settings. `_selftest` is now read from the environment at the top of `__init__`,
   and `_save_settings` itself refuses during a proof run.
3. **Any script that drives the real app writes the real `%APPDATA%`** — override it.
4. **The exe cannot be rebuilt while the launcher is open.** The build script fails
   loudly instead of printing "Built" over yesterday's file.
5. **`gh release create` with the commit message as an argument breaks on quotes** — and
   the script still printed "Released". Notes go through `--notes-file`, the exit code is
   checked, and the release is asked for afterwards.
6. **Python text pipes split on `\r`** — wrap with `newline="\n"` or a progress bar
   becomes a hundred log lines.
7. **`HF_HUB_DISABLE_SYMLINKS=1` on every Docling run and model download** — the hub's
   symlink probe crashed a download mid-way (WinError 1314).
8. **The `typing` backport breaks PyInstaller** — `build_exe.ps1` uninstalls it first.
9. **`.gitignore` must say `.venv*/`** — `.venv/` alone let a 33 000-file old
   environment into two commits.
10. **A ttk widget measures itself with Tk's default font at build time**; the theme's
    font arrives later. Measure in a sync step, not in the constructor.
11. **`.venv` cannot be renamed while an editor holds the folder**, and a moved venv does
    not start (absolute paths are baked into its launchers).
12. **A window parked entirely off-screen prints white.** `tools/snap_window.py` shows it
    at 1 % opacity as a non-activating tool window at the bottom of the pile instead.
