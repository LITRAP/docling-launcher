"""Runs INSIDE Docling's environment: who said what, the best local way.

    python speakers_tool.py <wav> [--speakers N] [--models FOLDER] [--json OUT] [--cpu]

Docling 2.126 tells voices apart with Resemblyzer (2019) on fixed 1.5-second windows and
guesses how many people talk from a silhouette score. On the owner's 54-minute meeting
(2026-09-13) that gave "2 speakers" with a silhouette of 0.13 - a coin toss - and a
transcript that changed speaker almost every sentence.

This module is the pipeline of pyannote 3.1, the reference open diarization, with its two
models in ONNX form (converted by the sherpa-onnx project; MIT and Apache licensed, no
account and no token needed), both run through onnxruntime on the graphics card, which
Docling's environment already carries for OCR:

1. pyannote **segmentation-3.0** looks at every ten-second window (one-second steps) and
   says, frame by frame, which of up to three local voices speak - including two at once.
2. **WeSpeaker ResNet34-LM** (the voice model pyannote 3.1 uses) turns each voice's speech
   in each window into a fingerprint. Its features are computed with kaldi-native-fbank
   exactly as sherpa-onnx computes them (checked: identical fingerprints to six decimals).
3. The fingerprints are grouped by spectral clustering: the common "room and microphone"
   component is removed, each fingerprint keeps its ten percent strongest links, and the
   eigenvalues of the graph say how many voices there are (the meeting's read 0, 0.04,
   0.11, 0.12, then 0.44: four people). pyannote's own tree clustering agreed on the same
   four groups (Rand index 0.89) but its threshold collapsed to one group or split into
   dozens with a hair's change, so the graph method is the one shipped. When the number of
   people is known, that many groups are made.
4. The window verdicts are averaged back onto one time line and turned into speech turns
   per speaker (gaps under half a second closed, turns under 0.3 s dropped).

Output: a list of (start, end, "SPEAKER_nn") turns, which may overlap when two people
talk at once. A single file with no launcher imports; shipped inside the exe as an asset.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

SEGMENTATION_FILE = "pyannote-segmentation-3.0.onnx"
EMBEDDING_FILE = "wespeaker-resnet34-LM.onnx"
MIN_DURATION_ON = 0.3
MIN_DURATION_OFF = 0.5
MIN_FRAMES = 10       # a local voice with fewer active frames (~0.17 s) gets no fingerprint
MAX_SPEAKERS = 8
NEIGHBOURS = 0.10     # each fingerprint keeps its strongest 10 % of links ...
MIN_NEIGHBOURS = 20   # ... and never fewer than twenty: a short clip's graph must stay in one piece
BUCKET_FRAMES = 20    # fingerprint inputs cut to fifths of a second (see Fingerprints.embed_all)
MIN_BUCKET_FRAMES = 50  # ... and stretched to half a second when shorter
BATCH = 32
MAX_FOR_EIGEN = 4000  # more fingerprints than this: cluster a sample, place the rest by nearest group


def models_dir() -> Path:
    override = os.environ.get("DOCLING_LAUNCHER_SPEAKER_MODELS")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "DoclingLauncher" / "models" / "speakers"


def models_present(folder: Path | None = None) -> bool:
    folder = folder or models_dir()
    return (folder / SEGMENTATION_FILE).is_file() and (folder / EMBEDDING_FILE).is_file()


def _session(path: Path, device: str):
    """An onnxruntime session on the card when there is one (its CUDA libraries come from
    the pip packages beside torch and must be loaded first), else on the CPU."""
    import onnxruntime as ort
    providers = ["CPUExecutionProvider"]
    if device != "cpu" and "CUDAExecutionProvider" in ort.get_available_providers():
        if hasattr(ort, "preload_dlls"):
            try:
                ort.preload_dlls()
            except Exception:
                pass
        providers.insert(0, "CUDAExecutionProvider")
    options = ort.SessionOptions()
    options.log_severity_level = 3
    session = ort.InferenceSession(str(path), sess_options=options, providers=providers)
    return session, ("cuda" if session.get_providers()[0].startswith("CUDA") else "cpu")


# ----------------------------------------------------------------------------- step 1

class Segmentation:
    """pyannote segmentation-3.0 through onnxruntime."""

    def __init__(self, path: Path, device: str = "auto"):
        self.session, self.device = _session(path, device)
        meta = self.session.get_modelmeta().custom_metadata_map
        self.sample_rate = int(meta["sample_rate"])
        self.window = int(meta["window_size"])
        self.step = self.window // 10
        self.field = int(meta["receptive_field_size"])
        self.field_step = int(meta["receptive_field_shift"])
        self.local_speakers = int(meta["num_speakers"])
        self.classes = int(meta["num_classes"])
        self.max_at_once = int(meta["powerset_max_classes"])
        self.input = self.session.get_inputs()[0].name
        self.output = self.session.get_outputs()[0].name

    def powerset_map(self) -> np.ndarray:
        """Class index -> which local speakers are active (7 classes: none, 3 singles, 3 pairs)."""
        mapping = np.zeros((self.classes, self.local_speakers), dtype=np.float32)
        k = 1
        for j in range(self.local_speakers):
            mapping[k, j] = 1
            k += 1
        if self.max_at_once >= 2:
            for j in range(self.local_speakers):
                for m in range(j + 1, self.local_speakers):
                    mapping[k, j] = mapping[k, m] = 1
                    k += 1
        return mapping

    def run(self, audio: np.ndarray, batch: int = 32) -> np.ndarray:
        """(windows, frames, local speakers) 0/1 activity for every window of the audio."""
        if len(audio) < self.window:
            audio = np.pad(audio, (0, self.window - len(audio)))
        count = (len(audio) - self.window) // self.step + 1
        tail = (len(audio) - self.window) % self.step > 0
        windows = np.lib.stride_tricks.as_strided(
            audio, shape=(count, self.window), strides=(self.step * audio.strides[0], audio.strides[0]),
        )
        outputs = []
        for start in range(0, count, batch):
            chunk = np.ascontiguousarray(windows[start:start + batch])[:, None, :]
            outputs.append(self.session.run([self.output], {self.input: chunk})[0])
        if tail:
            last = audio[count * self.step:]
            last = np.pad(last, (0, self.window - len(last)))[None, None, :]
            outputs.append(self.session.run([self.output], {self.input: last})[0])
        logits = np.concatenate(outputs, axis=0)
        return self.powerset_map()[np.argmax(logits, axis=-1)]

    def frame_time(self, frame: int) -> float:
        return (frame * self.field_step + self.field / 2) / self.sample_rate


# ----------------------------------------------------------------------------- step 2

class Fingerprints:
    """WeSpeaker ResNet34-LM through onnxruntime, fed sherpa-onnx's exact features:
    samples x 32768, 80 mel bins from 20 Hz to (Nyquist - 400) Hz, no dither, edges kept."""

    def __init__(self, path: Path, device: str = "auto"):
        import kaldi_native_fbank as knf
        self.session, self.device = _session(path, device)
        self.input = self.session.get_inputs()[0].name
        self.options = knf.FbankOptions()
        self.options.frame_opts.dither = 0
        self.options.frame_opts.samp_freq = 16000
        self.options.frame_opts.snip_edges = False
        self.options.mel_opts.num_bins = 80
        self.options.mel_opts.low_freq = 20.0
        self.options.mel_opts.high_freq = -400.0
        self.knf = knf

    def features(self, samples: np.ndarray) -> np.ndarray:
        bank = self.knf.OnlineFbank(self.options)
        bank.accept_waveform(16000, (samples * 32768.0).astype(np.float32))
        bank.input_finished()
        return np.stack([bank.get_frame(i) for i in range(bank.num_frames_ready)]).astype(np.float32)

    def embed_all(self, utterances: list[np.ndarray]) -> np.ndarray:
        """Fingerprints of many utterances. The card re-plans the network for every new
        input length (44 ms a run instead of 3), so the features are cut to a fifth of a
        second (an utterance under half a second is repeated up to half a second - its
        pooled statistics stay the same) and all utterances of one length go in one batch.
        Checked against exact one-by-one fingerprints: cosine 0.99 median, 0.95 for
        utterances over two seconds; four times faster."""
        features = [self.features(u) for u in utterances]
        by_length: dict[int, list[int]] = {}
        for index, frames in enumerate(features):
            length = max(MIN_BUCKET_FRAMES, (len(frames) // BUCKET_FRAMES) * BUCKET_FRAMES)
            by_length.setdefault(length, []).append(index)
        out = np.zeros((len(features), self.session.get_outputs()[0].shape[-1]), dtype=np.float32)
        for length, indexes in sorted(by_length.items()):
            for start in range(0, len(indexes), BATCH):
                chunk = indexes[start:start + BATCH]
                block = np.stack([np.resize(features[i], (length, features[i].shape[1])) for i in chunk])
                out[chunk] = self.session.run(None, {self.input: block})[0]
        return out


def fingerprints(model: Fingerprints, audio: np.ndarray, activity: np.ndarray, seg: Segmentation,
                 exclude_overlap: bool = True) -> tuple[list[tuple[int, int]], np.ndarray]:
    """One fingerprint per (window, local voice) that speaks long enough. Overlapped frames
    are left out of the fingerprint when enough clean speech remains."""
    windows, frames, voices = activity.shape
    clean = activity * (activity.sum(axis=-1, keepdims=True) < 2) if exclude_overlap else activity
    pairs: list[tuple[int, int]] = []
    utterances: list[np.ndarray] = []
    for w in range(windows):
        offset = w * seg.step
        for j in range(voices):
            mask = clean[w, :, j] if clean[w, :, j].sum() >= MIN_FRAMES else activity[w, :, j]
            if mask.sum() < MIN_FRAMES:
                continue
            # The active frames as sample ranges, concatenated into one utterance.
            edges = np.flatnonzero(np.diff(np.concatenate(([0], mask, [0]))))
            pieces = []
            for start, end in zip(edges[::2], edges[1::2]):
                a = int(start / frames * seg.window) + offset
                b = int(end / frames * seg.window) + offset
                pieces.append(audio[a:b])
            utterance = np.concatenate(pieces)
            if len(utterance) < 1600:  # under 0.1 s: no usable features
                continue
            utterances.append(utterance)
            pairs.append((w, j))
    if not utterances:
        return [], np.zeros((0, 1), dtype=np.float32)
    return pairs, model.embed_all(utterances)


# ----------------------------------------------------------------------------- step 3

def cluster(vectors: np.ndarray, num_speakers: int | None = None, log=None) -> np.ndarray:
    """Spectral clustering of the fingerprints; the eigenvalue gap decides how many
    voices unless the number is given. Labels 0, 1, 2 ... in order of first appearance."""
    n = len(vectors)
    if n == 0:
        return np.zeros(0, dtype=int)
    if n < 4:
        return np.zeros(n, dtype=int)
    unit = vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-8)
    centred = unit - unit.mean(axis=0)
    unit = centred / np.maximum(np.linalg.norm(centred, axis=1, keepdims=True), 1e-8)

    rng = np.random.default_rng(0)
    sample = np.arange(n) if n <= MAX_FOR_EIGEN else np.sort(rng.choice(n, MAX_FOR_EIGEN, replace=False))
    labels_sample, wanted = _spectral(unit[sample], num_speakers, log)
    if len(sample) == n:
        labels = labels_sample
    else:
        centroids = np.stack([unit[sample][labels_sample == k].mean(axis=0) for k in range(wanted)])
        labels = np.argmax(unit @ centroids.T, axis=1)
    return _renumber(labels)


def _spectral(unit: np.ndarray, num_speakers: int | None, log) -> tuple[np.ndarray, int]:
    from sklearn.cluster import KMeans
    n = len(unit)
    affinity = unit @ unit.T
    np.fill_diagonal(affinity, 0.0)
    keep = min(n - 1, max(int(NEIGHBOURS * n), MIN_NEIGHBOURS))
    floor = -np.sort(-affinity, axis=1)[:, keep - 1][:, None]
    affinity = np.where(affinity >= floor, affinity, 0.0)
    affinity = np.maximum(affinity, affinity.T)
    affinity = np.maximum(affinity, 0.0)
    degree = 1.0 / np.sqrt(np.maximum(affinity.sum(axis=1), 1e-8))
    laplacian = np.eye(n) - degree[:, None] * affinity * degree[None, :]
    values, vectors = np.linalg.eigh(laplacian)
    top = min(MAX_SPEAKERS, n - 1)
    if num_speakers and num_speakers >= 1:
        wanted = min(num_speakers, n)
    else:
        gaps = np.diff(values[: top + 1])
        wanted = int(np.argmax(gaps)) + 1
    if log:
        log("speakers: eigenvalues " + " ".join(f"{v:.3f}" for v in values[: top + 1]) + f" -> {wanted}")
    if wanted <= 1:
        return np.zeros(n, dtype=int), 1
    basis = vectors[:, :wanted]
    basis = basis / np.maximum(np.linalg.norm(basis, axis=1, keepdims=True), 1e-8)
    return KMeans(wanted, n_init=10, random_state=0).fit_predict(basis), wanted


def _renumber(labels: np.ndarray) -> np.ndarray:
    """0, 1, 2 ... in order of first appearance, so SPEAKER_00 is whoever speaks first."""
    order: dict[int, int] = {}
    for value in labels.tolist():
        order.setdefault(value, len(order))
    return np.array([order[v] for v in labels.tolist()], dtype=int)


# ----------------------------------------------------------------------------- step 4

def turns(activity: np.ndarray, pairs: list[tuple[int, int]], labels: np.ndarray,
          seg: Segmentation, total_samples: int) -> list[tuple[float, float, str]]:
    """Window verdicts averaged onto one time line -> speech turns per speaker."""
    windows, frames, voices = activity.shape
    speakers = int(labels.max()) + 1 if len(labels) else 0
    if not speakers:
        return []
    frame_step = seg.step / seg.field_step
    total_frames = int(round((windows - 1) * frame_step)) + frames
    votes = np.zeros((total_frames, speakers), dtype=np.float32)
    weight = np.zeros(total_frames, dtype=np.float32)
    who = {pair: label for pair, label in zip(pairs, labels.tolist())}
    for w in range(windows):
        start = int(round(w * frame_step))
        end = start + frames
        for j in range(voices):
            label = who.get((w, j))
            if label is not None:
                votes[start:end, label] += activity[w, :, j]
        weight[start:end] += 1
    votes /= np.maximum(weight, 1)[:, None]
    active = (votes > 0.5)[: int(total_samples / seg.field_step)]

    result: list[tuple[float, float, str]] = []
    for k in range(speakers):
        column = active[:, k].astype(np.int8)
        edges = np.flatnonzero(np.diff(np.concatenate(([0], column, [0]))))
        runs = [(seg.frame_time(int(a)), seg.frame_time(int(b))) for a, b in zip(edges[::2], edges[1::2])]
        merged: list[list[float]] = []
        for a, b in runs:
            if merged and a - merged[-1][1] < MIN_DURATION_OFF:
                merged[-1][1] = b
            else:
                merged.append([a, b])
        result.extend((a, b, f"SPEAKER_{k:02d}") for a, b in merged if b - a >= MIN_DURATION_ON)
    result.sort()
    return result


# ----------------------------------------------------------------------------- all together

def diarize(wav_path: Path, num_speakers: int | None = None, device: str = "auto",
            folder: Path | None = None, log=print) -> tuple[list[tuple[float, float, str]], int]:
    """Speech turns of the WAV, and how many speakers were found."""
    import soundfile as sf
    folder = folder or models_dir()
    started = time.time()
    seg = Segmentation(folder / SEGMENTATION_FILE, device)
    audio, rate = sf.read(str(wav_path), dtype="float32", always_2d=True)
    audio = np.ascontiguousarray(audio[:, 0])
    if rate != seg.sample_rate:
        import librosa
        audio = librosa.resample(audio, orig_sr=rate, target_sr=seg.sample_rate)
    activity = seg.run(audio)
    log(f"speakers: {activity.shape[0]} windows judged on {seg.device} in {time.time() - started:.0f} s")
    started = time.time()
    voices = Fingerprints(folder / EMBEDDING_FILE, device)
    pairs, vectors = fingerprints(voices, audio, activity, seg)
    log(f"speakers: {len(pairs)} voice fingerprints on {voices.device} in {time.time() - started:.0f} s")
    started = time.time()
    labels = cluster(vectors, num_speakers, log)
    result = turns(activity, pairs, labels, seg, len(audio))
    found = len({t[2] for t in result})
    log(f"speakers: {found} found in {time.time() - started:.0f} s" + (f" (asked for {num_speakers})" if num_speakers else ""))
    return result, found


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    wav, num, folder, out, device = None, None, None, None, "auto"
    rest = list(argv)
    while rest:
        item = rest.pop(0)
        if item == "--speakers" and rest:
            num = int(rest.pop(0)) or None
        elif item == "--models" and rest:
            folder = Path(rest.pop(0))
        elif item == "--json" and rest:
            out = Path(rest.pop(0))
        elif item == "--cpu":
            device = "cpu"
        else:
            wav = Path(item)
    if not wav or not wav.is_file():
        print("speakers_tool: no WAV file given")
        return 2
    result, found = diarize(wav, num, device=device, folder=folder)
    minutes: dict[str, float] = {}
    for a, b, who in result:
        minutes[who] = minutes.get(who, 0.0) + (b - a)
    for who in sorted(minutes):
        print(f"  {who}: {minutes[who] / 60:.1f} min")
    if out:
        out.write_text(json.dumps([[round(a, 2), round(b, 2), who] for a, b, who in result]), encoding="utf-8")
    print(f"DONE {found}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
