"""Explicit online OSV advisory lookup; sends PUBLIC package names/versions only."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tomllib
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]


def public_packages(root: Path = ROOT) -> list[dict]:
    document = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    packages = sorted({(p["name"], p["version"]) for p in document["package"] if "registry" in p.get("source", {})})
    queries = [{"package": {"name": name, "ecosystem": "PyPI"}, "version": version} for name, version in packages]
    vendor = json.loads((root / "app/web/vendor/manifest.json").read_text(encoding="utf-8"))
    queries += [{"package": {"name": name, "ecosystem": "npm"}, "version": vendor[name]} for name in ["marked", "dompurify"]]
    return queries


def findings_from_results(queries: list[dict], results: list[dict]) -> list[dict]:
    if not isinstance(results, list) or len(results) != len(queries):
        raise ValueError("Advisory response count differs from request")
    if any(not isinstance(row, dict) or row.get("next_page_token") or row.get("error") for row in results):
        # Do not label an incomplete/error page as a clean scan. A maintainer can
        # use OSV-Scanner for larger paginated inventories; never silently retry.
        raise ValueError("Incomplete or invalid advisory result")
    return [{**package, "advisories": row["vulns"]} for package, row in zip(queries, results) if row.get("vulns")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="Explicitly contact api.osv.dev; no automatic retries")
    parser.add_argument("--proxy", help="Optional local HTTP proxy without credentials")
    args = parser.parse_args()
    if args.proxy:
        proxy = urlsplit(args.proxy)
        if proxy.scheme != "http" or proxy.hostname not in {"localhost", "127.0.0.1", "::1"} or proxy.username or proxy.password:
            parser.error("Proxy must be local HTTP without credentials")
    queries = public_packages()
    report = {"captured_at": datetime.now(timezone.utc).isoformat(), "status": "inventory_only",
              "source": "https://api.osv.dev/v1/querybatch", "package_count": len(queries),
              "lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
              "scope": "All locked PyPI versions including optional/build groups and two vendored npm packages; excludes Docker/OS/DLL advisories",
              "private_configuration_read": False, "model_calls": 0, "packages": queries}
    if args.online:
        try:
            with httpx.Client(proxy=args.proxy, trust_env=args.proxy is None, timeout=45, follow_redirects=False) as client:
                response = client.post(report["source"], json={"queries": queries})
                response.raise_for_status()
                results = response.json()["results"]
                findings = findings_from_results(queries, results)
                report.update(status="advisories_found" if findings else "no_advisories_reported", findings=findings)
        except Exception as error:
            report.update(status="unavailable", error_type=type(error).__name__)
    output = ROOT / ".cache/dependency-audit/report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "packages": len(queries), "affected_packages": len(report.get("findings", [])), "report": str(output)}))
    return 1 if report["status"] in {"advisories_found", "unavailable"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
