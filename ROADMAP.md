# ROADMAP.md

# MVP Roadmap

## Current Summary and Follow-up Review (2026-10-18)

Current source and fixed desktop: **0.8.0 / 0006**; the historical name `PersonalAiMemoryOs-0.6.6` is retained. The original EXE now prepares opted-in local Ollama/Qdrant services; current local RAG is configured, while clean distributions default off. The separate Docker API's last recorded deployment remains **0.6.0 / 0004**, AI/RAG off. Sharing its Qdrant service does not upgrade or enable that API. See the [instance matrix](docs/project-audit-cn.md#current); this documentation review did not probe or deploy services.

Current follow-up queue is recorded in [项目审阅与后续补充清单](docs/project-audit-cn.md#priorities):

| ID | Priority / state | Next result required |
| --- | --- | --- |
| NEXT-01 | P1 / pending quality acceptance | Real generation and cited-answer review, fixed samples, separate explicit budgets |
| NEXT-02 | P1 / pending | Full isolated backup restoration, including vault/configuration and separate Qdrant route |
| NEXT-03 | P1 / pending | Physical Windows cold boot and entire local-stack relocation; do not repeat already-passed portable-only moves |
| NEXT-04 | P1 / pending | Track stable documentation/automatic-service acceptance tools outside `.cache`, publish a repeatable check matrix |
| NEXT-05 | P2 / pending | External log and historical artifact retention, preserving model weights and useful backups |
| NEXT-06 | P2 / pending | Fixed retrieval samples and synthetic capacity/latency/storage baselines |
| NEXT-07 | P2 / decision and maintenance | Build identity/version policy, dependency review and owner-selected project licensing before public release |

This review updates documentation only. Current features and evidence are summarized in [SPEC.md](SPEC.md); optional new features are not mandatory implementation commitments. TASK-004 and complete TASK-005 quality gates remain pending. Dated entries below preserve historical results; their old "current status", missing-key or Qdrant-off statements must not override this summary.

## Desktop One-Click Local RAG Preparation (2026-10-18)

Complete and delivered in the same portable directory, keeping `0.8.0 / 0006`. The existing EXE now prepares opted-in local Ollama/Docker Desktop/Qdrant through its bundled hidden helper before starting the backend; the user no longer needs a PowerShell command. Optional personal `config/local-rag-startup.json` selects the project location. Missing/disabled configuration, RAG-off or different endpoints do not start services. New distributions do not enable it or bundle model weights/Docker.

Full regression: 1,135 passed, 3 Windows symlink skips, one existing warning. Actual baseline EXE and dedicated automatic-startup/single-instance/proxy/restart acceptance passed with zero model calls. After verified backup, the existing installation was updated in place and configured for direct double-click startup; all business/configuration/vault data and the two published notes were retained. Service preparation does not pull weights, call DeepSeek, stop shared services or redeploy other APIs. Failures offer explicit basic-management fallback with RAG off for that launch and unchanged saved configuration. TASK-004/005 real-answer quality boundaries remain unchanged.

## Local RAG Connection: Ollama + BGE-M3 + Qdrant (2026-10-18)

Completed the user-approved local deployment without changing `0.8.0 / 0006`: verified official Ollama `0.40.6` Windows standalone archive under `.tools/ollama`, project-local BGE-M3 weights under `.cache/ollama/models`, and loopback Qdrant `1.19.2` with its Docker named volume. The fixed used desktop now has RAG enabled with `local_bge_m3`, native 1024 dimensions, batch 1 and timeout 180s; shipped defaults stay off. Startup remains explicit through `scripts/start_local_rag.ps1`, with no new Windows autostart or API-container rollout.

Real local Embedding, Chinese retrieval and edit/delete/restore/cache/restart acceptance passed in isolation. Both existing Knowledge records published successfully, two paraphrased queries returned the expected top note, and protected desktop restarts retained the same index. Business records, full vault, AI configuration and the 100,000-character input limit were preserved after a verified backup. Source-only content remains unindexed. Sixteen safety tests cover the acceptance tooling. System-proxy loopback failures were resolved through preserved user `NO_PROXY` exceptions.

TASK-005 now has real local Embedding and limited retrieval evidence. Full real cited-answer quality remains pending, as does TASK-004's bounded DeepSeek quality review; this work made zero text-generation requests and does not enlarge either call budget. Detailed evidence and model revision are in `IMPLEMENTATION_TASKS.md` and the Chinese RAG guide. Earlier RAG-off statements below describe historical deployments, not this desktop's current setting.

## v0.8.0: RAG Setup, Independent Prompts/Drafts and Consistent Pagination

Status: engineering complete and deployed in the fixed portable directory on 2026-10-17; application `0.8.0`, schema `0006`. Earlier release completion statements remain historical. Real Embedding/generation quality remains pending.

1. Add a visual RAG setup guide and independent Embedding profiles, Qdrant address, write-only credentials, active/next-start state, local preflight and explicit connection checks. Keep RAG off until the user chooses a service and enables it; configuration save is zero-call. A paid Embedding test requires its own confirmation and never starts indexing.
2. Move both knowledge-analysis and cited-answer templates to an independent Prompt center with search, 10/20/50/100 paging, revisions, copy/default/archive and immediate availability for new requests. Keep per-purpose defaults and frozen request revisions; retain the complete eight-stage analysis Prompt and enforce citation safeguards outside custom instructions.
3. Separate AI submission/progress from a draft library and draft detail. Drafts remain read-only until explicit adoption; existing source/version checks, v1/v2 compatibility and saved-note navigation stay intact. Show selected input lengths and the configured limit before generation.
4. Apply 10/20/50/100 pagination, page-number controls and direct jump across record collections, with independent return/filter state and lazy detail reads. Use summary polling and paged diagnostics rather than repeatedly returning full snapshots. Client-side report/result paging must never repeat imports or model calls. The per-generation selection cap remains 20.

Delivered in `dist/PersonalAiMemoryOs-0.6.6/` after clean staging, verified backup and stopped-instance upgrade. Full regression passed 1,088 checks/3 Windows skips; local/Docker browsers, final frozen pages/restart and real `0005 → 0006` EXE upgrade passed. Preserve all 571 Sources, 2 Knowledge, 3 runs, 1 batch, private configuration and full vault; RAG remains off. Backup `backups/upgrade-20261017-152603-89fb11df/`, installed audit `.cache/v08/installed-audit.json`. Public increments are committed locally. Phase 4/5 real model/retrieval quality remains pending and has no expanded call budget.

RAG HTTP integration: both local and Docker modes passed against real isolated Qdrant and offline models (`.cache/v08-rag/f61cb47e7d2044539184c58ed8509154/report.json`), including custom QA revision freezing, citations and note edit/delete/restore/restart. Owned containers/networks/volumes were removed and formal storage remained unchanged. Full browser/frozen/artifact results and the Windows long-path upgrade fix are recorded in `IMPLEMENTATION_TASKS.md`.

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

Current phase status: engineering implemented; formal real-generation quality review remains pending. The earlier v0.4 closing-step snapshot had no credentials and no live calls; it does not describe today's personal desktop configuration. No new call budget is granted by this status update.

Deliver: summary, classification and evidence-backed opinion extraction as previewable drafts; configurable model protocols; explicit one-time Knowledge adoption.

## Phase 5

RAG.

Current phase status: engineering and real local BGE-M3 interface/lifecycle/limited-retrieval checks passed; complete real cited-answer quality remains pending. The used desktop's RAG is enabled; the separate old Docker API remains disabled. Qdrant is running for the desktop. Phase 5 is not fully complete; earlier v0.5 empty/off-state deployment details below are historical.

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
