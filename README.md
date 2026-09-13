# Docling Launcher

Windows Tkinter desktop launcher for batch `docling convert` runs, with one-click updates of
Docling itself.

`TODO.md` is the status board: what is done, what is open, what was deferred and why.

## Layout of the project

| Path | What |
|---|---|
| `src/docling_launcher/` | the app. `app.py` window · `docling_cli.py` command building (`ConversionOptions`), one process per output folder, job object · `updates.py` version check with dates, upgrade with pins, restore points, GPU-edition guard · `models.py` + `assets/models_tool.py` model check/replace (runs in `.venv`) · `media.py` + `assets/media_tool.py` audio→video wrapper and transcript by speaker · `environment.py` extension status incl. GPU · `admin.py` elevated run |
| `.venv/` | **Docling's environment** — Python 3.12, Docling + OCR add-ins + speech/video (Whisper) + `kaldi-native-fbank` (voice features). The launcher finds `.venv\Scripts\docling.exe` next to the project and updates *this* folder |
| `tests/` | `python -m unittest discover tests -v` — real widgets on a withdrawn window, a stand-in `docling.exe` (`fake_docling.cmd`) |
| `app.py` | the window: sv_ttk (Windows 11 look, light/dark), tabs Convert · Settings · Updates · Log, Run bar with progress, results table, presets in the header, `dragdrop.py` (WM_DROPFILES via a window-procedure hook, no extra package). `DOCLING_LAUNCHER_SELFTEST=<file>` runs the exe withdrawn and writes a JSON report |
| `windows.py` · `watcher.py` · `safety.py` | keep-awake (SetThreadExecutionState), toast (PowerShell's notification identity), system theme (registry), Explorer menu (HKCU registry) · folder watching (ReadDirectoryChangesW on a thread, settle 5 s) · the reference check (assets/reference.pdf + reference_scan.png converted, compared with `settings.reference_baseline`) |
| `tools/snap_window.py` | pictures of every tab (light or dark) from a window the owner never sees — 1 % opacity, tool window, `WS_EX_NOACTIVATE`, bottom of the pile, printed with `PrintWindow(PW_RENDERFULLCONTENT)`; a window parked off-screen prints white |
| `launcher_update.py` | self-update from GitHub releases (`LAUNCHER_REPO`, public since 2026-09-13; a fine-grained token in Settings is only needed if it is made private again); `tools/release.ps1` tags, pushes and publishes `dist\DoclingLauncher.exe` |
| `assets/convert_tool.py` | **the road every run takes**: `convert` = Docling's own `docling.cli.main.app()` unchanged; `probe` = text-layer check per PDF (pypdfium2) for the automatic OCR decision; `describe` = Docling's `PictureDescriptionVlmModel` run directly on the PNGs a Markdown links, text written under each picture (better = granite-vision-3.3-2b with a technical prompt, small = SmolVLM). `DOCLING_CONVERT_TOOL` overrides the script (tests) |
| `build_exe.ps1` | builds `dist\DoclingLauncher.exe` (icon embedded) and the Desktop / Start-menu shortcuts |

## Pins and workarounds (2026-09-12) — see TODO.md "Open / watch"

- `transformers<5.8`: Docling 2.126's chart model (granite-vision-4.1-4b, loaded with `trust_remote_code=True`) breaks on 5.8+. `setuptools<80`: resemblyzer needs `pkg_resources`. Both in `constants.UPGRADE_PINS` (applied on every Update) and `build_exe.ps1`.
- `HF_HUB_DISABLE_SYMLINKS=1` on every Docling run and model download: the hub library's per-folder symlink probe crashed a download mid-way on Windows; without links files are moved into place (no duplicate blobs).
- Speaker separation exists only on Docling's video pipeline and only in the VTT output: sound files are wrapped into an MKV with a black frame track (`media_tool.py`), run through the video pipeline, and the VTT becomes the Markdown transcript by speaker.
- **Who said what, best engine** (2026-09-13): `assets/speakers_tool.py` is pyannote 3.1's pipeline in ONNX — segmentation-3.0 + WeSpeaker ResNet34-LM from sherpa-onnx's GitHub releases (downloaded by the model update into `%LOCALAPPDATA%\DoclingLauncher\models\speakers`), run on the GPU through onnxruntime-gpu, features by `kaldi-native-fbank` (sherpa's exact recipe: samples ×32768, 80 mel bins 20 Hz–7600 Hz, no dither, `snip_edges=False`, no CMN), spectral clustering with the eigenvalue gap. The driver (`convert_tool.py convert --launcher-speakers best`) swaps Docling's `diarize`/`assign_speakers` on `docling.pipeline.video_pipeline`, starts the separation right after the audio is extracted (beside Whisper), and assigns speakers word by word. `--launcher-language` sets Whisper's `language` on every preset; `condition_on_previous_text` is set to False explicitly (Docling's `None` already means off to Whisper — measured identical).
- OCR runtime: `onnxruntime-gpu[cuda,cudnn]==1.30.0` (CUDA 13, like torch cu130); `onnxruntime` (processor) must NOT be installed beside it — `build_exe.ps1` and `updates.restore_gpu_edition` remove it.
- Model rows in `constants.MODELS` carry Docling's pinned revision (the chart model is pinned to commit `dd48e975…`; a cleanup keeps exactly that copy).
- AI library: `torch 2.14.0+cu130` from the PyTorch index (`TORCH_INDEX_URL`); `updates.restore_gpu_edition` reinstalls it if an upgrade brings the CPU build.

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
