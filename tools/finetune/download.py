"""Download a pinned base model and verify every file against Hugging Face's checksums.

Usage: uv run --project tools/finetune python tools/finetune/download.py qwen3-0.6b
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME = Path.home() / ".cache/psychiatryeduai/models/hf"


def tree(repo: str, revision: str) -> list[dict]:
    url = f"https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true"
    with urllib.request.urlopen(url, timeout=60) as response:
        return [e for e in json.load(response) if e["type"] == "file"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def main(name: str) -> Path:
    spec = json.loads((ROOT / "config/finetune.json").read_text())["base_models"][name]
    target = HOME / f"{spec['repo'].split('/')[1]}-{spec['revision'][:12]}"
    target.mkdir(parents=True, exist_ok=True)
    for entry in tree(spec["repo"], spec["revision"]):
        path = target / entry["path"]
        lfs = entry.get("lfs")
        ok = path.exists() and path.stat().st_size == entry["size"] and (
            sha256(path) == lfs["oid"] if lfs else git_blob_sha1(path) == entry["oid"])
        if not ok:
            path.parent.mkdir(parents=True, exist_ok=True)
            url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{entry['path']}"
            print(f"Downloading {entry['path']} ({entry['size']} bytes)")
            urllib.request.urlretrieve(url, path)
            ok = path.stat().st_size == entry["size"] and (
                sha256(path) == lfs["oid"] if lfs else git_blob_sha1(path) == entry["oid"])
            if not ok:
                path.unlink()
                sys.exit(f"Checksum mismatch: {entry['path']}")
    print(f"Verified {spec['repo']}@{spec['revision'][:12]} in {target}")
    return target


if __name__ == "__main__":
    main(sys.argv[1])
