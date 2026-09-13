"""Runs INSIDE Docling's environment (that is where huggingface_hub and whisper live):
checks, downloads and replaces the AI models the launcher's abilities use.

    python models_tool.py check   '<json list of [label, repo, revision, gb]>' <whisper_name>
    python models_tool.py update  '<json list of [label, repo, revision, gb]>' <whisper_name or ->

`check` prints one JSON object per line: {"repo", "installed_sha", "installed_on",
"latest_sha", "latest_on", "state"} where state is one of "missing", "current", "newer",
"offline". The whisper line uses "whisper:<name>" as its repo; the who-said-what models
(two ONNX files from the sherpa-onnx project's GitHub releases, not the model hub) use
"speakers:pyannote3" and live in LOCALAPPDATA/DoclingLauncher/models/speakers.

`update` downloads every listed model at its pinned revision (only the files this machine
loads - no ONNX/GGUF/MLX copies), then deletes every OTHER cached revision of that repo
through huggingface_hub's own cache manager, which removes only what it can prove is
unreferenced. Progress lines are plain text; the last line is "DONE <n replaced> <n failed>".

Shipped inside the exe as an asset and run with the environment's python; it must stay a
single file with no imports from the launcher package.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

IGNORE = ["onnx/*", "*.onnx", "*.gguf", "*.bin", "*.h5", "*.msgpack", "*mlx*", "*.tflite", "*.ot"]


def hub_cache() -> Path:
    from huggingface_hub.constants import HF_HUB_CACHE
    return Path(HF_HUB_CACHE)


def repo_folder(repo: str) -> Path:
    return hub_cache() / ("models--" + repo.replace("/", "--"))


def installed_revision(repo: str, revision: str) -> tuple[str | None, str | None]:
    """The sha the cache holds for `revision` of `repo`, and the day it was downloaded."""
    folder = repo_folder(repo)
    ref = folder / "refs" / revision
    sha = None
    if ref.is_file():
        sha = ref.read_text(encoding="utf-8").strip()
    elif len(revision) >= 8 and (folder / "snapshots" / revision).is_dir():
        sha = revision
    if not sha:
        return None, None
    snapshot = folder / "snapshots" / sha
    if not snapshot.is_dir() or not any(snapshot.iterdir()):
        return None, None
    # A download in progress, or one that was interrupted, leaves *.incomplete blobs behind
    # and a snapshot with only some of its files: that is not an installed model.
    if any((folder / "blobs").glob("*.incomplete")):
        return None, None
    return sha, datetime.fromtimestamp(snapshot.stat().st_mtime).strftime("%Y-%m-%d")


def latest_revision(repo: str, revision: str) -> tuple[str | None, str | None]:
    try:
        from huggingface_hub import HfApi
        info = HfApi().model_info(repo, revision=revision, timeout=8)
        when = info.last_modified.strftime("%Y-%m-%d") if info.last_modified else None
        return info.sha, when
    except Exception:
        return None, None


def whisper_root() -> Path:
    return Path(os.path.expanduser("~")) / ".cache" / "whisper"


# Whisper saves a model under the last part of its download URL, which for two of them is
# not the short name a person chooses ("turbo" lands as large-v3-turbo.pt).
WHISPER_FILES = {"turbo": "large-v3-turbo.pt", "large": "large-v3.pt"}


def whisper_file(name: str) -> Path:
    return whisper_root() / WHISPER_FILES.get(name, f"{name}.pt")


def whisper_installed(name: str) -> tuple[str | None, str | None]:
    path = whisper_file(name)
    if not path.is_file():
        return None, None
    return name, datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


SPEAKER_RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download/{tag}/{asset}"
SPEAKER_API = "https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/tags/{tag}"
# file kept locally -> (release tag, asset name, member inside the archive or None, size)
SPEAKER_FILES = {
    "pyannote-segmentation-3.0.onnx": ("speaker-segmentation-models", "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
                                       "sherpa-onnx-pyannote-segmentation-3-0/model.onnx", 6958444),
    "wespeaker-resnet34-LM.onnx": ("speaker-recongition-models", "wespeaker_en_voxceleb_resnet34_LM.onnx", None, 26530550),
}


def speakers_dir() -> Path:
    override = os.environ.get("DOCLING_LAUNCHER_SPEAKER_MODELS")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "DoclingLauncher" / "models" / "speakers"


def speakers_installed() -> tuple[str | None, str | None]:
    """("pyannote3+wespeaker", date) when both files are present, else (None, None)."""
    folder = speakers_dir()
    stamps = []
    for name in SPEAKER_FILES:
        path = folder / name
        if not path.is_file() or path.stat().st_size < 1024:
            return None, None
        stamps.append(path.stat().st_mtime)
    return "pyannote3+wespeaker", datetime.fromtimestamp(min(stamps)).strftime("%Y-%m-%d")


def speakers_latest() -> tuple[str | None, str | None]:
    """The newest date GitHub shows for the two assets, or (None, None) when offline."""
    from urllib.request import Request, urlopen
    newest = None
    for _local, (tag, asset, _member, _size) in SPEAKER_FILES.items():
        try:
            with urlopen(Request(SPEAKER_API.format(tag=tag), headers={"User-Agent": "docling-launcher"}), timeout=15) as reply:
                release = json.loads(reply.read().decode("utf-8"))
        except Exception:
            return None, None
        for item in release.get("assets", []):
            if item.get("name") == asset:
                stamp = (item.get("updated_at") or "")[:10]
                newest = max(newest or "", stamp)
    return "pyannote3+wespeaker", newest


def speakers_update() -> None:
    """Download both files (the segmentation one sits inside a .tar.bz2); a file already
    present at its full size is left alone."""
    import shutil
    import tarfile
    import tempfile
    from urllib.request import Request, urlopen
    folder = speakers_dir()
    folder.mkdir(parents=True, exist_ok=True)
    for local, (tag, asset, member, size) in SPEAKER_FILES.items():
        target = folder / local
        if target.is_file() and target.stat().st_size > 1024:
            continue
        url = SPEAKER_RELEASES.format(tag=tag, asset=asset)
        print(f"Downloading {asset} ({size / 1e6:.0f} MB).", flush=True)
        with tempfile.TemporaryDirectory() as temp:
            packed = Path(temp) / asset
            with urlopen(Request(url, headers={"User-Agent": "docling-launcher"}), timeout=60) as reply, open(packed, "wb") as out:
                shutil.copyfileobj(reply, out)
            if member:
                with tarfile.open(packed, "r:bz2") as archive:
                    with archive.extractfile(member) as inner, open(target, "wb") as out:
                        shutil.copyfileobj(inner, out)
            else:
                shutil.move(str(packed), str(target))
        print(f"Downloaded {local}.", flush=True)


def check(models: list, whisper_name: str, online: bool = True) -> None:
    for label, repo, revision, _gb in models:
        if repo.startswith("speakers:"):
            sha, on = speakers_installed()
            latest, latest_on = speakers_latest() if online else (None, None)
            # The files are fixed downloads: present is current. A newer release date is
            # shown for information; the files are only fetched when missing.
            state = "missing" if sha is None else ("current" if (latest or not online) else "offline")
            print(json.dumps({"repo": repo, "installed_sha": sha, "installed_on": on,
                              "latest_sha": latest, "latest_on": latest_on, "state": state}), flush=True)
            continue
        sha, on = installed_revision(repo, revision)
        latest, latest_on = latest_revision(repo, revision) if online else (None, None)
        if sha is None:
            state = "missing"
        elif latest is None:
            state = "offline" if online else "unchecked"
        elif latest == sha:
            state = "current"
        else:
            state = "newer"
        print(json.dumps({"repo": repo, "installed_sha": sha, "installed_on": on,
                          "latest_sha": latest, "latest_on": latest_on, "state": state}), flush=True)
    if whisper_name and whisper_name != "-":
        name, on = whisper_installed(whisper_name)
        # Whisper's files are fixed downloads named by their content hash: never "newer".
        print(json.dumps({"repo": f"whisper:{whisper_name}", "installed_sha": name, "installed_on": on,
                          "latest_sha": whisper_name, "latest_on": None,
                          "state": "current" if name else "missing"}), flush=True)


def download(repo: str, revision: str, gb: float) -> str:
    from huggingface_hub import snapshot_download
    print(f"Downloading {repo} ({gb:.1f} GB). This can take a while; progress is not shown.", flush=True)
    started = time.time()
    path = snapshot_download(repo, revision=revision, ignore_patterns=IGNORE)
    print(f"Downloaded {repo} in {time.time() - started:.0f} s.", flush=True)
    return Path(path).name  # the snapshot folder is named by the sha


def delete_other_revisions(repo: str, keep_sha: str) -> None:
    from huggingface_hub import scan_cache_dir
    info = scan_cache_dir()
    for cached in info.repos:
        if cached.repo_id != repo:
            continue
        stale = [rev.commit_hash for rev in cached.revisions if rev.commit_hash != keep_sha]
        if not stale:
            return
        strategy = info.delete_revisions(*stale)
        print(f"Removing {len(stale)} old copy(ies) of {repo}: frees {strategy.expected_freed_size_str}.", flush=True)
        strategy.execute()


def update(models: list, whisper_name: str) -> None:
    replaced = failed = 0
    for label, repo, revision, gb in models:
        if repo.startswith("speakers:"):
            try:
                speakers_update()
                replaced += 1
            except Exception as exc:
                failed += 1
                print(f"FAILED {repo}: {exc}", flush=True)
            continue
        try:
            sha = download(repo, revision, gb)
            delete_other_revisions(repo, sha)
            replaced += 1
        except Exception as exc:
            failed += 1
            print(f"FAILED {repo}: {exc}", flush=True)
    if whisper_name and whisper_name != "-":
        try:
            import whisper
            root = whisper_root()
            root.mkdir(parents=True, exist_ok=True)
            if not whisper_file(whisper_name).is_file():
                print(f"Downloading the {whisper_name} speech model.", flush=True)
                whisper._download(whisper._MODELS[whisper_name], str(root), False)
                print(f"Downloaded the {whisper_name} speech model.", flush=True)
            replaced += 1
        except Exception as exc:
            failed += 1
            print(f"FAILED whisper {whisper_name}: {exc}", flush=True)
    print(f"DONE {replaced} {failed}", flush=True)


def main(argv: list[str]) -> int:
    command, spec, whisper_name = argv[0], json.loads(argv[1]), (argv[2] if len(argv) > 2 else "-")
    if command == "check":
        check(spec, whisper_name)
    elif command == "check-offline":
        check(spec, whisper_name, online=False)
    elif command == "update":
        update(spec, whisper_name)
    else:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
