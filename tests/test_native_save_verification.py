"""Maintenance fixture preparation must stay outside formal installation data."""

import json

import pytest

from scripts import verify_native_save as verifier


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier, 'ROOT', tmp_path)
    monkeypatch.setattr(verifier, 'CACHE', tmp_path / '.cache/native-save-as')
    return tmp_path


@pytest.mark.parametrize('location', ['cache_root', 'parent', 'installation'])
def test_evidence_directory_rejects_roots_and_escapes(workspace, location):
    paths = {'cache_root': verifier.CACHE, 'parent': verifier.CACHE / '..',
             'installation': workspace / 'dist/PersonalAiMemoryOs-0.6.6'}
    with pytest.raises(ValueError, match='Evidence must be a child'):
        verifier.evidence_directory(paths[location])


def test_tampered_context_cannot_target_the_fixed_installation(workspace):
    evidence = verifier.CACHE / 'fixture'
    evidence.mkdir(parents=True)
    (evidence / 'context.json').write_text(json.dumps({
        'runtime': str(workspace / 'dist/PersonalAiMemoryOs-0.6.6')}), encoding='utf-8')
    with pytest.raises(ValueError, match='Unexpected isolated runtime'):
        verifier.load_context(evidence)


def test_preparation_rejects_formal_bundle_before_inspecting_or_copying(workspace, monkeypatch):
    inspected = []
    monkeypatch.setattr(verifier, 'inspect_bundle', lambda path: inspected.append(path))
    with pytest.raises(ValueError, match='pristine bundle under the project .cache'):
        verifier.prepare(workspace / 'dist/PersonalAiMemoryOs-0.6.6')
    assert inspected == []
    assert not verifier.CACHE.exists()
