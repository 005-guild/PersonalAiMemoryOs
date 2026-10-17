# IMPLEMENTATION_TASKS.md

## v0.6.6 Visual AI Settings and Read-Only Storage Locations

Status: complete; implementation, source/local checks, four actual frozen-EXE workflows and audited portable delivery passed. Version `0.6.6`, schema `0004`, no migration. The environment editor directly uses existing `python-dotenv`, now declared as a direct runtime dependency; the 47-package lock adds no installed package, model SDK or framework. User scope is AI interface settings plus displayed data/configuration directories; do not expand into path editing or Embedding/RAG settings.

- Add upper-left/mobile/native Settings entries using the existing hash route and unsaved-input guard.
- Edit global AI/default selection and complete profiles, retaining authentication, protocol-specific fields and advanced JSON. Built-in templates perform no network request.
- Persist `.env`/YAML with revision checks and recoverable contained file operations. Keep current registries unchanged until complete exit/restart; no automatic model call, restart or RAG enablement.
- Require loopback same-origin/token access, bounded strict input, safe errors and no-store responses. Keys are write-only, empty inputs preserve existing values, shared references deduplicate, environment ownership is respected and Docker is read-only. Password fields and pending request-key references are cleared on successful save/disposal; no browser storage or response echo.
- Show actual runtime/data/database/Knowledge/configuration locations without exposing a connection string or allowing path changes. Preserve current formal Docker 0.6.0 and all used portable installations.

Executed: final full suite **925 passed, 3 Windows symlink skips, 1 existing Starlette/HTTPX warning**, 52.81s (`.cache/v066/pytest-final.log`); 30 ESM modules and `uv lock --check` over 47 packages passed. Six intercepted-API Chromium cases validate four-protocol complete round trips/advanced parameters, shared-key conflicts, blank-key preservation, explicit password replacement/clearing, no URL/storage/text leakage, no automatic calls/retries, 409 reload confirmation, validation/service errors, read-only controls, dirty leave/cancel, late GET and save responses during navigation confirmation. Report `.cache/settings-ui/3e237a1470ec44ddabadbcfef1abf23c/report.json` includes 1440/390 evidence and zero page errors/external requests. Existing eight-order UI regression also passed (`.cache/source-sort-ui/cf93ae1bda02491caabe8adf5858d75b/report.json`).

Real isolated API/Chromium save/restart acceptance passed (`.cache/settings-local-real/971c3d69449c4822aec2c418f4cf61d0/report.json`): configuration saved once, no hot apply, restarted profile/key readiness, empty password fields and zero trapped endpoint/model requests. This verifies persistence/configuration readiness, not service connectivity or generated output quality.

Delivered separate `dist/PersonalAiMemoryOs-0.6.6/`, ZIP 21,989,284 bytes; EXE SHA-256 `0899b2b7355f9be23946e30d1258b50839616b448623798daaa93f9ce1ce1b0b`, ZIP `d05d5c512b5b07dff3cc20adfc2dc24f4184ae491dc096ff8a9ba4dd9870ab8e`. `.cache/v066/final-audit.json` verifies source fingerprint, 36 web resources, 235 packaged files, x64 GUI/CRC/privacy, unchanged 15 previous artifacts and formal storage. Keep TASK-004/005 real quality, production Save As interaction and second-PC review pending.

Actual frozen settings acceptance passed (`.cache/ai-settings-validation/cc980ee5477944138fdbc946a39a2d5d/report.json`): saved once, no hot apply, actual exit/restart profile/key readiness, no password DOM/storage echo, retained original profiles and Source/Knowledge row hashes, key only in isolated `.env`, successful journal credential-copy cleanup, zero trapped endpoint requests and unchanged formal hashes. Grouped reading also passed (`.cache/source-groups-validation/c58681190c554d5bb5adec40be7aee09/report.json`, 46 groups/48 independent Sources, full text, paging, editor return and restart). Frozen sorting passed 27 groups/67 Sources in all eight orders, headings, filtered type order, return context and restart with unchanged Source snapshots (`.cache/source-sorting-validation/1079db283786450d9851dfd4a9b9523c/report.json`). Complete desktop regression passed 17 flows, in-flight fake-call drain/draft persistence without a Knowledge, native invalid-configuration feedback without outside file creation, restart/relocation and unchanged formal hashes (`.cache/desktop-validation/2042177c88c04b149202973303f02499/report.json`). Actual WebView2 testing remains local to this computer; no real-provider quality gate or production native Save As claim is changed.

Final cleanup `.cache/desktop-066-cleanup.json` passed: zero owned processes, four closed validation ports, pristine 235-file/43,552,764-byte unpacked release, unchanged 15 prior artifacts and formal storage. No user process was closed or automatically started, and no formal deployment was performed.

## v0.6.5 Source Library Sorting

Status: complete; version0.6.5/schema0004, no migration or new dependency. Source/backend/browser/frozen verification and pristine portable delivery passed.

- Extend the read-only group endpoint with four whitelisted sort keys and two directions; sort before pagination and retain stable title ties, state-aware aggregates and unchanged response contracts.
- Add visible dropdowns and sortable headings; retain selected order across paging, filtering, refresh and group/editor returns, resetting to page1 on sort changes.
- Verify all eight orders against independent expectations across page boundaries, empty/invalid/filter/state cases, zero writes, keyboard/mobile behavior, actual EXE persistence and existing regression.
- Package separately without overwriting running installations, then record actual validation and upgrade instructions.

Executed: 856 tests passed/3 Windows symlink skips/1 existing warning (55.80s), including47 sort tests; 26 ESM modules passed. Controlled sorting over45 groups verifies all8 complete orders, paging, defaults, aria-sort/keyboard, hash/return state, focus/debounce and stale-response guards (`.cache/source-sort-ui/84cc445457824fdeb9ab7d9181b811ac/report.json`); previous group guards also passed (`.cache/source-groups-ui/afe29bca0f034a57aa501e264d9e1820/report.json`). Actual frozen sorting (`.cache/source-sorting-validation/4711e8bc33764bdeaa9626dd19a33d50/report.json`) passed27 groups/67 Sources, 8 API/dropdown orders, 4 headings in both directions, filtered MIN type, returns/restart and unchanged seeded Source snapshot. Existing group workflow passed (`.cache/source-groups-validation/e99a0e13f9164815a627344e472a42a6/report.json`). Cache-only real corpus verification matched571 Sources/432 groups, eight22-page orders/176 pages, zero SQL writes and unchanged all-table/file hashes (`.cache/source-sort-corpus/6d5e615811744ad4b312bc678762d6da/report.json`).

Full desktop sequential regression passed17 flows plus in-flight fake-call drain and native configuration checks (`.cache/desktop-validation/6a4b97d0b5ed460b94187fa9f5decd13/report.json`). Retain the first parallel full attempt4495fafa... as failed/incomplete after an early normal window shutdown; cause unestablished, no app fix or causal claim. Deliver `dist/PersonalAiMemoryOs-0.6.5/`, ZIP21,949,576 bytes and checksum. EXE SHA256 `eb03ee7fe789564f9e49769ba819ec495ced8480146c32016517985815a990be`; ZIP `4a93068766ea3a33b7bce80cc90aeb99f5fe8076d9d13e1076eb6b08448b8bd1`. `.cache/v065/final-audit.json` confirms source/resource/privacy/CRC and old12 release files/formal hashes unchanged. No used installation overwritten, live-data copy, formal Docker deployment or paid call; previous real-quality/native Save As/second-PC boundaries remain.

## v0.6.4 Source Pagination and Same-Title Reading

Status: complete; backend/browser/real local/frozen acceptance and clean portable delivery passed. Version 0.6.4, schema0004; no physical merge, new tables, migration or runtime dependency.

- Read-only global title grouping with accurate group/source totals, literal keyword filtering and state-aware counts; bounded exact-title member projections and existing individual full-body APIs.
- Numbered pagination, page-size selection and validated page jump; grouped author/body reading with safe rendering, independent edits and retained list/group context.
- Backend/query regression, browser paging/race/security/mobile checks, actual corpus isolation and new frozen EXE acceptance, preserving all live data and old releases.
- Ship a separate complete portable directory, ZIP/checksums and updated instructions after verification. Keep formal Docker and previous real-model quality gates unchanged.

Executed: 809 tests passed, 3 Windows symlink skips and 1 existing warning (39.39s); 25 ESM modules passed. Five synthetic browser groups cover numbered/page-size/jump behavior, editor/409/restore return context, safe oversized content, bounded concurrency, search focus and same-tick route races (`.cache/source-groups-ui/cc06ede91d474cfcbe004eed8b56cd88/report.json`). Real local (`.cache/source-groups-local/28c6165e81e74d1d8bbce882eff17699/report.json`) and real EXE (`.cache/source-groups-validation/44988b71a4bc426ba5719850074a72a6/report.json`) passed 46 groups/48 independent records with complete authored bodies, editing and restart persistence. Read-only corpus acceptance (`.cache/source-group-corpus/82da5e247698417e92588e8ee20168fc/report.json`) matched 571 records/432 groups, 71 repeated titles/max12, all 22 pages and 571 body hashes; original1898 files unchanged, no Knowledge/model side effects.

Complete frozen regression passed 17 flows plus in-flight mock drain and invalid configuration (`.cache/desktop-validation/7838f4117cb941aebe5f68addf6b9aeb/report.json`). Delivery: `dist/PersonalAiMemoryOs-0.6.4/` and 21,948,226-byte ZIP/SHA. EXE SHA256 `02851318327a7424bf8b2d6b261fd5f396fea8d381b4dd9b91ae2fe6e57b04b0`; ZIP `6d5a5182b8d56b10003cd7137dcc3969d697fd5fbb125a89cbfc8f46284aa412`. Final audit `.cache/v064/final-audit.json` confirms pristine release, matching source/static assets, x64 GUI/CRC, 12 older binary/archive/checksum files and formal storage unchanged. The existing 0.6.3 user instance remains running and was not overwritten; complete stopped/backed-up upgrade instructions accompany the release. No new Docker deployment, paid calls or revised real-provider/Save As/second-PC claims.

## v0.6.3 Zhihu Markdown Folder Import

Status: complete; source/browser/actual local/frozen acceptance and clean portable delivery passed. Version 0.6.3, schema0004; no new dependencies or migration. Source-only, offline, text-only ingestion, with user-confirmed preview/commit.

- New bounded Markdown request adapter and per-file report, safe frontmatter/body mapping, pin URL/legacy deduplication support, existing JSON compatibility and durable per-item transactions.
- Folder selection plus multiple-file compatibility, README/media filtering, exact serialized-byte limits, selection/race protection, partial-failure reporting and no retry.
- Synthetic parser/API/browser regression and isolated actual 571-file local/frozen acceptance; preserve private input/formal hashes, create no Knowledge/vault files and make no real-model calls.
- Complete 0.6.3 portable release with old installations preserved or backed up before any stopped-instance upgrade. Document actual results without relabeling real-provider/Save As/second-PC acceptance.

Executed: 780 passed, 3 Windows symlink skips, 1 existing warning (31.95s), 174 import-specific checks and 20 ESM syntax checks. Simulated browser safeguards passed five groups (`.cache/markdown-ui-validation/ba65f331a27c48cfa8eeb2e95fbef4fe/report.json`). Actual local and frozen WebView2/SQLite passed all 571 files, preview/no-write, creation, repeat-zero-new, exact body hashes, report pagination/download, Source-only and restart persistence; reports `.cache/markdown-import-validation/4aea4976ee0b402baf38cfe22925a693/report.json` and `.cache/markdown-import-validation/65516bd88a8c4c488351e79a710cf738/report.json`. Full desktop regression passed (`.cache/desktop-validation/1804c35b68284bc4b1d6c009eaba89ed/report.json`). Original 1,898 files and formal hashes stayed unchanged, zero images/live calls and zero generated Knowledge Markdown.

Delivery `dist/PersonalAiMemoryOs-0.6.3`, ZIP/SHA; EXE `305c166587a748b3bcd23f1d3c8e5bafc59a449876c786fef2bb82dd36db25b6`, ZIP `15f589aeee973e8bf87922df9a14ad0f220aa4c96c54e4c7f32d6ba741669a69`. Artifact checks confirm x64 GUI, ZIP CRC, source fingerprint and clean new directory. Old installations/archives are unchanged, no user program was stopped and no automatic formal import/upgrade was performed. Full upgrade instructions accompany the new backend; all validation data remain in ignored cache, private exports are excluded from Git/Docker/release. Formal Docker and prior real-provider/Save As/clean-PC review limits are unchanged.

Supplemental Docker smoke was attempted with networking disabled and recorded **skipped**, not passed: cached base images were available, but the dependency layer needed an uncached `idna==3.20` wheel. Evidence `.cache/v063-docker-smoke/6883c3437d93/report.json`; no container/network or formal deployment was changed, and cleanup had no errors. The approved local-browser/frozen-EXE acceptance above remains passed. Actual desktop build-environment runtime versions were separately checked against `uv.lock` and matched.

## v0.6.2 Knowledge List and Search Controls

Status: complete; source, browser/regression and independent frozen release verification passed. No new API, migration or dependency.

- Knowledge list checkboxes, current-page select-all, cancel selection and confirmed bulk soft deletion. Deleted notes remain ineligible; changing filters/pages clears selection immediately.
- Submit loaded `expected_version` per note, retain changed records on 409, report partial results and stop unsubmitted work on connection/server failure without retry. Disable stale table controls during loading and return from an emptied last page.
- Align retrieval label/select with search/answer tabs through scoped CSS; preserve `top_k` behavior and narrow-screen wrapping.
- Preserve the running original portable directory and 0.6.1 ZIP. Build 0.6.2 into a separate named directory; never overwrite user storage or redeploy formal Docker.
- Executed: 710 tests passed, 3 permission-related skips, 1 existing warning (34.96s); 64 targeted tests; 18 ESM modules. Real SQLite/Chromium bulk workflow passed 12 cases (`.cache/ui-bulk-live/2c3037854b9a4ca0bbc0db9ba3da054b/report.json`). Separate controlled browser tests passed six behavioral cases and eight responsive search/answer combinations (`.cache/ui-patch-validation/11e438f4b9dd4f51936d688a29d5db4d/report.json`). Real model calls: zero.
- New `dist/PersonalAiMemoryOs-0.6.2` passed full frozen acceptance (`.cache/desktop-validation/8f593aaa09a0439f89b6a57d7bcc16c7/report.json`) and an additional real WebView2/SQLite UI check (`.cache/frozen-ui-patch/5d927111e2454e5d96370e2356c621fd/report.json`): two selected notes deleted/v2, one unselected active/v1, correct expected versions, eight layout combinations, persistence/integrity after exit, released port and no page errors.
- Delivery: EXE SHA-256 `5f1a5843b932bbad75c0aeba0474906b9f4ba5844f5c6ce18f0fb09b0d1e6bae`; ZIP SHA-256 `6d25b3ccc27d7785b5ae5fff67c0622b79268ca97acd64128ceed5949a84b94e`; `.cache/desktop-build-result.json` records matching source fingerprint and 223 clean packaged files. Original EXE/ZIP unchanged.
- The old user app was already stopped when four web resources were backed up and atomically updated. `.cache/desktop-ui-update-result.json` confirms old EXE/ZIP and database/vault/configuration hashes unchanged. Reopen the original EXE for existing-data use; the separate new package starts empty. No user-window reload, process termination, formal Docker deployment or live-model call was performed. Original real-service/Save As/second-PC review limits remain.

## v0.6.1 Portable Windows Desktop Delivery

Status: complete; final Windows x64 portable artifacts and frozen-EXE engineering acceptance passed on 2026-10-17. Version `0.6.1`, schema `0004`; no formal Docker recreation or data migration is part of this delivery.

- Deliver a complete `dist/PersonalAiMemoryOs/` portable directory, ZIP and SHA-256 checksum using a clean project-local build environment.
- Include Python, migrations, prompts, local web assets and configuration templates; exclude personal configuration, data, secrets, browser test binaries and acceptance evidence.
- Keep resource/runtime roots separate; initialize an independent empty portable database, default AI/RAG off, enforce contained data paths and preserve vault identity.
- Use pywebview/WebView2, a dynamic loopback backend and per-directory single-instance activation. Confirm dirty closing and drain in-flight work without automatic forced termination.
- Supported old databases require confirmed, verified full backup before migration. Missing runtime, unwritable storage, invalid configuration and unknown/newer schemas must give useful Chinese errors.
- `scripts/verify_desktop.py` validates the actual frozen EXE under `.cache/desktop-validation`, on a child PATH containing only System32, with real embedded WebView2, native-close messages and formal-storage fingerprints. It tests source/note CRUD, Markdown export/external edit/move, import preview/submit/report download, duplicate launch, dirty close, restart and portable-directory relocation.
- Do not claim second-clean-PC testing, real model acceptance, signed distribution or bundled RAG infrastructure.

Executed results:

- Full pytest **696 passed, 3 skipped, 1 warning** in 37.05 seconds (`.cache/desktop-pytest.log`). Skips require Windows symbolic-link privileges; the warning is the existing upstream TestClient deprecation. Final targeted storage/configuration/migration checks passed 72 tests with one skip/one warning, and final runtime checks passed 16 tests/one warning after strengthening early index-stop behavior.
- Existing `scripts/verify_local.py` and `scripts/verify_docker.ps1` both exited **0**, preserving migration/import/four-protocol/adoption/CRUD/sync/restart/shared-file acceptance and owned cleanup. Logs `.cache/desktop-legacy-local.log`, `.cache/desktop-legacy-docker.log`. All 17 JavaScript modules passed ESM syntax checks.
- Final `scripts/verify_desktop.py --bundle dist/PersonalAiMemoryOs` exited **0**. Report `.cache/desktop-validation/08a46b518be848cfb14bc89742a6e1bd/report.json` records actual WebView2 **155.0.4283.60**, GUI PE subsystem 2, a System32-only child PATH, independent empty initialization, native dirty-close cancel/exit and duplicate launch, source/note CRUD, Markdown export/external edit/move/trash/restore, JSON preview/import/report saving, restart and complete-directory relocation. No page script errors occurred.
- Closing during one held offline provider call waited for the response, persisted a ready draft and created no Knowledge; exactly one mock call and **zero real model calls**. Invalid outside-root configuration showed the Chinese native startup dialog, exited nonzero after acknowledgement and created no outside database. Formal database/vault hashes were unchanged.
- `dist/PersonalAiMemoryOs/` stays pristine, with 222 packaged files and no personal `.env`, database or vault. Final EXE SHA-256: `b61742bd5f3f2430734db40ca767a931309d6c8d34ddd3bac732e0dff19fe18d`; ZIP SHA-256: `4dba32b13d3454568a030295b28608a57365af66e497a69ce50db45fa3ae5f60`. Build/resource/privacy/CRC/checksum evidence: `.cache/desktop-build-result.json` and `.cache/desktop-build-final.log`.

The healthy formal Docker deployment remains **0.6.0**, with schema `0004`, AI/RAG disabled and no acceptance content. Desktop delivery is complete; no second clean Windows PC was tested, and TASK-004/005 real-provider quality acceptance remains pending.

Report saving has one remaining manual review boundary. The main EXE workflow passed **test-mode automatic report saving**, with the exported JSON still present after exit/relocation. The independent production-mode helper (`testing=false`) installed the real hooks and observed native `DownloadStarting`, but did not finish Save As interaction, reach `Completed`, or verify a persisted post-exit file. Its final evidence `.cache/desktop-native-download-review.json` is **`incomplete`** because the verification environment's native control channel was unavailable. Do not treat an earlier briefly visible file as a completed production save, or claim automated selection of the native Save As dialog. The helper timed out its review, then closed its own GUI and HTTP service normally, without forced termination or residual processes. The native Save As interaction remains a manual check; no application or distribution change was made for this clarification.

The separate interactive review was governed by [computer-use/SKILL.md](C:/Users/15050/.codex/plugins/cache/openai-bundled/computer-use/26.1013.31256/skills/computer-use/SKILL.md). Its referenced [guidance.md](C:/Users/15050/.codex/plugins/cache/openai-bundled/computer-use/26.1013.31256/docs/guidance.md) states: “Use `node_repl` JavaScript for all Computer Use actions.” The unavailable native channel was therefore recorded as an incomplete interactive review rather than replaced with another UI-control route. This does not change the separate CDP-based automated EXE tests or their test-mode export results.

## v0.6 TASK-006 Visual Management Workspace

Status: complete; local/Docker engineering acceptance and formal v0.6 deployment passed. Schema stays `0004`.

- Same-service Chinese workspace, local pinned assets and hash routing; no Node build or login.
- Overview counts and lightweight source/note summary lists; all existing mutation/detail APIs retained.
- Source/Knowledge create/edit/trash/restore, source links, Markdown source and sanitized preview.
- Offline JSON preview/submit/report, AI draft preview/adoption, retrieval/cited answers and synchronization/conflict/index/configuration status.
- Preserve unsaved input and stale-version failures; no automatic paid retries, preview truncation or credential forms.
- Python Playwright browser acceptance under `.cache/v06-validation`, with isolated storage/offline models/real Qdrant, local and Docker lifecycle, responsive screenshots, console checks and owned-resource cleanup.

TASK-004 and TASK-005 real-provider quality gates remain pending. No mock result or browser acceptance changes their status or live-call budgets. Formal AI/RAG remain disabled and formal storage must not receive demonstration records.

Executed on 2026-10-17:

- Pytest **655 passed, 2 skipped, 1 warning**, 25.94 seconds. The skips require Windows symbolic-link privileges; the warning is the existing upstream TestClient deprecation. Log `.cache/v06-pytest.log`.
- Existing local and Docker acceptance both exited **0**; logs `.cache/v06-legacy-local.log`, `.cache/v06-legacy-docker.log`.
- `scripts/v06_acceptance.py --mode all --skip-build --image memory-os-v06-validation:latest` exited **0**, using real Chromium, real Qdrant 1.19.2 and offline models. Final report `.cache/v06-validation/f685f6759bea49f99519b873d2dbbdbb/report.json` records both workflow/restart modes passed, formal hashes unchanged and zero real calls. Each cleanup report has an empty errors list. Browser profiles, driver temporaries and downloads stay under the workspace; screenshots cover 1440/1024/390 pixels.
- Browser checks cover stale-version retained input and dirty navigation, same-byte mixed imports/report downloads/partial-503 display, draft preview without notes and adoption, long/safe Markdown, SQLite-to-Qdrant search/cited answers, reference navigation, note trash/restore, dual-edit conflict selection and explicit index rebuild. Deliberate 409/429/503/504 responses are retained in browser console evidence; no script errors or unexpected external requests occurred.
- Seven intercepted navigation/async checks passed (`.cache/v06-async-navigation-review.json`); five focused editor race/field-preservation/restoration checks passed (`.cache/v06-editor-review.json`). `scripts/check_web_modules.py` explicitly parses JavaScript as ESM via existing development Node; filename-only `node --check` was inadequate for this module tree and is not accepted as the syntax check. `scripts/v06_editor_safeguards.py` reproduces the focused editor review with no database/provider access.

Formal deployment passed after a stopped-service full SQLite/vault backup to `data/backups/v0.5-before-v0.6-20261017-bfed7a26`, with every SHA-256 manifest entry verified. No migration was needed: schema remains `0004`. The API is healthy as `10001:10001`, restart count 0, publishes only `127.0.0.1:18000` and reports OpenAPI 0.6.0. SQLite integrity is `ok`; sources/knowledge/origins/processing runs and all three RAG tables remain empty, and vault hashes are unchanged. AI/RAG remain false, formal Qdrant is not started, no real provider was called and no demonstration content entered formal storage. The UI overview has zero counts. Machine-readable result: `.cache/v06-deployment-result.json`. TASK-006 is complete; TASK-004/005 real quality gates remain pending.

Read-only formal Chromium smoke also passed all seven pages with no mutations or script errors, and retained desktop/mobile screenshots in `.cache/v06-formal-browser` (`report.json`). Image inspection confirmed vendored licenses are present and Playwright/`.env` absent. Final owned-resource audit found only the formal API running; validation containers/networks/named volumes were removed.

## v0.5 TASK-005 Implementation and Acceptance

Status: engineering acceptance and formal v0.5 deployment passed. Real Embedding/retrieval/answer quality acceptance remains pending, independently of TASK-004. TASK-005 / Phase 5 is not fully complete.

- [x] Explicit `0003 → 0004` migration, repeated migration, old-data preservation and full regression.
- [x] Independent Embedding profiles, strict vector validation, deterministic bounded chunking and project-local SQLite cache.
- [x] Real Qdrant 1.19.2 ownership, automatic incremental publication, stale/conflict/deleted filtering, recovery and explicit incompatible-config rebuild.
- [x] Search and cited knowledge-only answer interfaces, no-evidence zero generation, malformed-output/context-change failures and shared generation concurrency.
- [x] Local real-process acceptance against isolated Qdrant and offline models.
- [x] Docker acceptance, owned named-volume recreation persistence and complete owned-resource cleanup.
- [ ] Separately budgeted real-provider relevance and answer faithfulness review; unavailable credentials leave this gate pending.

New `scripts/v05_acceptance.py --mode all` (or local/docker) builds a validation image and uses real Qdrant plus deterministic offline Embedding/Chat endpoints. The Qdrant image must first be available as `qdrant/qdrant:v1.19.2`. Reports, model request counters, database, vault and logs remain beneath `.cache/v05-validation/<id>/`; formal data hashes are compared, and owned containers/networks/named volumes are removed in `finally`. No real provider is called, formal AI/RAG are not enabled, and this runner does not deploy or migrate the formal service. `--skip-build --image <v0.5-image>` can reuse a verified image.

The workflow checks no-evidence answers without generation, API-created note indexing, citation/source identity, Markdown edit and path move, deletion exclusion, restoration, explicit rebuild and restart/recreation persistence. Unit/integration tests additionally cover concurrency, configuration drift, failure/interruption recovery, citations and existing feature regressions. No simulated model result qualifies as real semantic quality.

Executed v0.5 legacy Docker regression on 2026-10-17: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_docker.ps1` exited **0**; log `.cache/v05-legacy-docker.log`. Its separate image and isolated project passed explicit migration, CRUD/Markdown synchronization, Zhihu preview/mixed/repeated/deleted-source handling, all four generation protocols, no-note previews, adoption/export/editor updates, recreation persistence/repeated adoption and stopped-container host SQLite/import-identity reads. Final label queries found zero owned containers and networks; the owned temporary directory was removed. The existing formal container remained healthy and was not recreated by that regression.

Final v0.5 verification on 2026-10-17:

- Full pytest: **609 passed, 2 skipped, 1 warning** in **21.76 seconds**; log `.cache/v05-pytest.log`. Skips require Windows symbolic-link privileges; the warning is the existing upstream TestClient deprecation.
- `scripts/verify_local.py` exited **0**; log `.cache/v05-legacy-local.log`, preserving earlier import, four text protocols, adoption, synchronization and restart coverage.
- New `scripts/v05_acceptance.py --mode all --skip-build --image memory-os-v05-validation:latest` exited **0** with **real Qdrant 1.19.2** and offline Embedding/Chat services. Local and Docker full workflows plus restart/recreation passed. Log: `.cache/v05-acceptance-final.log`; report: `.cache/v05-validation/0e022cb9aae0471c8ac2b0efe3c98f32/report.json`. Both cleanup reports have empty errors, all owned containers/networks/named volumes were removed, and only the formal API remained. Formal storage hashes matched before/after isolated validation.
- Real model requests remained **0**. TASK-004 awaits real DeepSeek acceptance; TASK-005 awaits separately budgeted real Embedding relevance and cited-answer quality review.

Formal v0.5 rollout passed after stopping the service and backing up SQLite plus the complete vault to `data/backups/v0.4-before-v0.5-20261017-cf037130`; every manifest entry verified. Explicit migration `0003 → 0004`, tagging the validated image for formal use and `docker compose up -d --no-build` succeeded. The API is healthy as `10001:10001`, restart count 0, loopback 18000, version 0.5.0. SQLite integrity is `ok`; `sources`, `knowledge`, `source_origins`, `processing_runs`, `rag_index_generations`, `rag_note_index_states` and `rag_index_jobs` all have zero rows. Vault hashes remain unchanged. Personal Embedding YAML was copied from its example only because it did not exist and remains ignored; no production key was supplied. AI and RAG are false, formal Qdrant was not started, and no acceptance examples entered formal storage. Evidence: `.cache/v05-deployment-result.json`.

# First Development Tasks

## TASK-001

Initialize project.

Acceptance: - service starts - health API works

Current status: complete; local and Docker acceptance passed.

## TASK-002

Create database models.

Acceptance: - CRUD works

Current status: complete; CRUD, bidirectional Markdown and local/Docker acceptance passed.

## TASK-003

Create Zhihu importer.

Acceptance: - import sample data

Current status: complete; v0.3 local and Docker acceptance passed.

## TASK-004

Create knowledge processor.

Acceptance: - generate structured notes

Current status: v0.4 automated/local/Docker engineering acceptance and bounded DeepSeek real-acceptance preparation passed; credentials are missing, zero live requests have been made and formal AI is off. Not complete.

## TASK-005

Create RAG search.

Acceptance: - answer questions from knowledge base

Current status: v0.5 automated/local/Docker engineering acceptance and formal deployment passed; real Embedding relevance and cited-answer quality remain pending. Not fully complete.

## Historical v0.1 TASK-001 Acceptance (2026-10-15)

Status at this historical checkpoint: foundation implemented and local acceptance passed; Docker acceptance was pending. The checklist below preserves that checkpoint; current completion is recorded above and in the Docker acceptance section.

Implemented foundation scope:

- Python 3.12, uv-managed locked dependencies, project-local runtime/cache/virtual environment, and local Git initialization.
- Validated settings, project-relative persistent SQLite paths, startup connection verification and shutdown disposal.
- FastAPI application factory and database-backed `/health`; no business tables or CRUD.
- Local README commands, non-root single-process Docker image, localhost-only Compose publication and project `data/` bind mount.
- Isolated tests and a repeatable Docker verification script using temporary project-cache data rather than the formal database.

Acceptance checklist:

- [x] Local README startup, `/health`, `/docs` and `/openapi.json` verified.
- [x] Configuration, connection failure, health failure and resource disposal tests passed against temporary databases.
- [ ] Docker image build and Compose startup passed; container became healthy.
- [ ] Temporary SQLite write survived container recreation.
- [ ] After stopping the container, local Python read the same temporary SQLite file.

Local verification results:

- `uv run --locked pytest`: 31 tests passed with Python 3.12.15, FastAPI 0.143.1 and SQLAlchemy 2.0.54. One upstream Starlette/HTTPX deprecation warning was observed; no dependency was added to suppress it.
- Started using the README Uvicorn factory command on `127.0.0.1:8000`, overriding the database to `.cache/local-smoke/memory.db` to preserve formal data.
- Actual HTTP requests returned `/health` 200 with the expected JSON, `/docs` 200 and `/openapi.json` 200. OpenAPI includes the health response schemas for both 200 and 503.
- `Ctrl+C` produced `Application shutdown complete` and `Database connections released` log messages.
- The formal `data/memory.db` file was not created. Python runtime, dependency environment and test artifacts remain within the current project directory.

Constraint recorded at v0.1: Docker Desktop / Docker CLI was unavailable. `scripts/verify_docker.ps1` provides the pending acceptance procedure. Static Docker configuration review does not count as runtime acceptance. The current installation/reboot status is recorded below.

## TASK-002 Acceptance Clarification Recorded at v0.1

In Phase 2, extend the existing CRUD acceptance to include Markdown generation and the agreed database/Markdown synchronization rules. Business models, migrations and this behavior are outside TASK-001.

## v0.2 TASK-002 Implementation and Acceptance (2026-10-16)

Status: complete. Local implementation, automated regression, real-process and Docker acceptance passed; the backed-up formal database has been migrated and the formal Compose service is running. Results below refer to v0.2 only; the historical 31-test run does not validate this release.

Approved implementation:

- Source/Knowledge CRUD with UUIDs, one-to-many nullable source links, optimistic `expected_version`, soft deletion and restoration.
- Explicit Alembic migration and startup schema checks; add Alembic and PyYAML runtime dependencies and bump the application to 0.2.0.
- Bidirectional Markdown creation/edit/move/delete/restore, generated IDs, two-observation stability, two-second polling and ten-second deletion grace.
- Durable baselines/operations, vault identity, preserved conflict snapshots and explicit database/Markdown resolution, including restart recovery.
- Bilingual usage documentation; host port 18000; Docker mounts both data and knowledge and requires a separate migration command.

Acceptance checklist:

- [x] v0.2 unit/integration suite passed against isolated storage.
- [x] Real Uvicorn verification passed for migrations, CRUD/export, external create/edit/move/delete/restore, both conflict choices and restart recovery.
- [x] Formal database and vault were not modified during isolated verification.
- [x] Docker image built, explicit migration succeeded and API became healthy.
- [x] Docker API creation exported Markdown and a host file edit automatically updated the database.
- [x] Both database and Markdown survived container recreation; local Python read the same database after stopping the container.

Use `scripts/verify_local.py` for isolated real-process acceptance and `scripts/verify_docker.ps1` for Docker acceptance. Both use temporary storage beneath project `.cache`. Both acceptance paths have now passed; the Docker result below supersedes the earlier installation/restart checkpoint.

Local real-process result: the complete v0.2 verifier passed with default two-second polling and ten-second deletion grace. It verified API creation/update/export, editor creation with ID backfill, body import, UUID-based moves, external/API soft deletion and restoration, preserved conflict snapshots with both resolution choices, pending export and offline-edit recovery after restart, and host SQLite integrity/content reads. The successful run exited with code 0 and removed its temporary directory after stopping all owned processes.

Storage baseline: the formal zero-byte database already existed from the user's v0.1 service run on 2026-10-16; it was backed up before the upgrade. Isolated v0.2 verification did not migrate or modify that file, and the formal vault remained unchanged. Formal migration/startup is a separate explicitly authorized upgrade step.

Final automated result: **164 passed, 2 skipped, 1 warning**. The skips require Windows symbolic-link privileges unavailable in this environment; Windows junction safety was tested. The warning is an upstream Starlette/HTTPX deprecation notice. No dependency was added to suppress it.

Formal upgrade: the v0.1 database was backed up under `data/backups/v0.1-20261016-e9243604` before `alembic upgrade head` migrated `data/memory.db` successfully to revision `0001`. This authorized upgrade is separate from the isolated tests.

Formal local startup succeeded on `127.0.0.1:18000`: `/health` returned 200 with the established response contract, `/docs` returned 200, and OpenAPI reported version `0.2.0`. Source and Knowledge counts were both zero; no demonstration note was written to formal storage. Synchronization reported `enabled=true`, `running=true`, `last_error=null` and `issues=[]`.

## Historical Docker Installation and Restart Checkpoint

- With user authorization and Windows UAC, WSL 3.0.3.0 (kernel 6.18.54.1-1) was installed and Virtual Machine Platform enabled. Windows explicitly requires restart; CBS `RebootPending=true`. No restart has been performed.
- Docker Desktop 4.95.0 was installed per user at `%LOCALAPPDATA%\Programs\DockerDesktop` with the WSL 2 backend; installer exit code was 0. The official installer had a valid Docker Inc signature and SHA-256 `73431db38491f770543880366228a23c993f84d1e8e045f56d83b8a98940cf76`.
- Version checks passed for Docker CLI 29.8.2, Compose plugin 5.6.0 and Buildx 0.37.2. The user PATH includes Docker's `resources\bin`; the first Desktop launch selected `desktop-linux`. `docker compose config --quiet` exited 0.
- The Engine was still unready after the initial wait. No image build, container migration, health/persistence run or Docker acceptance has occurred. TASK-001/Phase 1 and all Docker checklist items remain incomplete.
- The existing local project's health endpoint remained normal after prerequisite installation.
- After Windows restart: run `docker desktop start`, wait for successful server information from `docker info`, then run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_docker.ps1` from the project directory. Record real results before changing acceptance status.

## Current Docker Acceptance and Formal Deployment

- The Engine is now ready. The updated `scripts/verify_docker.ps1` completed under Windows PowerShell 5.1 with exit code 0, using automatic Windows system-proxy discovery rather than manually injected proxy variables. Log: `.cache/docker-validation-run.log`.
- Image build, explicit Alembic migration, healthy API startup, Source/Knowledge creation, automatic Markdown export, host edit import, forced-recreation database/Markdown persistence, and host SQLite integrity/content reads after container stop all passed.
- Before/after SHA-256 checks confirmed formal `data/memory.db` and vault files were unchanged by isolated verification. Temporary validation directories, containers and networks were removed; the final count was zero. TASK-001/Phase 1 and TASK-002/Phase 2 now meet both local and Docker acceptance.
- Before formal deployment, the database and full vault including `.memory-os-vault` were backed up to `data/backups/v0.2-before-docker-20261016-a3fe0a78`, with a SHA-256 manifest. The explicit container migration was idempotent and exited 0; `docker compose up -d --no-build` exited 0.
- `personalaimemoryos-api-1` is healthy and remains running as `10001:10001`, with non-root identity and restart count 0. It publishes `127.0.0.1:18000` to container port 8000 and binds the project's actual `data` and `knowledge` directories.
- Formal `/health` and `/docs` returned 200, OpenAPI reported `0.2.0`, and Source/Knowledge counts were both zero. Synchronization reported `enabled=true`, `running=true`, `last_error=null`, `issues=[]`.
- The verifier honors explicit process `HTTP_PROXY`/`HTTPS_PROXY`, fills missing values only from valid Windows HTTP(S) system-proxy settings, merges loopback bypasses, and restores all original proxy variables on every exit. Ordinary Compose builds may need temporary process inheritance of the same existing proxy for registry authentication; no machine port or global proxy variable is prescribed.

## v0.3 TASK-003 Implementation and Acceptance

Status: complete; v0.3 automated, real-process local and Docker acceptance passed, and formal deployment is healthy. Earlier release results remain historical.

- [x] Shared JSON parser and API/CLI import behavior passed unit/integration verification.
- [x] Dry-run preview left isolated import state unchanged.
- [x] Mixed valid/invalid input and repeat/change outcomes matched the report contract.
- [x] Persistent deduplication survived container recreation.
- [x] Import did not create or modify Knowledge or vault files.
- [x] Existing v0.2 bidirectional synchronization/persistence acceptance still passed.
- [x] Formal upgrade/startup and backup results were recorded after actual execution.

The API accepts host-submitted UTF-8 `application/json` at `POST /api/v1/imports/zhihu?dry_run=true|false`, using `{schema_version:1,items:[{url,title,author?,content}]}` with up to 10 MiB/500 entries. The report carries counters and ordered per-item identity, skip/difference and field-error details. Migration `0002` adds persistent origins. Docker uses a random verification-only loopback port and no imports-directory mount.

The stdlib CLI is `scripts/import_zhihu.py --file <project-local JSON> [--dry-run] [--base-url <origin>]`; it writes full reports to `.cache/import-reports`. `examples/zhihu-import.sample.json` is synthetic input, not a fetched Zhihu collection.

Final v0.3 verification on 2026-10-17: **270 passed, 2 skipped, 1 warning**. Skips require unavailable Windows symbolic-link privileges; the warning is an upstream deprecation notice. `scripts/verify_local.py` and the extended `scripts/verify_docker.ps1` both exited 0. Logs: `.cache/v03-local-verification.log` and `.cache/v03-docker-verification.log`.

Docker validation used a newly built image and migration `0002`, host HTTP JSON submission, no-write preview, two valid plus one invalid item, unchanged repeated/changed Sources, soft-deleted-source preservation and deduplication after forced recreation. Knowledge/API snapshots and every vault-file SHA-256 remained unchanged through import scenarios. Original bidirectional sync, persistence, stopped-container host SQLite checks and safe cleanup also passed. Formal data was not used for sample imports.

Formal deployment on 2026-10-17 (Asia/Shanghai):

- After stopping the service, `memory.db` and the entire vault including `.memory-os-vault` were backed up to `data/backups/v0.2-before-v0.3-20261017-3815b32d`; `manifest.json` records SHA-256 hashes.
- Explicit migration `0001`→`0002` and `docker compose up -d --no-build` both exited 0.
- The formal container is healthy, runs as `10001:10001`, has restart count 0, binds the actual project data/knowledge directories and publishes `127.0.0.1:18000`.
- Health/docs returned 200, OpenAPI reported `0.3.0` and exposes the import route. Synchronization is enabled/running with `last_error=null`, `issues=[]`.
- The only sample operation against formal storage was CLI `--dry-run`: `would_create=2`, `created=0`, `invalid=0`. Full report: `.cache/import-reports/917359b2-6117-4b89-8e8c-2c0054030c4c.json`. No example was actually imported.
- Final formal checks confirmed revision `0002`, SQLite `integrity_check=ok`, `sources=0`, `knowledge=0`, `source_origins=0`. All vault-file hashes matched the pre-upgrade state, every backup-manifest hash verified, and logs contained no errors.

## v0.4 TASK-004 Implementation and Acceptance

Status: engineering acceptance passed; real-provider compatibility and quality acceptance remain pending. TASK-004 is not fully complete because no real credentials/quality results have been supplied.

- Four configurable protocol adapters and profile discovery with safe credential references; DeepSeek and other provider templates.
- Manual Source generation, immutable provenance, strict structured results/evidence and Knowledge preview, without creating notes before adoption.
- Versioned runs, stale-source rejection, short transactions around remote waits, single concurrent generation, safe failure records and interrupted-run recovery without retries.
- Atomic one-time adoption into normal Knowledge; automatic Markdown export, external editing and repeat adoption after restart.
- Explicit migration `0003`, locked runtime HTTPX, bundled prompts, read-only Docker config and environment key passthrough.

Acceptance evidence:

- [x] Automated v0.4 suite, including four protocols/configuration, failures, concurrency, adoption and earlier regression.
- [x] Real local process plus isolated model service: all four protocols and full draft/adoption/export/edit/restart workflow.
- [x] Docker build/migration/health with isolated internal mock network and random loopback API port; retain older import/sync/persistence/host-read checks.
- [x] Formal storage remains unchanged during isolated acceptance; upgrade backup/migration/deployment documented separately.
- [ ] Real model service compatibility and quality: faithful summary, useful category, source viewpoints separated from AI analysis and exact supporting evidence.

All validation storage is project-local under `.cache`; synthetic credentials/input must not be replaced by personal profiles in automated acceptance. A successful mock run qualifies engineering verification only. Keep TASK-004 incomplete until at least one configured real provider passes the final quality/compatibility check.

Executed on 2026-10-17 (Asia/Shanghai): automated suite **422 passed, 2 skipped, 1 warning** in 17.37 seconds. Skips require Windows symbolic-link privileges, and the warning is the existing upstream TestClient deprecation. `scripts/verify_local.py` exited 0; log `.cache/v04-local-verification.log`. It exercised all four model protocols, original-content evidence, preview without Knowledge/vault changes, one-time adoption, automatic export and external editing, then preserved runs/edited notes and repeat-adoption identity after restart. Mock request records showed exactly four calls, one per protocol, with no new calls from restart/repeated adoption. The earlier import/CRUD/editor/conflict/recovery workflow also passed. The owned temporary directory and both child processes were cleaned up.

`scripts/verify_docker.ps1` also exited 0; log `.cache/v04-docker-verification.log`. The new image, explicit `0003` migration and healthy API passed all four protocol workflows, zero-note/file preview, adoption/export/editor updates and persistence/repeat adoption after forced recreation, alongside the earlier import/sync/shared-host-SQLite checks. All two temporary containers, two networks and validation storage were cleaned up. The three formal storage-file hashes were identical before and after isolated validation. Docker Desktop's internal-only API network did not publish a usable host port, so the verifier now uses a normal API bridge plus a separate internal model-only backend; production Compose is unchanged by this verification-specific arrangement. Both isolated services clear proxy variables and never use real credentials.

Formal v0.4 rollout on 2026-10-17 (Asia/Shanghai):

- Stopped the service, backed up `memory.db` and the entire paired vault to `data/backups/v0.3-before-v0.4-20261017-c80de831`, and verified every manifest SHA-256. Explicit migration `0002 → 0003` and `docker compose up -d --no-build` exited 0.
- Health/docs returned 200; OpenAPI reports 0.4.0 and 17 routes. The container is healthy, runs as `10001:10001`, has restart count 0 and publishes only `127.0.0.1:18000`. Actual data/knowledge mounts are writable and actual config is read-only.
- Bundled prompt was read successfully inside the image; `/app/.env` is absent. Sync reports enabled/running, `last_error=null`, `issues=[]`.
- AI remains `false`. The ignored personal config was copied from the example only because it did not already exist; no real key was added or changed. Profiles list 11 entries, default DeepSeek, and DeepSeek `configured=false`.
- Processing list total is zero. SQLite revision is `0003`, integrity is `ok`, and Source/Knowledge/origin/run counts are all zero; all vault hashes are unchanged. No paid model request or formal sample processing occurred.
- Machine-readable deployment/backup evidence: `.cache/v04-deployment-result.json`, `.cache/v04-deployment-backup.json`.

Remaining acceptance is a real model service: configure credentials, generate from synthetic original material and check provider compatibility, summary faithfulness, category suitability, viewpoint/analysis separation and literal evidence accuracy. Leave Phase 4 / TASK-004 incomplete until that check passes.

## TASK-004 Real-Provider Acceptance Preparation (2026-10-17)

The approved closing plan was established at application `0.4.0` and Alembic revision `0003`. The runner now accepts the current application version and explicitly upgrades isolated storage to the current schema head, retaining compatibility with v0.5 without adding business scope or changing the original three-call budget. Safe preflight confirmed no DeepSeek key and a healthy formal service with AI disabled. **No real model request has been executed (0/3); real-provider and quality acceptance remain pending.**

- Use the existing DeepSeek profile with JSON output and thinking disabled. The owner enters `MEMORY_OS_AI_KEYS__DEEPSEEK` into the project `.env`; keep the formal `MEMORY_OS_AI_ENABLED=false`. Never request or record a key in chat, logs or acceptance reports.
- `scripts/verify_real_provider.py --check` (also the default) performs a non-calling preflight; `--run` explicitly starts bounded live acceptance. Missing credentials/configuration returns 2 without model calls. Evidence stays under `.cache/real-provider-validation/<validation-id>/`. Three original Chinese texts in `examples/real-provider-acceptance.json` cover explicit viewpoints (local), factual material (Docker) and instruction-like source text (Docker).
- The real run may make at most three generation requests, capped at 2,048 output tokens and 90 seconds per request, without automatic retry/provider/model changes. Authentication, insufficient balance or unavailable model stops the run. The Docker stage reuses the stopped local stage's isolated database and vault.
- Cross-process budget locking rejects a new live run if any earlier live attempt (including failed or unknown outcomes) or unresolved lock exists. Restarting the command or creating a new workspace cannot reset the three-call budget.
- Verify preview without notes, adoption/export, external editing, repeated adoption and restart persistence; preserve inputs, run IDs, validated results, available token usage and quality-review criteria. Owned processes/containers/networks are cleaned up while evidence is retained. Test examples must not enter formal storage.
- Human review must approve summary faithfulness, category usefulness, viewpoint/analysis separation, exact evidence and handling of instruction-like source content for all three results. A successful `--run` only records `awaiting_quality_review`; retain the completed `quality-review.json`. Never re-run a failed/unknown attempt merely to obtain a new three-call allowance. Only after quality approval enable formal AI, recreate Compose and verify health/profiles/sync plus unchanged formal counts.

Executed preparation verification on 2026-10-17 (Asia/Shanghai):

- Full pytest suite: **459 passed, 2 skipped, 1 warning** in 14.86 seconds. Skips are Windows symbolic-link privileges; the warning is the existing upstream deprecation.
- `scripts/verify_real_provider.py --check` exited 2 with `waiting_for_credentials` / `ai_api_key_missing`, `actual_model_calls=0`, no attempts, `formal_ai_changed=false` and unchanged formal hashes. Evidence: `.cache/real-provider-validation/2e068b1e930a44d493fe91854cfd9749/report.json`; adjacent inputs and quality-review template are retained, with quality acceptance still false.
- An actual AI-disabled runtime smoke started and stopped local Uvicorn, started Docker against the same isolated database/vault, recreated the container and stopped it. Schema remained `0003`, Source/Knowledge/processing-run tables stayed empty, model calls stayed zero and cleanup had no errors. Formal storage hashes were unchanged. Evidence: `.cache/real-provider-validation/29191844ae894d32a3f343bab0749f12/runtime-smoke.json`.
- Formal service remains healthy, profiles report `enabled=false` with DeepSeek `configured=false`, and synchronization is running without errors. Read-only verification confirmed schema `0003`, SQLite integrity `ok` and zero Source/Knowledge/origin/run rows. Six new Python files passed AST/whitespace checks; no owned isolated processes or temporary real-acceptance containers/networks remained. No formal migration, recreation or AI enablement was performed for this preparation step. Summary evidence: `.cache/real-provider-preparation-result.json`.

Preparation engineering is complete. The AI-disabled smoke and offline tests do not qualify as real-provider or quality acceptance. Leave the real-provider checkbox above, TASK-004 and Phase 4 incomplete until credentials enable the three live cases and their quality review passes.
