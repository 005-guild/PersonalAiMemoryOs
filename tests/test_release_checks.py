import json
from pathlib import Path
import shutil

import pytest

from scripts.audit_dependencies import findings_from_results, public_packages
from scripts.check_release import ROOT, check


def test_advisory_batches_cannot_silently_drop_pagination_or_errors():
    query = {"package": {"name": "httpx", "ecosystem": "PyPI"}, "version": "test"}
    assert findings_from_results([query], [{}]) == []
    assert findings_from_results([query], [{"vulns": [{"id": "example"}]}])[0]["package"]["name"] == "httpx"
    for results in [[], [{"next_page_token": "not-complete"}], [{"error": "invalid"}]]:
        with pytest.raises(ValueError):
            findings_from_results([query], results)


def test_public_dependency_inventory_excludes_the_local_project():
    queries = public_packages()
    assert all(row["package"]["name"] != "personal-ai-memory-os" for row in queries)
    assert any(row["package"] == {"name": "dompurify", "ecosystem": "npm"} for row in queries)


def test_release_check_rejects_version_drift_and_changed_vendor_resources(tmp_path):
    for name in ["pyproject.toml", "uv.lock", "app/main.py", "app/web/vendor/manifest.json"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, path)
    manifest = json.loads((ROOT / "app/web/vendor/manifest.json").read_text("utf-8"))
    for name in manifest["files"]:
        shutil.copy2(ROOT / "app/web/vendor" / name, tmp_path / "app/web/vendor" / name)
    actual = check(tmp_path)
    assert actual["status"] == "passed"
    target = tmp_path / "app/main.py"
    original = target.read_text("utf-8")
    target.write_text(original.replace(f'version="{actual["application_version"]}"', 'version="0.0.0"'), encoding="utf-8")
    with pytest.raises(ValueError, match="versions differ"):
        check(tmp_path)
    target.write_text(original, encoding="utf-8")
    (tmp_path / "app/web/vendor/marked.js").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        check(tmp_path)
