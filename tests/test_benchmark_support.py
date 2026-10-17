import asyncio
import json
from types import SimpleNamespace

import pytest

from scripts.benchmark_support import IsolatedQdrant, SyntheticEmbedding, timings


def test_percentiles_are_deterministic_and_use_nearest_rank_p95():
    assert timings([.001, .002, .003, .004])["p95_ms"] == 4
    with pytest.raises(ValueError):
        timings([])


def test_synthetic_benchmark_is_reproducible_and_not_a_real_transport():
    service = SyntheticEmbedding()
    resolved = SimpleNamespace(profile=SimpleNamespace(dimension=1024))
    first = asyncio.run(service.embed(resolved, ["中文内容", "其他内容"]))
    second = asyncio.run(service.embed(resolved, ["中文内容"]))
    assert first.vectors[0] == second.vectors[0]
    assert first.vectors[0] != first.vectors[1]
    assert len(first.vectors[0]) == 1024 and any(first.vectors[0])
    assert service.calls == 2


def test_benchmark_cleanup_refuses_container_owned_by_someone_else(monkeypatch):
    resource = IsolatedQdrant()
    resource.container_created = resource.volume_created = True
    commands = []
    def command(*args):
        commands.append(args)
        if args[0] == "ps":
            return "identifier"
        if args[0] == "inspect":
            return json.dumps([{"Config": {"Labels": {"personal-ai-memory-os.benchmark": "other"}}}])
        pytest.fail("Foreign resource was mutated")
    monkeypatch.setattr(resource, "command", command)
    with pytest.raises(ValueError, match="ownership"):
        resource.stop()
    assert not any(args[0] in {"rm", "stop"} for args in commands)


def test_failed_run_without_container_can_remove_only_its_labeled_volume(monkeypatch):
    resource = IsolatedQdrant()
    resource.container_created = resource.volume_created = True
    commands = []
    def command(*args):
        commands.append(args)
        if args[0] == "ps":
            return ""
        if args[:2] == ("volume", "inspect"):
            return json.dumps([{"Labels": {"personal-ai-memory-os.benchmark": resource.name}}])
        if args == ("volume", "rm", resource.volume):
            return "removed"
        pytest.fail("Unexpected cleanup command")
    monkeypatch.setattr(resource, "command", command)
    resource.stop()
    assert commands[-1] == ("volume", "rm", resource.volume)
