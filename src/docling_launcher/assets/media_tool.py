"""Runs INSIDE Docling's environment (where PyAV lives): wraps a sound file into a video
container so Docling's video pipeline - the one with speaker separation - will take it.

    python media_tool.py wrap <sound file> <out.mkv>

The sound track is copied as it is (no re-encoding, no quality loss); a tiny black picture
track at one frame per second is added because the video pipeline expects one. Docling's
scene-change sampling then finds no scenes in it, so no pictures come out of the black.

WORKAROUND, 2026-09-12: Docling 2.126 offers "who said what" (diarization) only on the video
pipeline; the audio pipeline has the code but no switch. The owner chose to route audio
through video until Docling exposes it for audio - then app.py stops wrapping and this file
goes. Exit code 0 = wrapped, 1 = failed (the caller then sends the original sound file).
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path


def wrap(source: Path, target: Path) -> None:
    import av

    with av.open(str(source)) as inp:
        audio_in = next((s for s in inp.streams if s.type == "audio"), None)
        if audio_in is None:
            raise ValueError("no sound track")
        duration = float(inp.duration / av.time_base) if inp.duration else None
        target.parent.mkdir(parents=True, exist_ok=True)
        with av.open(str(target), mode="w") as out:
            try:
                audio_out = out.add_stream_from_template(audio_in)
            except AttributeError:  # PyAV < 13
                audio_out = out.add_stream(template=audio_in)
            video_out = out.add_stream("mpeg4", rate=1)
            video_out.width = 32
            video_out.height = 32
            video_out.pix_fmt = "yuv420p"

            seconds = int(duration) + 1 if duration else 1
            frame = av.VideoFrame(32, 32, "yuv420p")
            for plane in frame.planes:
                plane.update(bytes(plane.buffer_size))
            for index in range(seconds):
                frame.pts = index
                frame.time_base = Fraction(1, 1)
                for packet in video_out.encode(frame):
                    out.mux(packet)
            for packet in video_out.encode(None):
                out.mux(packet)

            for packet in inp.demux(audio_in):
                if packet.dts is None:
                    continue
                packet.stream = audio_out
                out.mux(packet)


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] != "wrap":
        print("usage: media_tool.py wrap <sound file> <out.mkv>")
        return 2
    source, target = Path(argv[1]), Path(argv[2])
    try:
        wrap(source, target)
    except Exception as exc:
        print(f"could not wrap {source.name}: {exc}")
        return 1
    print(f"wrapped {source.name} -> {target.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
