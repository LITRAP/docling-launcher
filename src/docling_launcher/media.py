"""Sound and video: the "who said what" workaround and the transcript-by-speaker Markdown.

Docling 2.126 separates speakers only on its VIDEO pipeline, and writes the speaker of
each line only into the WebVTT subtitle output. So, when "Who said what" is ticked:

1. a sound file is wrapped into a video container (assets/media_tool.py, no re-encoding)
   and Docling is given the wrapper instead — same file stem, so the outputs keep the name;
2. Docling is asked for VTT as well as whatever the owner chose;
3. afterwards the VTT is turned into a Markdown transcript grouped by speaker, which
   replaces Docling's speaker-less Markdown for that file.

The day Docling exposes diarization for audio and puts speakers into Markdown itself, the
three steps go and nothing else changes (the owner's decision, 2026-09-12).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess

from .assets import asset_path
from .constants import MEDIA_INPUT_EXTENSIONS
from .docling_cli import CREATE_NO_WINDOW, resolve_python

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}


def is_media(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_INPUT_EXTENSIONS


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def wrap_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
    return base / "DoclingLauncher" / "Temp" / "wrap"


def wrap_audio_as_video(source: Path) -> Path | None:
    """The video-container twin of a sound file, or None when wrapping failed (the caller
    then sends the sound file itself and loses only the speaker labels)."""
    python = resolve_python()
    tool = asset_path("media_tool.py")
    if not python or not tool.exists():
        return None
    # One folder per source path so two "meeting.mp3" in different folders never collide.
    folder = wrap_dir() / hashlib.sha1(str(source.resolve()).encode("utf-8")).hexdigest()[:12]
    target = folder / f"{source.stem}.mkv"
    try:
        result = subprocess.run(
            [str(python), str(tool), "wrap", str(source), str(target)],
            capture_output=True, text=True, timeout=600, creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        return None
    return target if result.returncode == 0 and target.is_file() else None


def discard_wrapper(target: Path) -> None:
    try:
        target.unlink()
        target.parent.rmdir()
    except OSError:
        pass


_CUE_TIME = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.\d{3} --> ")
_VOICE = re.compile(r"^<v ([^>]+)>(.*)$")


def speakers_markdown(vtt_text: str, title: str) -> str | None:
    """A Markdown transcript grouped by speaker, from a WebVTT with <v SPEAKER_xx> voices.
    None when the VTT carries no speaker tags (then Docling's own Markdown stands)."""
    turns: list[tuple[str, str, list[str]]] = []  # (speaker, start mm:ss, lines)
    names: dict[str, str] = {}
    start = ""
    saw_voice = False
    for raw in vtt_text.splitlines():
        line = raw.strip()
        match = _CUE_TIME.match(line)
        if match:
            hours, minutes, seconds = (int(x) for x in match.groups())
            start = f"{hours * 60 + minutes:02d}:{seconds:02d}"
            continue
        if not line or line == "WEBVTT" or "-->" in line:
            continue
        voice = _VOICE.match(line)
        if voice:
            saw_voice = True
            tag, text = voice.group(1).strip(), voice.group(2).strip()
            speaker = names.setdefault(tag, f"Speaker {len(names) + 1}")
        else:
            speaker, text = (turns[-1][0] if turns else "Speaker"), line
        if turns and turns[-1][0] == speaker:
            turns[-1][2].append(text)
        else:
            turns.append((speaker, start, [text]))
    if not saw_voice:
        return None
    parts = [f"# {title}", ""]
    for speaker, when, lines in turns:
        parts.append(f"**{speaker}** ({when})  ")
        parts.append(" ".join(lines))
        parts.append("")
    return "\n".join(parts)
