"""Validate tracked project manuals and examples without an existing .cache."""

import argparse
import ast
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.configuration import _ProfileDocument
from app.services.markdown import parse_document
from app.vector.configuration import EmbeddingProfile
from documentation_checks import blocks, check_links


def check(root: Path = ROOT) -> dict:
    report = {"status": "passed", "files": 0, "links": 0, "json_examples": 0,
              "yaml_examples": 0, "real_model_calls": 0, "personal_configuration_read": False}
    files = sorted([*root.glob("*.md"), *(root / "docs").glob("*.md")])
    for path in files:
        text = path.read_text(encoding="utf-8-sig")
        examples = blocks(text)
        report["files"] += 1
        report["links"] += check_links(root, path, text)
        # Historical prose may contain deliberately incomplete protocol fragments.
        if path.name not in {"readme-cn.md", "rag-guide-cn.md", "config-reference-cn.md"}:
            continue
        for language, content in examples:
            if language == "json":
                json.loads(content)
                report["json_examples"] += 1
            elif language == "yaml":
                value = yaml.safe_load(content)
                report["yaml_examples"] += 1
                if isinstance(value, dict) and "profiles" in value:
                    if all(p.get("protocol") != "openai_embeddings" for p in value["profiles"].values()):
                        _ProfileDocument.model_validate(value)
                    else:
                        if value["schema_version"] != 1 or value["default_profile"] not in value["profiles"]:
                            raise ValueError("Invalid Embedding example default")
                        for profile in value["profiles"].values():
                            EmbeddingProfile.model_validate(profile)
            elif language == "markdown" and "schema_version: 1" in content:
                parse_document(content)
    reference = (root / "docs/config-reference-cn.md").read_text(encoding="utf-8")
    for relative, class_name in [("app/config.py", "Settings"), ("app/agents/configuration.py", "AIProfile"),
                                 ("app/vector/configuration.py", "EmbeddingProfile")]:
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
        fields = [n.target.id for n in cls.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
        for field in fields:
            token = "MEMORY_OS_" + field.upper() if class_name == "Settings" else f"`{field}`"
            if token not in reference:
                raise ValueError(f"Undocumented {class_name} field: {field}")
        report[class_name + "_documented_fields"] = len(fields)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-build", action="store_true", help="Additionally compare the last local build fingerprint")
    args = parser.parse_args()
    try:
        report = check()
        if args.check_build:
            from build_desktop import source_fingerprint
            saved = json.loads((ROOT / ".cache/desktop-build-result.json").read_text(encoding="utf-8"))
            if saved["source_fingerprint"] != source_fingerprint():
                raise ValueError("Application/build resources changed since the last build")
            report["application_build_resources_unchanged"] = True
    except Exception as error:
        report = {"status": "failed", "error": str(error)}
    output = ROOT / ".cache/documentation-check/report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
