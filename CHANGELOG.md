# Changelog

## 0.11.0 — 2026-11-14

- Support OpenAI Responses JSON and inline image inputs, with bounded input-token counting.
- Add explicit collection-provider switching that retains approved style and published articles while binding the selected model fingerprint.
- Freeze conservative provider prices per job/request; schema 0008 preserves historical accounting unchanged.
- Keep portable installation and credentials local; user defaults are configured independently from disabled public examples.

## 0.8.0 maintenance — 2026-10-18

- Add public documentation, release and unified non-paid checks plus a read-only GitHub Actions workflow.
- Make actual EXE local-service startup/restart verification reproducible outside ignored caches.
- Add isolated full backup restoration, configuration/vault hash checks and SQLite-cached-vector recovery acceptance.
- Add read-only Windows boot evidence, fixed Chinese retrieval/QA review inputs, protected disk inventory and explicit stopped-log rotation.
- Add separate real local retrieval evaluation and synthetic SQLite/Qdrant capacity benchmarks.
- Add an explicit online OSV package-advisory audit without a new runtime dependency.

These changes add maintainer tools and documentation. Application resources, portable executable, business schema (`0006`), personal settings and formal deployment remain unchanged. A future application change must receive an appropriate new version and its own clean build and EXE acceptance. Real generation/cited-answer review, actual Windows cold boot, complete stack relocation and project-license selection remain separate gates.
