# ROADMAP.md

# MVP Roadmap

## v0.7.0: Multi-Source Analysis, Prompt Templates and In-Place Desktop Updates

Status: engineering complete and deployed in the fixed existing portable directory on 2026-10-17. Version `0.7.0`, database `0005`; real-provider quality remains a separate pending gate.

Deliver the six confirmed improvements:

1. Paged/searchable Source selection with body preview, current-page checkboxes and cross-page selection; explicit individual or merged analysis of at most 20 inputs.
2. Align the generation button and status selection in the AI workspace.
3. Return to the overview after a successful Knowledge save.
4. After AI settings save, offer explicit immediate desktop restart or later restart, protecting unsaved input and draining in-flight work.
5. Maintain the same existing portable directory through verified resource/schema upgrades, rather than making a new versioned user directory for every change; keep local Git history of public code/document changes.
6. Manage/select multiple versioned Prompt templates; preserve the user's full eight-stage Zhihu analysis Prompt as the default and keep legacy output/run compatibility.

Generation v2 stores the complete Markdown analysis plus metadata and exact source quotations. Persistent batches retain source/template/model/generation snapshots, per-item results and idempotency; restart pauses incomplete work and paid retries remain explicit. Merged Knowledge retains ordered multi-source provenance, with the first-source compatibility field, all-source restore/delete safeguards, Markdown v1/v2 compatibility and complete RAG citation metadata. Ordinary Python/Docker startup still requires explicit migration. Real web verification is not implemented by changing a Prompt.

Final validation passed 1,030 tests/3 Windows skips/1 existing warning, a 47-package lock and 34 ESM checks; controlled and real local browser workflows, final actual EXE batches/templates/restart, blocked-call restart draining and real old-to-new same-directory migration all passed. The fixed `dist/PersonalAiMemoryOs-0.6.6/` was backed up, upgraded and reopened with all existing 571 Sources/1 Knowledge/2 runs and configuration retained. Detailed evidence and SHA-256 values are recorded in `IMPLEMENTATION_TASKS.md`. Historical Phase 4/5 live-quality acceptance remains separate; no new feature authorizes unattended model calls or consumes the earlier dedicated real-validation budget.

## v0.6.6: Visual AI Configuration and Storage Locations

Approved scope: a prominent upper-left Settings entry, mobile top-bar link and native desktop menu; editable text-generation AI switch, default profile, multiple four-protocol profiles, write-only key updates and preserved advanced parameters. Display actual data/Knowledge/configuration locations read-only. Save next-start configuration without a model call, hot reload, automatic restart or RAG enablement. Respect environment-managed values and Docker read-only configuration. No business-path editing, Embedding/RAG editor or schema migration. Declare the already-transitive `python-dotenv` directly; the 47-package lock adds no installed package, model SDK or framework.

Engineering status: complete. Verification passed 925 tests/3 Windows skips/1 existing warning, 30 ESM modules, six controlled browser groups and real isolated local save/restart checks. The audited separate 0.6.6 portable directory/ZIP is delivered. Actual frozen settings save/restart, grouped reading, all eight sorting orders and complete 17-flow desktop regression passed, with no real model calls and unchanged formal hashes. Existing installations/data and formal Docker 0.6.0 are preserved. Phase 4/5 real-provider quality, production native Save As interaction and second-clean-PC review remain separate.

Final resource cleanup passed (`.cache/desktop-066-cleanup.json`), with no owned process and all four validation ports closed. Detailed frozen workflow/audit paths and checksums are recorded in `IMPLEMENTATION_TASKS.md` and both READMEs.

## v0.6.5: Source Library Sorting

Complete: whole-result ascending/descending sorting by title, source count, source type and latest update, with dropdowns and accessible column headings. Preserve filters, pagination and editor return state. Default order stays latest update descending; mixed-type groups use their first visible type in database character order. Verification passed 856 tests/3 Windows skips/1 existing warning, 26 ESM modules, controlled eight-order/browser regression, actual frozen sorting/grouped reading and sequential complete desktop regression. Cached571 corpus matched all eight orders/432 groups/176 pages with unchanged data hashes. A separate complete0.6.5 portable directory/ZIP/checksum is delivered; used installations and formal Docker are not overwritten. No migration/dependency, schema0004; real-provider and previous manual review gates remain separate.

## v0.6.4: Paginated Source Title Groups

Complete: numbered pages, 20/50/100 title page sizes and direct page jump in the Source library. Group exact matching titles globally before pagination; open a group to read independently authored answers with separate edit/draft/note actions and 5/10/20-member pagination. Preserve records and version checks, list/group return position, read-only flat API compatibility and schema0004. Verification passed 809 tests/3 Windows skips/1 existing warning, 25 ESM modules, five controlled browser groups, actual local/frozen 46-group/48-Source workflows and full frozen regression. Real corpus isolation matched 571 Sources/432 title groups with 22 pages and all body hashes unchanged. The complete 0.6.4 portable directory/ZIP/checksum is separate; existing user runtime, formal Docker and real-provider acceptance gates remain untouched.

## v0.6.3: Offline Zhihu Markdown Folder Import

Complete: reusable folder/multiple-file selection, preview/commit into Sources, 1,000-file/10 MiB Markdown endpoint, answers/articles/pins, conservative deduplication and file-level reports. 780 tests and actual local/frozen ingestion passed all 571 files with exact bodies, zero repeat additions and restart persistence. No automatic Knowledge/AI/RAG, image transfer, migration or dependency. The pristine complete 0.6.3 release is delivered separately; old installations and private/formal data remain unchanged. Formal imports require user preview/commit in the target workbench. Previous real-service/Save As/clean-PC review boundaries remain unchanged.

## v0.6.2: Knowledge List Usability

Complete: list-level Knowledge selection and confirmed bulk soft deletion with optimistic versions, partial-result reporting and no automatic retries. Search/answer retrieval controls align and wrap responsively. Schema remains `0004`. All 710 tests and actual frozen-EXE workflows passed, including a separate true WebView2/SQLite bulk-delete/layout check. The used desktop received only backed-up web assets with runtime storage hashes unchanged; independent 0.6.2 folder/ZIP/checksums were delivered. Formal Docker, real-provider and native Save As review boundaries remain unchanged.

## v0.6.1: Portable Windows Desktop

Approved: an unsigned Windows x64 onedir EXE with a native WebView2 window, embedded Python/API, independent portable data/configuration, dynamic loopback port, single-instance activation, graceful dirty-aware close, verified schema-upgrade backups and reproducible ZIP/checksums. No installer, updater, new schema, bundled Qdrant or model is added. AI/RAG default off. The existing formal v0.6 Docker deployment is not changed.

Status: complete; the final portable Windows x64 directory, ZIP/checksums and actual frozen-EXE engineering acceptance passed on 2026-10-17. Full regression: 696 passed, three Windows symlink privilege skips and one existing warning; final targeted/runtime checks and existing source/Docker process regressions passed. Actual embedded WebView2 155 passed CRUD/import/export/Markdown, duplicate launch, dirty-aware close, in-flight mock drain, restart/relocation and native configuration-error checks. Report `.cache/desktop-validation/08a46b518be848cfb14bc89742a6e1bd/report.json` identifies the final EXE, records no page errors/real calls and unchanged formal hashes. The existing formal Docker service remains 0.6.0 with AI/RAG off. No second clean Windows PC was tested; TASK-004/005 real-provider quality gates remain pending.

## Phase 6: Local Visual Management

Approved v0.6 scope: a Chinese, light-theme, same-service HTML/CSS/modular-JavaScript workspace for overview, Sources, offline JSON import, Markdown Knowledge editing/preview, AI draft adoption, semantic search/cited answers and sync/index/configuration status. No Node build pipeline, accounts, new migration or business-model expansion. Version `0.6.0`; schema remains `0004`.

Status: complete; engineering acceptance and formal v0.6 deployment passed on 2026-10-17. Verification: 655 tests, two Windows symbolic-link skips and one existing warning (25.94 seconds); existing local/Docker regression, both isolated Chromium/Qdrant/offline-model workflows and restarts, 1440/1024/390 layout checks and safeguard reviews all passed. Evidence: `.cache/v06-validation/f685f6759bea49f99519b873d2dbbdbb/report.json`, with unchanged formal hashes, clean owned-resource removal and zero real calls. Formal deployment followed verified full backup `data/backups/v0.5-before-v0.6-20261017-bfed7a26`; schema stays `0004`, the non-root loopback service is healthy, all seven business/index tables remain empty and vault hashes are unchanged (`.cache/v06-deployment-result.json`). Formal AI/RAG remain off, Qdrant stays stopped, no demonstration data entered formal storage, and Phase 4/5 real quality acceptance remains pending.

All seven formal pages also passed read-only Chromium checks without writes or script errors; desktop/mobile evidence is in `.cache/v06-formal-browser/report.json`. Production image excludes Playwright/`.env`, and owned validation resources are fully cleaned.

## Phase 1

Project foundation.

Current status: complete; local and Docker acceptance passed.

Complete: - FastAPI - database - configuration

## Phase 2

Knowledge storage.

Current status: complete; CRUD and bidirectional Markdown passed local/Docker acceptance.

Complete: - Source model - Knowledge model - Markdown generation

## Phase 3

Zhihu Import.

Current status: complete; v0.3 local and Docker acceptance passed.

Complete: - parser - importer - validation

## Phase 4

AI Processing.

Current status: v0.4 engineering acceptance and bounded DeepSeek real-acceptance preparation passed; credentials are missing and zero live requests have been made. Formal AI is off. Not complete.

Deliver: summary, classification and evidence-backed opinion extraction as previewable drafts; configurable model protocols; explicit one-time Knowledge adoption.

## Phase 5

RAG.

Current status: v0.5 engineering acceptance and formal deployment passed. Real Embedding/retrieval/answer quality acceptance remains pending; Phase 5 is not fully complete. Formal AI and RAG remain off, and formal Qdrant has not been started.

Deliver: Knowledge-only incremental Embedding, SQLite vector caching, owned Qdrant collections, semantic search, checked citations and single-turn knowledge-only answers. Do not mark Phase 5 complete until engineering and real quality gates both pass.

Verified on 2026-10-17: 609 tests passed, two Windows symbolic-link privilege skips and one existing warning (21.76 seconds). Both real-Qdrant 1.19.2/offline-model local and Docker workflows/restarts passed; old local/Docker regression also passed. Owned containers/networks/named volumes were cleaned, and isolated acceptance preserved formal hashes. Evidence: `.cache/v05-validation/0e022cb9aae0471c8ac2b0efe3c98f32/report.json`; detailed logs are in `IMPLEMENTATION_TASKS.md`.

Formal upgrade used the fully verified stopped-service backup `data/backups/v0.4-before-v0.5-20261017-cf037130`, explicit `0003 → 0004` migration and healthy non-root Compose startup on 18000. Version is 0.5.0, SQLite integrity is `ok`, all four business/import/run and three RAG tables are empty, and vault hashes are unchanged. No real model calls were made; TASK-004 and TASK-005 retain their respective real-provider quality gates. Deployment evidence: `.cache/v05-deployment-result.json`.

## Historical v0.1 Status (2026-10-15)

- Phase 1: the foundation is implemented and local acceptance passed: 31 tests, live health/docs/OpenAPI requests, and graceful shutdown. The agreed deliverables include local and Docker launch paths, isolated configuration and SQLite lifecycle, health checks, tests, and shared project data. Docker build, health, recreation persistence and shared-file verification remain pending because Docker is not available in the current environment; Phase 1 is not complete until both launch paths pass acceptance. Detailed results are recorded in `IMPLEMENTATION_TASKS.md`.
- Phase 2: retain Source/Knowledge storage and Markdown generation. Before implementation, define model constraints, migrations, and database/Markdown ownership and synchronization. TASK-002 must include Markdown generation acceptance as well as CRUD.
- Phases 3-5 remain unimplemented. Zhihu acquisition/sample input, structured AI output quality, and vector-index synchronization require decisions and validation in their respective phases.

## v0.2 Status (2026-10-16)

- Phase 1 / TASK-001 and Phase 2 / TASK-002 are complete with both local and Docker acceptance. The implementation includes Source/Knowledge CRUD, nullable one-to-many source links, explicit migrations, version checks, soft deletion/restoration, and automatic bidirectional Markdown synchronization.
- Markdown support includes external creation/edit/move/deletion, UUID backfill, stable-file polling, deletion grace, preserved conflicts with explicit resolution, vault identity and restart recovery. Local/Docker storage now includes both `data/` and `knowledge/`; host port is 18000.
- v0.2 real-process acceptance passed, and the automated suite finished with 164 passed, 2 Windows symlink privilege skips and 1 upstream deprecation warning. The formal v0.1 database was backed up and explicitly migrated to revision `0001`. Full results are recorded in `IMPLEMENTATION_TASKS.md`; the 31-test result above belongs only to v0.1. Docker acceptance now also passed image build, explicit migration, health, automatic bidirectional sync, recreation persistence, host SQLite reads and complete temporary-resource cleanup.
- Phases 3-5 remain outside this release: no Zhihu collector, AI generation or vector index is introduced.

The formal local v0.2 service started successfully at `127.0.0.1:18000` after migration. Health/docs/OpenAPI checks passed, synchronization was running without reported errors, and formal Source/Knowledge storage remained empty.

The formal service now runs with Compose on `127.0.0.1:18000` as a healthy non-root container. The database and complete vault were backed up with a hash manifest before the switch; migration and live HTTP/sync checks passed, with zero formal Source/Knowledge records at verification. The verifier uses existing Windows proxy settings only within its process and restores the prior environment.

## v0.3 Accepted (2026-10-17)

- Zhihu JSON preview/import is implemented through a shared parser/service, HTTP API and stdlib CLI. Migration `0002` adds durable Source identities; reports distinguish invalid input, new Sources, repeats and field differences, while preserving soft-deleted Sources and conservative legacy matches.
- Preserve the boundary between raw Sources and processed Knowledge: importing must not create or modify Knowledge or Markdown.
- Phase 3 / TASK-003 is complete. The full v0.3 suite passed 270 tests, with two Windows symlink privilege skips and one upstream deprecation warning. Both real-process local and Docker verifiers exited 0.
- Docker acceptance passed migration `0002`, host HTTP JSON preview/mixed import, repeat/change/deleted-source handling, post-recreation deduplication, unchanged Knowledge/vault assertions, host reads and cleanup, retaining the earlier bidirectional-sync checks. Logs are `.cache/v03-local-verification.log` and `.cache/v03-docker-verification.log`.
- Formal deployment passed on 2026-10-17 (Asia/Shanghai), with full backup `data/backups/v0.2-before-v0.3-20261017-3815b32d`, explicit migration `0001`→`0002`, healthy non-root Compose service on port 18000, and 0.3.0 health/docs/OpenAPI/import-route and sync checks. The sample CLI ran only as a no-write preview; no sample content was imported into formal storage.
- Final formal verification confirmed revision `0002`, SQLite integrity `ok`, zero Source/Knowledge/origin rows, unchanged vault hashes, a fully verified backup manifest and error-free logs.

## v0.4 AI Processing Decisions (2026-10-17)

- Four configurable text-generation protocols: Chat Completions, Responses, Claude Messages and Gemini GenerateContent. DeepSeek and common compatible services have configuration templates; templates do not imply all vendors have passed live testing.
- Single-Source manual generation, immutable draft/Source provenance and explicit one-time adoption. Preview does not create Knowledge/Markdown. Adopted notes use the existing Markdown protocol and remain editable.
- Add explicit revision `0003` and promote HTTPX to a runtime dependency. Default AI remains off. Personal profile YAML is ignored, named secret references come from environment/.env, and Docker mounts config read-only.
- Engineering acceptance passed: 422 tests, two Windows symlink privilege skips and one upstream warning; both isolated local/Docker real-process scripts exited 0. Four protocols and full draft/adoption/export/edit/restart checks passed, retaining previous import/sync acceptance. At least one actual model service must also pass compatibility/quality acceptance before Phase 4 / TASK-004 can be marked complete. Real configuration will be supplied later; mock success is not live-provider coverage.
- Formal deployment passed after the verified full backup `data/backups/v0.3-before-v0.4-20261017-c80de831`, explicit migration `0002 → 0003` and healthy non-root Compose startup on loopback port 18000. AI remains disabled; OpenAPI is 0.4.0, all four business/import/run table counts are zero, SQLite integrity is `ok`, and vault hashes are unchanged. Detailed results are in `IMPLEMENTATION_TASKS.md`.

## v0.4 Real-Provider Closing Step (2026-10-17)

- Preflight still has no DeepSeek key; real call count is zero and the healthy formal service keeps AI disabled. No version bump, schema migration or formal test data is needed for this closing step.
- Prepared a bounded isolated acceptance runner and three original Chinese texts, using one local and two Docker generations, at most three requests with 2,048 output tokens and 90 seconds each. Keep database/vault/evidence beneath `.cache/real-provider-validation/`; never use formal storage for examples. A cross-process lock and prior-attempt check reject parallel or repeated live execution without review.
- After credentials are supplied locally through `.env`, verify real compatibility plus faithful summaries, useful categories, evidence and source-viewpoint/AI-analysis separation. Preserve generated outputs for human review; embedded source instructions must not redirect generation.
- Enable formal AI and mark Phase 4 / TASK-004 complete only after all three cases and quality review pass. Missing credentials or a failed real check leave both statuses unchanged. Existing mock engineering results remain distinct from live-provider acceptance.
- Preparation verification passed 459 tests, with two Windows symbolic-link skips and one existing upstream warning. Non-calling preflight returned 2 (`ai_api_key_missing`); AI-disabled local-to-Docker shared-storage/recreation smoke passed with no model calls, empty schema-`0003` business tables, clean runtime shutdown and unchanged formal hashes. The healthy formal service remains AI-disabled, DeepSeek unconfigured and sync running. Detailed evidence is in `IMPLEMENTATION_TASKS.md`; this is not real-provider acceptance.
