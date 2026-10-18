"""Explicit pinned-model provisioning. Ordinary desktop startup never downloads."""

import argparse
import hashlib
import json
from pathlib import Path
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
MODEL = "BAAI/bge-reranker-v2-m3"
REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
FILES = ("config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
         "sentencepiece.bpe.model", "model.safetensors", "README.md")


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def prepare(proxy=None):
    cache = ROOT / ".cache/reranker"
    directory = cache / "models/bge-reranker-v2-m3"
    manifest = cache / "model-manifest.json"
    directory.mkdir(parents=True, exist_ok=True)
    if manifest.exists():
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        if saved["revision"] != REVISION:
            raise RuntimeError("Existing model revision differs; preserve it before provisioning a replacement.")
        if all((directory / name).is_file() and sha256(directory / name) == digest for name,digest in saved["files"].items()) and set(saved["files"]) == set(FILES):
            print("Pinned reranker model is already verified; no download.")
            return saved
    hashes = {}
    with httpx.Client(proxy=proxy, timeout=httpx.Timeout(600, connect=30), follow_redirects=True) as client:
        for name in FILES:
            target = directory / name
            # Cached files without a manifest are checked against immutable HF
            # metadata, not trusted merely because their pathname exists.
            url = f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}"
            head = client.head(url, follow_redirects=False)
            head.raise_for_status() if head.status_code >= 400 else None
            linked = head.headers.get("x-linked-etag", head.headers.get("etag", "")).strip('"')
            expected = linked if len(linked) == 64 else None
            if target.is_file() and expected and sha256(target) == expected:
                hashes[name] = expected
                print(name + " verified", flush=True)
                continue
            temporary = target.with_suffix(target.suffix + ".partial")
            with client.stream("GET", url, params={"download": "true", "validation": str(time.time_ns())}) as response:
                response.raise_for_status()
                with temporary.open("wb") as stream:
                    for block in response.iter_bytes(1024 * 1024):
                        stream.write(block)
            digest = sha256(temporary)
            if expected and digest != expected:
                raise RuntimeError("Downloaded file hash differs from pinned metadata: " + name)
            temporary.replace(target)
            hashes[name] = digest
            print(f"{name}: {target.stat().st_size} bytes verified", flush=True)
    saved = {"model": MODEL, "revision": REVISION, "files": hashes}
    manifest.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy", help="Optional download proxy; never used for local inference")
    args = parser.parse_args()
    prepare(args.proxy)
