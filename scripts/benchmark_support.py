"""Synthetic throughput helpers and strictly owned Qdrant resources."""

import hashlib
import math
from pathlib import Path
import statistics
import subprocess
from uuid import uuid4

import httpx

from app.vector.embedding import EmbeddingReply
from scripts.local_rag_support import get_json
from scripts.verification_support import eventually


def timings(values: list[float]) -> dict:
    if not values:
        raise ValueError("Timings cannot be empty")
    ordered = sorted(values)
    return {"samples": len(values), "p50_ms": round(statistics.median(ordered) * 1000, 3),
            "p95_ms": round(ordered[math.ceil(len(ordered) * .95) - 1] * 1000, 3),
            "max_ms": round(ordered[-1] * 1000, 3)}


class SyntheticEmbedding:
    """Transport-free deterministic 1024D vectors; NEVER claims model performance."""
    def __init__(self):
        self.calls = 0

    async def embed(self, resolved, texts):
        self.calls += 1
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vector = [(digest[i % 32] - 127.5) / 127.5 for i in range(resolved.profile.dimension)]
            vectors.append(vector)
        return EmbeddingReply(vectors, {})

    async def aclose(self):
        pass


class IsolatedQdrant:
    def __init__(self):
        self.name = "memory-os-benchmark-" + uuid4().hex[:12]
        self.volume = self.name + "-storage"
        self.owner = "personal-ai-memory-os.benchmark=" + self.name
        self.container_created = self.volume_created = False

    def command(self, *arguments):
        value = subprocess.run(["docker", *arguments], capture_output=True, text=True, encoding="utf-8",
                               timeout=90, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return value.stdout.strip()

    def start(self):
        self.command("image", "inspect", "qdrant/qdrant:v1.19.2")
        self.command("volume", "create", "--label", self.owner, self.volume)
        self.volume_created = True
        # A failed docker run may still leave a created container. Track the
        # attempt before invocation, then discover the exact name at cleanup.
        self.container_created = True
        self.command("run", "-d", "--pull=never", "--name", self.name, "--label", self.owner,
                     "-p", "127.0.0.1::6333", "--mount", f"type=volume,source={self.volume},target=/qdrant/storage",
                     "qdrant/qdrant:v1.19.2")
        self.url = "http://" + self.command("port", self.name, "6333/tcp").splitlines()[0]
        def ready():
            try:
                return get_json(self.url, "/collections")
            except httpx.HTTPError:
                return None
        eventually(ready, timeout=45)
        return self.url

    def storage_bytes(self):
        return int(self.command("exec", self.name, "du", "-sb", "/qdrant/storage").split()[0])

    def stop(self):
        import json
        if self.container_created:
            found = self.command("ps", "-aq", "--filter", f"name=^/{self.name}$")
            if found:
                metadata = json.loads(self.command("inspect", self.name))[0]
                if metadata["Config"]["Labels"].get("personal-ai-memory-os.benchmark") != self.name:
                    raise ValueError("Container ownership mismatch")
                self.command("stop", "--time", "10", self.name)
                self.command("rm", self.name)
        if self.volume_created:
            metadata = json.loads(self.command("volume", "inspect", self.volume))[0]
            if metadata["Labels"].get("personal-ai-memory-os.benchmark") != self.name:
                raise ValueError("Volume ownership mismatch")
            self.command("volume", "rm", self.volume)
