# Personal AI Memory OS

[中文使用说明](readme-cn.md)

The [complete Chinese manual](readme-cn.md) covers every management page, installation, import, AI profiles, Markdown synchronization, backup and troubleshooting. See the [step-by-step RAG setup](docs/rag-guide-cn.md) and [full configuration reference](docs/config-reference-cn.md) for Embedding, Qdrant, generation, environment variables and Docker-specific settings.

## Current release: 0.8.0 (schema 0006)

The desktop installation stays at **`dist/PersonalAiMemoryOs-0.6.6/`**. Its historical directory name is retained; the application reports 0.8.0. New clean distributions use `dist/PersonalAiMemoryOs-windows-x64.zip`, built from staging rather than an installation containing user data.

The AI page now supports searchable, paged source checkboxes (up to 20), lazy source preview, sequential individual drafts and one-call merged analysis. SQLite-backed tasks keep progress after navigation; cancellation drains the current call, and restart pauses remaining work. Continue pending items and retry failed calls are separate explicit actions. There are no automatic paid retries.

The independent **Prompt center** manages analysis and RAG-answer templates, each with its own default and immutable revisions. Existing templates retain their content, versions and defaults as analysis templates. The analysis default preserves the complete eight-stage Chinese prompt; the legacy brief template remains available. Deep analysis starts with editable 16,384-token/180-second overrides while preserving the selected model's thinking setting. No browsing is performed. New JSON v2 retains full Markdown and exact source quotes; old v1 drafts remain readable and adoptable. RAG answer templates customize style while the fixed JSON, literal-citation and evidence-only rules remain enforced. Each request freezes its selected revision.

**AI analysis** contains source selection and generation tasks; the separate **Draft box** contains ready/adopted results and full draft details. Old run-detail links remain usable. Lists consistently offer 10/20/50/100 rows, numbered pages and page jumps; source groups load complete bodies only when expanded. This includes template pickers/revisions, tasks/items/attempts, import reports, conflicts and index issues. Paging a result never repeats its model or import request. The 20-source batch cap and search top-k limit remain separate.

**Settings → RAG** saves Embedding profiles, credential references and the Qdrant address, with restart/rebuild guidance. Merely viewing or saving configuration does not probe a provider. Qdrant checking is read-only; Embedding testing requires explicit confirmation and performs one synthetic request without indexing. Saved configuration takes effect after restart. Semantic model/revision/dimension/chunk changes require an explicit index rebuild. No production Embedding service is selected; RAG remains off. Knowledge is the only indexed content, so adopt or write notes before building an index.

Knowledge may link up to 20 sources; `source_id` remains the first-source compatibility field. Multi-source Markdown uses schema v2, while existing v1 files and synchronization baselines are retained. Saving a Knowledge editor, including an unchanged form, returns to the overview. Model settings offer Restart now/Later; automatic restart is desktop-only and waits for calls/sync and the single-instance handover.

Use the same workspace for source changes and clean `.cache` staging for builds. The in-place updater requires a normally closed desktop, verifies backups of the database, full vault and configuration, preserves unknown files, rejects resource/data path overlaps and migrates supported old databases to 0006. Tested source/document units are committed locally without private data or automatic pushes. Docker/source startup still requires an explicit Alembic migration.

```powershell
uv run --locked pytest
docker build -t memory-os-v08-validation .
uv run --locked python scripts/verify_v08_rag.py --mode all
uv run --locked python scripts/verify_v08_web.py --mode local
uv run --locked python scripts/verify_v08_web.py --mode docker --image memory-os-v08-validation
uv run --locked python scripts/build_desktop.py --staging-only
# Replace STAGING with the tested clean directory from .cache/desktop-build-result.json.
uv run --locked python scripts/verify_desktop.py --bundle STAGING
uv run --locked python scripts/update_desktop.py --bundle STAGING
```

The final v0.8 regression passed **1,088 tests, 3 Windows symlink skips and one existing warning** (`.cache/v08/pytest-release.log`), with 42 ESM modules and the locked 47-package dependency set. Local/Docker browsers, the final actual EXE and the `0005 → 0006` old-to-new desktop upgrade passed. Real isolated Qdrant HTTP integration and controlled browser QA transport are recorded separately. Frozen testing includes RAG later/now restart, PID/port release, configuration activation and single-instance handoff. Deep Windows upgrade paths use short exclusive temporary files after a reproduced failure and successful rollback/regression. See [implementation tasks](IMPLEMENTATION_TASKS.md) for exact evidence and boundaries.

The fixed installation was backed up at `backups/upgrade-20261017-152603-89fb11df/`, upgraded and reopened, retaining its current **571 Sources, 2 Knowledge, 3 runs, 1 batch**, existing templates, all private configuration and complete vault bytes. AI state and the user's input limit were preserved; RAG remains off. Formal Docker/project storage and other installations were unchanged. Clean ZIP SHA-256: `0674f332119964ecfc1c00e7159498f961ed3da8c1819ae5e1e40b396f58d703` (22,136,791 bytes). Real provider/RAG quality gates remain pending; engineering checks do not call paid providers.

The preceding 0.7 release passed 1,030 tests with 3 Windows symlink skips and one existing warning (`.cache/v070-release-verified.log`), plus actual frozen generation/restart/upgrade checks. Its clean ZIP SHA-256 was `a020718d2c978269340a21edab1cb2fe67e5eaa87a65b21e8bbfc68384225dc8`; this is a historical artifact, not the new ZIP checksum.

## Historical Windows portable desktop (0.6.6)

Extract `PersonalAiMemoryOs-0.6.6-windows-x64.zip` into a writable directory and double-click `PersonalAiMemoryOs.exe` in `PersonalAiMemoryOs-0.6.6/`. Keep the complete directory, including `_internal`. The frozen application embeds Python and the existing API/UI, opens its own pywebview/WebView2 window, and needs no system Python, uv or Docker for basic management. Microsoft Edge WebView2 Runtime and .NET Framework 4.8 are prerequisites; missing-runtime messages link to Microsoft's installers without installing them automatically.

Version 0.6.6 adds **Settings** below the upper-left brand, a direct settings link in the narrow-screen top bar, and a desktop Settings menu. Manage the text-generation AI switch, default profile and multiple provider profiles, including protocol, address, model, authentication, output limits and advanced JSON parameters. Read the actual runtime, data, database, Knowledge and configuration locations without changing data paths. Embedding/RAG configuration remains separate. Schema stays `0004`; upgrade the complete application to obtain the settings API.

Saving persists the next-start configuration without contacting a model, hot-loading a profile, enabling RAG or restarting the application. Completely exit and reopen before using the changed configuration. Password fields start empty: leaving one blank preserves its existing key; a new value updates that reference for every profile sharing it. Existing keys are shown only as configured/unconfigured and are never returned. Keys are stored in the local `.env`, not YAML, database, browser storage or reports. Process environment values remain authoritative; environment-managed keys cannot be replaced here. Docker settings are read-only: edit the host configuration and recreate that service explicitly.

0.6.6 engineering acceptance passed: **925 tests, 3 Windows symlink skips, 1 existing Starlette/HTTPX warning** in 52.81 seconds (`.cache/v066/pytest-final.log`); 30 browser modules and the locked 47-package dependency check passed. Six controlled Chromium groups passed full four-protocol/advanced-parameter round trips, secret handling, conflicts, read-only state, dirty navigation, late responses and 1440/390 layouts (`.cache/settings-ui/3e237a1470ec44ddabadbcfef1abf23c/report.json`). Real isolated local API/Chromium saved configuration, kept the current runtime unchanged and loaded the profile/key after restart, with zero endpoint/model calls (`.cache/settings-local-real/971c3d69449c4822aec2c418f4cf61d0/report.json`). All four actual frozen-EXE workflows below passed. Formal Docker remains 0.6.0, with AI/RAG off.

The separate 0.6.6 bundle is `dist/PersonalAiMemoryOs-0.6.6/`; ZIP is 21,989,284 bytes. EXE SHA-256 `0899b2b7355f9be23946e30d1258b50839616b448623798daaa93f9ce1ce1b0b`; ZIP `d05d5c512b5b07dff3cc20adfc2dc24f4184ae491dc096ff8a9ba4dd9870ab8e`. Artifact audit `.cache/v066/final-audit.json` confirms the source fingerprint, all 36 web resources, 235 packaged files, x64 GUI/ZIP CRC, a clean release and unchanged 15 older artifacts plus formal storage. Existing installations and their live data have not been overwritten or copied into the new release. No migration is required; the existing transitive `python-dotenv` package is now declared directly, without adding an installed package, provider SDK or framework.

Actual frozen settings acceptance passed (`.cache/ai-settings-validation/cc980ee5477944138fdbc946a39a2d5d/report.json`): one saved update, no hot apply, real exit/restart loading the profile/key, no password DOM/browser-storage echo, retained profiles and business-row hashes, cleaned successful credential journals and zero trapped endpoint calls. Grouped reading passed (`.cache/source-groups-validation/c58681190c554d5bb5adec40be7aee09/report.json`); sorting passed all eight orders over 27 groups/67 Sources with unchanged Source snapshots (`.cache/source-sorting-validation/1079db283786450d9851dfd4a9b9523c/report.json`). Complete desktop regression passed all 17 flows, in-flight mock draining/draft persistence without a Knowledge, and native invalid-configuration feedback (`.cache/desktop-validation/2042177c88c04b149202973303f02499/report.json`). These were actual local WebView2 checks, with zero real model calls and unchanged formal storage; real quality, production native Save As and second-PC review boundaries remain unchanged.

Final cleanup `.cache/desktop-066-cleanup.json` confirms no owned desktop process remains and all four validation ports are closed. The release stays pristine (235 files/43,552,764 unpacked bytes); final artifact/formal hashes still match.

Version 0.6.5 adds Source-library sorting by title, source count, source type and latest update, with ascending/descending controls and clickable column headings. Sorting applies to the complete filtered set before pagination. Changing order resets to page 1; pagination, filtering, refresh and returning from an editor retain the selection. Default remains latest update descending. Titles/types use database character order rather than Chinese pinyin; a mixed-type group uses its alphabetically first visible source type. Schema remains `0004`; install the complete application because sorting runs on the backend.

0.6.5 acceptance passed: **856 tests, 3 Windows symlink skips, 1 existing warning** (55.80s), 26 JavaScript modules, eight browser sort combinations over 45 groups and existing navigation/security regression. Actual frozen WebView2 checked eight global/page orders, both column-heading directions, mixed-type/state behavior, retained group/editor return context and restart persistence on 27 groups/67 independently retained Sources. Sorting left the seeded Source snapshot unchanged. A copy of the previous isolated real corpus separately verified 571 Sources/432 title groups in all eight orders across 176 pages, with every table and file hash unchanged. No real provider calls or formal data writes occurred.

Evidence: sorting UI `.cache/source-sort-ui/84cc445457824fdeb9ab7d9181b811ac/report.json`, navigation regression `.cache/source-groups-ui/afe29bca0f034a57aa501e264d9e1820/report.json`, actual EXE sorting `.cache/source-sorting-validation/4711e8bc33764bdeaa9626dd19a33d50/report.json`, grouped reading `.cache/source-groups-validation/e99a0e13f9164815a627344e472a42a6/report.json`, corpus `.cache/source-sort-corpus/6d5e615811744ad4b312bc678762d6da/report.json`, and complete desktop `.cache/desktop-validation/6a4b97d0b5ed460b94187fa9f5decd13/report.json`. The initial parallel full-desktop attempt ended early after its window shut down normally and is retained as incomplete/failed (`4495fafaad554a42964b720f5c84d091`); the independent sequential rerun passed all 17 flows, in-flight fake-call draining and native configuration checks. The early closure's cause was not established.

The historical 0.6.5 release is `dist/PersonalAiMemoryOs-0.6.5/`, ZIP 21,949,576 bytes. EXE SHA-256 `eb03ee7fe789564f9e49769ba819ec495ced8480146c32016517985815a990be`; ZIP `4a93068766ea3a33b7bce80cc90aeb99f5fe8076d9d13e1076eb6b08448b8bd1`. `.cache/v065/final-audit.json` verifies matching source/static resources, x64 GUI, ZIP CRC/privacy and unchanged 12 previous release files plus formal storage. Used portable installations were not overwritten and their live data were not copied into that pristine release. Use the stopped-and-backed-up upgrade procedure below. Formal Docker remains 0.6.0, and previous real-provider/native Save As/second-PC review boundaries are unchanged.

Version 0.6.4 groups the Source library by exact title across the complete filtered set. Select 20/50/100 titles per page, click numbered pages, or enter a page number. Open a title to read its individual answers with their authors and original links; each remains independently editable and usable for draft generation. Group reading has its own 5/10/20-answer pagination. Returning from an editor retains the group and list position. Grouping changes presentation only: records, IDs, content and versions are retained. No migration is required (schema `0004`). Install the complete release because the new read-only grouping APIs are required.

Historical 0.6.4 verification: **809 tests passed, 3 Windows symlink skips, 1 existing warning** (39.39s); 25 JavaScript modules passed syntax checks. Five controlled Chromium groups cover paging, search focus, safe/large bodies, version conflicts, restore and same-tick navigation races. Actual local and frozen WebView2 workflows passed 46 title groups/48 independent Sources, page-size changes, numbered/jump navigation, complete authored bodies, editor return context and frozen restart persistence. The read-only private corpus was separately imported into isolated cache storage: 571 Sources formed 432 exact-title groups, including 71 repeated titles and a largest group of 12; all 22 pages and 571 original body hashes matched. These grouping/corpus checks created no Knowledge and made no live model calls or modifications to original input files.

Historical 0.6.4 evidence: `.cache/source-groups-ui/cc06ede91d474cfcbe004eed8b56cd88/report.json`, `.cache/source-groups-local/28c6165e81e74d1d8bbce882eff17699/report.json`, `.cache/source-groups-validation/44988b71a4bc426ba5719850074a72a6/report.json` and `.cache/source-group-corpus/82da5e247698417e92588e8ee20168fc/report.json`. At that delivery, the pristine release was `dist/PersonalAiMemoryOs-0.6.4/`; ZIP is 21,948,226 bytes. EXE SHA-256: `02851318327a7424bf8b2d6b261fd5f396fea8d381b4dd9b91ae2fe6e57b04b0`; ZIP: `6d5a5182b8d56b10003cd7137dcc3969d697fd5fbb125a89cbfc8f46284aa412`. Artifact audit `.cache/v064/final-audit.json` verifies matching source/resources, x64 GUI, ZIP CRC, no personal data, and unchanged 12 older binary/archive/checksum files plus formal storage. The used 0.6.3 application was left unchanged during that delivery. Preserve paired data/configuration when upgrading.

Complete frozen regression also passed: 17 desktop flows, graceful completion of an in-flight fake-provider call, native invalid-configuration feedback, restart/relocation and released ports. Report `.cache/desktop-validation/7838f4117cb941aebe5f68addf6b9aeb/report.json`. All regression data stayed under `.cache`; only the existing user desktop remained running afterward. Production native Save As interaction, second-PC compatibility and real-provider quality retain the separate review boundaries documented below.

Version 0.6.3 adds offline Zhihu Markdown directory import. Choose the Markdown mode in Imports, select the exported folder, preview, then commit into Sources. Answers, articles and pins are supported; README indexes and non-Markdown media are skipped. Up to 1,000 files/10 MiB per request, with per-file reports and conservative deduplication. No AI, Knowledge creation or image transfer occurs. This needs the complete new backend; copying frontend assets into an older application is insufficient.

Version 0.6.2 adds Knowledge-list checkboxes, current-page selection and confirmed bulk soft deletion, with per-note version checks and partial-result reporting. Filter/page changes clear selection; trash records cannot be selected. Connection/server failures stop remaining submissions without retries. Search/answer retrieval-count controls now align horizontally with the tabs and wrap on narrow screens. No new API or migration is needed.

Do not overwrite an existing portable folder containing your data. To use the new full release with existing content, close the old application, back up its complete directory, then copy `.env`, `config/`, `data/` and the complete `knowledge/` (including its marker) into the extracted new directory before its first launch. If paths were customized, retain all corresponding contained runtime paths. The new release never imports another installation's data automatically.

The first launch starts an empty independent database with AI/RAG off. `.env`, personal provider YAML, SQLite, Markdown, logs and browser cache stay beside the EXE. A dynamic loopback port avoids the existing Compose service on 18000. Reopening the same directory activates its existing instance; different portable directories remain independent. Desktop data paths cannot escape the portable root. Model services and Qdrant are external and are not bundled.

Close the window to stop gracefully. Unsaved edits require confirmation; synchronization and active calls drain before the backend exits, with a waiting state beyond 150 seconds rather than forced termination. Exit before moving or backing up the directory. Back up SQLite and the complete paired vault including `.memory-os-vault`. Empty databases initialize automatically; supported old databases require confirmed, manifest-verified backup before migration. Unknown/newer schemas stop startup. Normal source/Docker startup still requires explicit migrations.

The release is unsigned and has no installer or automatic updater. Frozen acceptance runs on this Windows x64 machine, with no claim of testing on a second clean computer. `scripts/verify_desktop.py --bundle dist/PersonalAiMemoryOs-0.6.6` copies the pristine bundle into project-local `.cache/desktop-validation`, drives the actual embedded WebView2 through CDP, limits the child PATH to System32, checks native shutdown and data relocation, and fingerprints formal storage. It does not modify the running formal Docker deployment or call paid providers. Existing TASK-004/005 real-quality gates remain pending.

Build and validate from the project directory:

```powershell
uv run --no-sync python scripts/build_desktop.py --output-name PersonalAiMemoryOs-0.6.6
uv run --locked python scripts/verify_desktop.py --bundle dist/PersonalAiMemoryOs-0.6.6
uv run --locked python scripts/verify_ui_patch.py
uv run --locked python scripts/verify_markdown_import.py --mode local
uv run --locked python scripts/verify_markdown_import.py --mode desktop --bundle dist/PersonalAiMemoryOs-0.6.6
uv run --locked python scripts/verify_source_groups.py --bundle dist/PersonalAiMemoryOs-0.6.6
uv run --locked python scripts/verify_source_sorting.py --bundle dist/PersonalAiMemoryOs-0.6.6
uv run --locked python scripts/verify_source_sort_ui.py
uv run --locked python scripts/verify_source_group_corpus.py
uv run --locked python scripts/verify_settings_ui.py
uv run --locked python scripts/verify_ai_settings.py --bundle dist/PersonalAiMemoryOs-0.6.6
```

The build script creates a clean `.cache/desktop-build-venv` from locked `desktop` and `build` dependency groups. Outputs are the portable folder, ZIP and `.zip.sha256` under `dist/`, including SHA-256 checks for the ZIP and EXE. It does not include development browsers or personal storage. Build evidence stays in `.cache/desktop-build-result.json`.

0.6.3 acceptance passed: **780 tests, 3 Windows symlink skips, 1 existing warning** (31.95s), 20 ESM modules, five controlled browser groups and actual local/EXE directory ingestion. Both actual modes previewed 571, created 571 and created zero on repeat, with 522 answers/41 articles/8 pins, 571 matching body hashes, restart persistence and no Knowledge, generated notes, processing/index records, copied images or live-model calls. Original 1,898-file hashes and formal storage remained unchanged. Local report `.cache/markdown-import-validation/4aea4976ee0b402baf38cfe22925a693/report.json`; frozen report `.cache/markdown-import-validation/65516bd88a8c4c488351e79a710cf738/report.json`; complete desktop regression `.cache/desktop-validation/1804c35b68284bc4b1d6c009eaba89ed/report.json`.

Historical 0.6.3 EXE SHA-256: `305c166587a748b3bcd23f1d3c8e5bafc59a449876c786fef2bb82dd36db25b6`; ZIP: `15f589aeee973e8bf87922df9a14ad0f220aa4c96c54e4c7f32d6ba741669a69` (21,932,572 bytes). That delivery preserved existing installations/archives and used `.cache` databases exclusively. Commit your real import through the chosen workbench after preview. Formal Docker remains 0.6.0 without redeployment.

0.6.2 validation passed: **710 tests, 3 Windows symlink skips, 1 existing warning**, 18 ESM modules, isolated real-database bulk-deletion/browser checks, and the complete frozen-EXE workflow. Additional actual WebView2/SQLite acceptance confirmed two selected notes deleted at v2 while the unselected note remained active at v1, correct versioned requests, eight search/answer layout cases, persistence after graceful exit and released ports. Reports: `.cache/desktop-validation/8f593aaa09a0439f89b6a57d7bcc16c7/report.json` and `.cache/frozen-ui-patch/5d927111e2454e5d96370e2356c621fd/report.json`. No real model calls or formal Docker changes.

During the historical 0.6.2 delivery, `dist/PersonalAiMemoryOs` received four backed-up compatible web assets while its backend remained 0.6.1. Evidence: `.cache/desktop-ui-update-result.json`. That frontend-only procedure cannot deliver 0.6.3's new import API: upgrade the complete desktop application after closing and backing up, preserving its paired data/configuration. Each portable directory owns independent data.

Historical 0.6.1 Windows desktop engineering acceptance passed on 2026-10-17: **696 tests passed, 3 Windows symlink cases skipped, 1 existing upstream warning**; final targeted storage/configuration checks and 16 runtime checks passed. Existing source-mode and Docker real-process regression both exited 0. The final frozen EXE passed actual WebView2 155 browser workflows, native dirty-close cancel/exit, duplicate activation, Unicode/space paths, foreign working directory, JSON import/report export, Markdown edit/move, restart and complete-directory relocation. A held local fake-provider request finished and persisted its draft during graceful shutdown without creating a note; real provider requests remained zero. Invalid external data-path configuration showed a Chinese native error and created no outside file. Formal storage hashes were unchanged. Report: `.cache/desktop-validation/08a46b518be848cfb14bc89742a6e1bd/report.json`.

That historical 0.6.1 EXE is `b61742bd5f3f2430734db40ca767a931309d6c8d34ddd3bac732e0dff19fe18d` (SHA-256); its ZIP is `4dba32b13d3454568a030295b28608a57365af66e497a69ce50db45fa3ae5f60`. Each release's checksums are beside its ZIP; current 0.6.6 values are recorded above. The formal Docker service stays at **0.6.0**, was not redeployed for this delivery, and retains its disabled AI/RAG configuration. A second clean PC and real provider quality remain untested.

Report-download acceptance above uses **test-mode automatic saving**, and the exported JSON remained present after exit. A separate production-mode check reached the native Save As workflow (`DownloadStarting`), but its interaction and saved-file review remain **incomplete** because the verification environment's native control channel was unavailable. No successful production Save As selection is claimed; this remains a manual review item. Evidence: `.cache/desktop-native-download-review.json` (`status=incomplete`); the helper closed its own GUI/backend normally without leaving a process.

Version 0.6 adds a Chinese visual management workspace at <http://127.0.0.1:18000/>. It brings together source/import management, Markdown note editing and safe previews, draft adoption, search/answers and synchronization status. Existing APIs and Swagger remain available; schema stays at `0004`. Real-model retrieval and answer quality still require separate acceptance.

The formal v0.6 workspace is running at <http://127.0.0.1:18000/>. Local/Docker engineering acceptance and deployment passed. AI and RAG remain disabled and formal Qdrant stays stopped. TASK-004 awaits real DeepSeek acceptance; TASK-005 engineering acceptance passed while real retrieval/answer quality remains pending.

## Visual workspace

Open <http://127.0.0.1:18000/> after starting the application. It uses the same FastAPI service and loopback port; no frontend build command or additional server is required. Navigation covers overview, Sources, JSON import, Knowledge, AI drafts, search/answers and synchronization/system status. The workspace is for local use and has no account/login system. Keep the existing loopback binding.

Use active/trash/all filters to find retained records. Note edits submit the version originally loaded; a concurrent update preserves local input and offers the latest server version for comparison. Unsaved edits prompt before leaving. A successful save distinguishes database persistence from pending Markdown export. Restore a deleted linked Source first, or explicitly unlink it when restoring the note.

Import previews and submissions use the same selected JSON bytes. Invalid entries and partial commits remain visible in the report, which can be downloaded. Draft generation and cited answers are manual requests with no automatic retries; after a disconnected generation, check the Source's processing records before making another call. Drafts are read-only until adoption. Profile status indicates configuration readiness, not live service connectivity. In 0.6.6, Settings accepts write-only password input into local configuration and manages next-start text-generation enablement; keys are never read back or stored by the browser, and RAG remains separately configured.

Markdown previews use pinned local Marked and DOMPurify assets. Raw HTML is discarded, external images are not loaded and links allow safe schemes only. Body text over 100,000 characters stays fully editable/savable while preview is paused. No runtime CDN is used. Static hosting exposes only `app/web/`, not configuration, SQLite or vault directories.

The UI uses lightweight read-only `/api/v1/ui/overview`, `/sources` and `/knowledge` endpoints. The Source library uses `/api/v1/ui/source-groups` (title totals and source totals) and `/api/v1/ui/source-groups/items` (exact-title member summaries), loading full bodies through existing individual detail APIs. Summary lists support `q`, `state=active|deleted|all`, pagination and optional Knowledge `source_id`; details and all mutations use existing API contracts. Browser state polling runs only on visible relevant pages and does not refresh editing fields.

Settings uses `GET/PUT /api/v1/settings/ai`; writes include the loaded revision and process-scoped configuration token, with loopback Host/same-origin checks. Replies contain key readiness flags only and use no-store headers. A stale revision keeps local input for confirmed manual reload. Only local configuration files are changed; the database schema and live provider objects are unchanged.

To install the project-local acceptance browser and run both real-browser modes:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD '.cache/playwright'
uv sync --locked
uv run --locked playwright install chromium
uv run --locked python scripts/v06_acceptance.py --mode all
```

The browser is a development dependency and is excluded from production images. Acceptance uses isolated SQLite/vault storage and offline models under `.cache/v06-validation`, real Qdrant 1.19.2 with an owned named volume, screenshots at 1440/1024/390 pixels and retained console/report evidence. It cleans up owned processes/containers/networks/volumes and checks formal storage hashes. Mock success is engineering acceptance only and does not consume or expand either real-provider budget.

Executed on 2026-10-17: **655 tests passed, 2 Windows symbolic-link cases skipped, 1 existing upstream warning**, 25.94 seconds (`.cache/v06-pytest.log`). Real Chromium plus real isolated Qdrant and offline models passed both local and Docker workflows, including restart, stale-input retention, import report/download/partial-503 display, safe and oversized Markdown, adoption, citations, trash/restore, conflict selection and explicit index rebuild. Report: `.cache/v06-validation/f685f6759bea49f99519b873d2dbbdbb/report.json`. Browser profiles/driver temporaries/downloads stayed project-local. Both cleanup reports have no errors, formal hashes are unchanged, browser page errors/unexpected external requests are absent and real model requests remain zero. Expected deliberate HTTP 409/429/503/504 console entries are retained in each browser log.

Earlier local/Docker regression also exited 0 (`.cache/v06-legacy-local.log`, `.cache/v06-legacy-docker.log`). Seven fully mocked navigation/race checks passed (`.cache/v06-async-navigation-review.json`), as did five focused editor safeguards (`.cache/v06-editor-review.json`). Optional development checks:

```powershell
uv run --locked python scripts/check_web_modules.py
uv run --locked python scripts/v06_editor_safeguards.py
```

The first command uses an existing Node installation only to check ESM syntax; Node is unnecessary to run or deploy the application. The second uses Chromium with intercepted synthetic APIs and does not mutate a database or call a provider.

Formal v0.6 deployment passed on 2026-10-17 after stopping the service and backing up SQLite plus the complete paired vault to `data/backups/v0.5-before-v0.6-20261017-bfed7a26`; every manifest entry verified. Schema remains `0004` with no migration. The non-root container (`10001:10001`) is healthy on loopback 18000, restart count 0, OpenAPI 0.6.0; SQLite integrity is `ok`, all seven business/index tables remain empty and vault hashes are unchanged. AI/RAG stay false, formal Qdrant is not started and no acceptance samples entered formal storage. Evidence: `.cache/v06-deployment-result.json`.

Read-only Chromium checks of all seven formal pages passed without script errors or mutations, including desktop/mobile screenshots (`.cache/v06-formal-browser/report.json`). The production image contains the vendored licenses and neither Playwright nor `.env`; all owned validation resources are gone and only the formal API remains running.

## Run locally (PowerShell)

Prerequisites: Git and uv 0.13.0. Run every command from this project. Python, dependencies, caches, data, and verification artifacts stay within the project directory. Before switching to local mode, stop the Compose service with `docker compose down`.

```powershell
Set-Location D:\VsCode\PersonalAiMemoryOs
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PWD '.tools/python'
uv python install 3.12 --install-dir $env:UV_PYTHON_INSTALL_DIR --no-bin --no-registry
uv sync --locked
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:create_app --factory --host 127.0.0.1 --port 18000 --workers 1
```

Preserve an existing `.env`. Set the two uv environment variables again in each new PowerShell session. Migrations are explicit: startup checks the schema revision and stops if migration is needed; it does not create or upgrade tables. Stop the service and back up storage before later migrations. Use `Ctrl+C` for graceful shutdown.

- Health: <http://127.0.0.1:18000/health>
- Interactive API: <http://127.0.0.1:18000/docs>
- OpenAPI: <http://127.0.0.1:18000/openapi.json>

## Configuration and storage

Environment variables override project `.env`, which overrides defaults. Tests can inject `Settings` explicitly.

| Variable | Default | Purpose |
|---|---|---|
| `MEMORY_OS_DATABASE_URL` | `sqlite:///data/memory.db` | Persistent SQLite database; relative paths resolve from the project root |
| `MEMORY_OS_KNOWLEDGE_DIR` | `knowledge` | Markdown vault directory within the project |
| `MEMORY_OS_SYNC_ENABLED` | `true` | Enable background synchronization |
| `MEMORY_OS_SYNC_INTERVAL` | `2` | Polling interval in seconds |
| `MEMORY_OS_DELETION_GRACE` | `10` | Missing-file grace period in seconds |
| `MEMORY_OS_LOG_LEVEL` | `INFO` | Standard Python log level |

Only file-based SQLite is supported; in-memory databases, URI/query parameters, and other drivers are rejected. Startup verifies the connection and schema. `/health` returns 200 with `{"status":"ok","database":"ok"}` or 503 with `{"status":"error","database":"unavailable"}`.

Local and Docker modes share `data/` and `knowledge/`; run them alternately. Runtime data, `.env`, `.tools`, `.venv`, and `.cache` are ignored by Git. While the service is stopped, back up the database and entire vault together, including `.memory-os-vault`. Missing or mismatched vault identity can block synchronization to protect existing notes.

## Create and edit knowledge

```powershell
$base = 'http://127.0.0.1:18000/api/v1'
$source = Invoke-RestMethod -Method Post -Uri "$base/sources" -ContentType 'application/json' -Body '{"title":"Reading notes","source_type":"manual","content":"Original material"}'
$note = Invoke-RestMethod -Method Post -Uri "$base/knowledge" -ContentType 'application/json' -Body (@{ title = 'First note'; source_id = $source.id; body = '# My note'; tags = @('reading') } | ConvertTo-Json)
```

One Source can have multiple Knowledge notes; `source_id` can be null for independent notes. Knowledge changes export automatically. To create a note from an ordinary editor, save a file in the vault:

```markdown
---
schema_version: 1
title: A note created in my editor
source_id: null
summary: A short summary
category: null
tags: [reading]
concepts: []
---
# Editable Markdown body
```

New files omit `id`; synchronization generates and writes back a UUID. Preserve existing IDs when editing or moving files within the vault. Unknown or duplicate UUIDs, invalid metadata, and unsafe paths cause synchronization errors. Existing notes cannot change `source_id` through Markdown; use the API to change that relationship.

Files must be stable across two observations before import. Missing files require the deletion grace period and repeated valid scans before soft deletion. API deletion is also soft deletion; use the restore API to recover retained content.

| API | Behavior |
|---|---|
| `POST/GET /api/v1/sources`, `GET /api/v1/sources/{id}` | Create, list, or read sources |
| `POST/GET /api/v1/knowledge`, `GET /api/v1/knowledge/{id}` | Create, list, or read notes |
| `PATCH /api/v1/{sources\|knowledge}/{id}` | JSON `expected_version` plus changed fields |
| `DELETE /api/v1/{sources\|knowledge}/{id}?expected_version=N` | Soft-delete the current version |
| `POST /api/v1/{sources\|knowledge}/{id}/restore` | JSON `expected_version`; Knowledge may also set `source_id` |
| `GET /api/v1/sync/status`, `POST /api/v1/sync/run` | Inspect synchronization or request a scan |
| `GET /api/v1/sync/conflicts`, `GET /api/v1/sync/conflicts/{id}` | Inspect preserved conflict versions |
| `POST /api/v1/sync/conflicts/{id}/resolve` | Select `{"choice":"database"}` or `{"choice":"markdown"}` |

Lists contain `items`, `total`, `offset`, and `limit`; `include_deleted=true` includes soft-deleted records. Knowledge lists also accept `source_id`. Reload the latest `version` before update/delete/restore; stale versions return HTTP 409. Sources with active Knowledge cannot be deleted; detach or delete their notes first.

If both database and Markdown diverge from the shared baseline, both versions are preserved as a conflict. Inspect the snapshots and explicitly choose a version using the conflict API. Ordinary editors do not share an application write lock: conflict checks protect observed versions, while a write racing final file replacement remains a practical limitation.

## Import offline Zhihu Markdown folders

In the target workbench, open Imports and choose the Zhihu Markdown folder mode. Select the export root, collection directory or `articles` directory; multiple Markdown selection is also available. Preview the selected files before committing, then inspect Sources and download the report. A fresh selection invalidates the previous preview. Inputs are read locally and the same serialized bytes are reused for preview/commit; the backend never opens a client-supplied filesystem path.

`POST /api/v1/imports/zhihu-markdown?dry_run=true|false` accepts `{"files":[{"relative_path":"collection/articles/example.md","content":"..."}]}`. The separate limit is 1,000 files and 10 MiB for the complete JSON request; the original JSON import retains its 500-item limit. Decode UTF-8/BOM, parse safe YAML frontmatter, map title/author/source, and preserve the complete body including CRLF. Supported export types are `zhihu-answer`, `zhihu-article` and `zhihu-pin`. Export IDs do not become internal UUIDs; export dates do not overwrite database timestamps. Index README files and media are ignored; unrecognized or malformed documents are reported individually.

Reports retain standard counters and per-item status, adding relative path, title, author, URL and warnings without source bodies. Reimports skip identities and report differences without overwriting or restoring records. A database failure returns HTTP 503 with a partial report. Requests are never automatically retried. Original files and images remain untouched, and image references stay as text without copying/rendering/fetching media. Import creates Sources only: manually generate/adopt drafts into Knowledge before enabled RAG can index them.

## Import offline Zhihu JSON

The importer accepts the project's JSON format, not an arbitrary Zhihu export. It does not visit Zhihu, log in, fetch URLs, or create Knowledge/Markdown. Prepare UTF-8 JSON (a BOM is allowed), up to 10 MiB and 1-500 items:

```json
{
  "schema_version": 1,
  "items": [
    {
      "url": "https://www.zhihu.com/question/123/answer/456",
      "title": "Synthetic example answer",
      "author": "Example author",
      "content": "Offline source text prepared by the user."
    }
  ]
}
```

Each item requires `url`, nonempty `title`, and nonblank `content`; `author` may be omitted or null. Supported resource paths are `zhihu.com/question/<positive integer>/answer/<positive integer>`, `zhihu.com/pin/<positive integer>` (both also accept `www.zhihu.com`) and `zhuanlan.zhihu.com/p/<positive integer>`. HTTP/HTTPS, host case, query/fragment, and an optional trailing slash are normalized to canonical HTTPS URLs. Credentials, explicit ports, lookalike domains, and other resource paths are rejected. Identity combines resource type with its answer, article or pin ID.

Preview the supplied synthetic example first:

```powershell
.\.venv\Scripts\python.exe scripts/import_zhihu.py --file examples/zhihu-import.sample.json --dry-run --base-url http://127.0.0.1:18000
```

For your own input, copy the example into ignored `imports/`, edit it, and preview that file. Removing `--dry-run` performs a real import into the selected server's Source database:

```powershell
if (-not (Test-Path -LiteralPath imports/my-zhihu.json)) { Copy-Item examples/zhihu-import.sample.json imports/my-zhihu.json }
.\.venv\Scripts\python.exe scripts/import_zhihu.py --file imports/my-zhihu.json --dry-run
# After reviewing the preview, explicitly import:
.\.venv\Scripts\python.exe scripts/import_zhihu.py --file imports/my-zhihu.json
```

`--file` must resolve inside the project; `--base-url` defaults to `http://127.0.0.1:18000`. The CLI uploads bytes through `POST /api/v1/imports/zhihu?dry_run=true|false` with `Content-Type: application/json`; Docker needs no imports-directory mount. The API defaults to a real import if `dry_run` is omitted. Preview performs no writes and simulates same-batch deduplication.

HTTP 200 reports `dry_run`, `total`, `processed`, `created`, `skipped`, `invalid`, `would_create`, `failed`, and ordered `items`. Each item reports `index`, `status`, `reason`, identity/source/version fields, `differing_fields`, `matched_source_ids`, and field errors. Valid items can succeed alongside invalid items. Existing identities are skipped, including soft-deleted Sources; they are never overwritten or restored. Differences compare only `title`, `author`, and `content`. Existing manual URL matches are skipped without claiming an import identity; ambiguous multiple matches are reported rather than chosen.

The CLI saves the full report in `.cache/import-reports/<uuid>.json` and prints counters. Invalid/failed items, protocol/network errors, or non-200 responses produce exit code 1; already committed valid items remain imported. Database failure returns HTTP 503 with `detail` and the processed partial `report`. Other protocol errors are 400 for invalid UTF-8/JSON or duplicate object keys, 413 above 10 MiB, 415 for non-JSON media type, and 422 for invalid top-level schema/version/item count.

## Configure models and generate drafts

AI starts disabled. In 0.6.6, open **Settings** below the upper-left brand (or the desktop Settings menu / narrow-screen top-bar link):

1. Select a local template and create a profile, or expand an existing profile. Fill the API prefix, model ID, protocol and key reference. Advanced parameters preserve existing `extra_body`, authentication and protocol-specific settings.
2. Enter a key only when adding or replacing it; blank means keep the existing key. Profiles sharing a reference share its replacement. A deleted profile does not delete its stored key. Environment-managed values must be changed in the launching environment; the container UI is read-only.
3. Enable the intended profile, choose the default and set the text-generation AI switch as needed. Save once, then completely exit and reopen. Saving performs no connectivity test or model call, and does not enable RAG.
4. Check the restarted profile status, then deliberately generate a draft. Configuration readiness is separate from real-provider quality acceptance. The existing formal Docker service remains off and is not upgraded by desktop configuration.

Unsaved changes prompt before leaving. A revision conflict preserves local input; **Reload configuration** asks before discarding it. Network/configuration failures are not automatically retried. The locations section displays the actual database, Knowledge and configuration paths, with no path-edit capability. Local `.env` contains credentials, so treat it and complete-directory backups as private configuration.

For source-mode file configuration, prepare a personal copy before isolated provider acceptance:

```powershell
if (-not (Test-Path -LiteralPath config/ai-providers.yml)) { Copy-Item config/ai-providers.example.yml config/ai-providers.yml }
```

Select a profile in that file, set its actual model ID and API base URL, and set `default_profile`. The example includes DeepSeek and other Chat Completions services, OpenAI Responses, Claude Messages and Gemini GenerateContent. Model names and endpoint availability depend on your provider/account; the examples are configuration templates, not a claim that every service has been live-tested.

Put the referenced `MEMORY_OS_AI_KEYS__<NAME>` in the project `.env` or process environment. For the default DeepSeek profile, use `MEMORY_OS_AI_KEYS__DEEPSEEK`; enter the key locally, never in chat. Keep `MEMORY_OS_AI_ENABLED=false` for the formal service until isolated real-provider compatibility and quality acceptance pass. Keys stay outside YAML and are never returned by the profiles API. Environment variables override `.env`. `MEMORY_OS_AI_DEFAULT_PROFILE` optionally overrides the YAML default. `MEMORY_OS_AI_CONFIG_FILE` defaults to `config/ai-providers.yml` locally; Compose uses `/app/config/ai-providers.yml`.

| Protocol | API suffix appended to `base_url` | Examples |
|---|---|---|
| `openai_chat` | `/chat/completions` | OpenAI, DeepSeek, Qwen, SiliconFlow, Ark, Kimi, Zhipu, compatible endpoints |
| `openai_responses` | `/responses` | OpenAI Responses-compatible endpoints |
| `anthropic_messages` | `/messages` | Claude Messages-compatible endpoints |
| `gemini_generate_content` | `/models/{model}:generateContent` | Gemini native endpoints |

Keep the version prefix in `base_url` when the provider requires one. Profiles select model, optional key reference, authentication (`auto`, `bearer`, `x_api_key`, `x_goog_api_key`, `none`), output/timeout limits and approved `extra_body` parameters. Chat supports `prompt`/`json_object` output and either token-limit field; the other protocols use prompt-constrained JSON. All results receive the same strict validation. Extra parameters cannot replace messages, models, authentication, streaming or controlled output fields. No fallback or automatic retry is performed. Profiles are loaded at startup; restart after editing them.

Use Swagger in this order:

1. `GET /api/v1/ai/profiles` lists enabled/configured profiles without secrets.
2. Create or select an active Source with nonempty original text.
3. `POST /api/v1/processing/runs` with `{"source_id":"<UUID>","expected_source_version":1,"profile_id":"deepseek"}` generates a draft (201). Omit `profile_id` to use the default.
4. `GET /api/v1/processing/runs/{id}` displays the validated result, note proposal and source-staleness flag. Lists support `source_id`, `status` and `profile_id` filters.
5. `POST /api/v1/processing/runs/{id}/adopt` with `{"expected_version":<draft version>}` creates one Knowledge (201). Repeated adoption returns that same note (200), including after restart. Edit the adopted note through API or Markdown.

Generation and preview create no Knowledge or Markdown. Results contain title, summary, free-text Chinese category, tags, concepts, key points, and opinions separating source evidence from AI analysis. Evidence must occur in the source. Adoption renders these into Markdown sections and schedules normal synchronization; inspect the returned Knowledge `sync_status` to distinguish saved records from exported files.

Default input is at most 20,000 source-content characters (`MEMORY_OS_AI_MAX_INPUT_CHARS`); long sources are rejected, never truncated. Profile defaults are 4,096 output tokens and 90 seconds total request time; responses are limited to 1 MiB. Invalid, refused or truncated output fails without a note. One generation can run at a time (429 otherwise). Disabled AI/missing credentials return 503, disabled profiles 409, unknown profiles 422; source-version conflicts return 409 and invalid/oversized source content 422. Model errors return 502, timeouts 504, with a safe code and run ID. Check the run list after a client timeout before starting another paid request.

Sources changed or deleted after generation make drafts stale and adoption returns 409. Each explicit regeneration creates a new run. Startup marks leftover running jobs interrupted without invoking a model again. Adopted notes are not automatically restored if later deleted. Real-provider compatibility and quality require separate live acceptance; mock success does not certify all vendors.

### DeepSeek real-provider acceptance

The original closing plan was prepared at version 0.4.0 and schema revision `0003`. On 2026-10-17, preflight found no DeepSeek key; **zero real model requests have been made** and formal AI remains off. TASK-004 is still pending real-provider acceptance.

This is the historical v0.4 acceptance scope. Its runner now accepts the current application version and explicitly migrates isolated storage to the current schema head, so it remains usable with v0.5 code. That compatibility update does not enlarge or reset the original three-call budget, enable formal AI, or qualify v0.5 retrieval/answer quality.

Use the existing DeepSeek profile (`deepseek-flash`, JSON output, thinking disabled). Its model ID must be available to your account; authentication, balance or model-availability failures stop acceptance without switching providers or retrying automatically. Original acceptance inputs are in `examples/real-provider-acceptance.json`.

Run the non-calling preflight from this project first. Omitting a flag also selects `--check`:

```powershell
.\.venv\Scripts\python.exe scripts/verify_real_provider.py --check
```

Exit code 2 means credentials/configuration are not ready and no real call was made; 0 means configuration is ready, without proving live compatibility. The printed directory contains `report.json`, `inputs.json` and `quality-review.json`. After filling the local key and reviewing the configuration, this explicit command starts the paid acceptance workflow:

```powershell
.\.venv\Scripts\python.exe scripts/verify_real_provider.py --run
```

Do not repeat `--run` after an error or disconnect without first inspecting the previous report: a reserved request may have reached the provider even if its outcome is unknown. A cross-process budget lock rejects live execution when any prior live attempt or unresolved lock exists; a new evidence directory does not renew the three-call budget. The runner never enables formal AI. A successful workflow exits 0 with `awaiting_quality_review`; complete and retain `quality-review.json` after inspecting the actual outputs before treating acceptance as passed.

Real acceptance uses a separate database, vault and loopback port beneath `.cache/real-provider-validation/<validation-id>/`. It is limited to three generation requests in total: one local opinion-bearing Chinese technical text, then two Docker cases covering factual text and instruction-like source content. Each request is capped at 2,048 output tokens and 90 seconds. The Docker stage reuses the stopped local stage's isolated storage. The report preserves inputs, run IDs, results, available token usage and review criteria without keys or raw upstream responses; formal storage is never used for these examples.

Check summary faithfulness, category usefulness, viewpoint/analysis separation, literal evidence and resistance to instructions embedded in source text. The workflow also verifies preview without notes, adoption/export, Markdown editing, repeated adoption and restart persistence. Passing automated checks is followed by explicit human review of all three results. Temporary processes/containers/networks are released; isolated evidence is retained for review.

Only after all three cases and quality review pass, confirm no formal generation is running, set `MEMORY_OS_AI_ENABLED=true` and run `docker compose up -d --force-recreate api`. Verify `/health`, profile readiness and sync status, and confirm no acceptance examples entered formal storage. On failure or missing credentials, leave formal AI off and TASK-004 pending.

## Configure semantic search and cited answers

RAG is opt-in. Copy `config/embedding-providers.example.yml` to ignored `config/embedding-providers.yml` without overwriting an existing personal file. Choose a compatible `/embeddings` service independently of the text-generation provider; DeepSeek generation does not imply an Embedding endpoint. No model is downloaded by the application.

```yaml
schema_version: 1
default_profile: embedding
profiles:
  embedding:
    enabled: true
    protocol: openai_embeddings
    base_url: http://127.0.0.1:8080/v1
    model: your-embedding-model
    dimension: 1024
    api_key_ref: embedding
    auth: bearer
    batch_size: 8
    timeout_seconds: 60
```

Replace the address/model/dimension with values supported by your service. `dimension` validates the expected output; it is not automatically sent as a request option. Set `request_dimensions` only if the provider explicitly supports that parameter, and keep it equal to `dimension`. For a local service requiring no key, explicitly use `auth: none`. Model or model revision, dimension and chunking changes require an explicit new-generation rebuild. Environment keys override `.env`; YAML and API responses never contain secrets.

| Variable | Default | Purpose |
|---|---|---|
| `MEMORY_OS_RAG_ENABLED` | `false` | Enable indexing/search; does not enable text generation |
| `MEMORY_OS_EMBEDDING_CONFIG_FILE` | `config/embedding-providers.yml` | Project-local profile YAML |
| `MEMORY_OS_EMBEDDING_DEFAULT_PROFILE` | YAML default | Optional profile override |
| `MEMORY_OS_AI_KEYS__EMBEDDING` | empty | Credential for `api_key_ref: embedding` |
| `MEMORY_OS_RAG_QDRANT_URL` | `http://127.0.0.1:6333` | Local API connection; Compose fixes its API to `http://qdrant:6333` |

Start the real Qdrant dependency with `docker compose --profile rag up -d qdrant`. Its pinned image is `qdrant/qdrant:v1.19.2`; HTTP is published only on `127.0.0.1:6333`. Qdrant alone uses a Docker named volume, which is outside the project directory and survives ordinary `docker compose down`. Avoid `down -v` against formal storage. SQLite retains the current vectors needed to recover the index. Back up the stopped SQLite database and full Markdown vault together; index collections can be rebuilt from the current cache.

After configuration and explicitly authorized real-service acceptance, set RAG true and restart the API. Search needs only RAG and Embedding. Ask additionally needs `MEMORY_OS_AI_ENABLED=true` and a ready text-generation profile. Both flags stay false in the delivered defaults. A container cannot reach a host-local model through `127.0.0.1`; use an address accessible from the container, such as Docker Desktop's `host.docker.internal` when appropriate.

| API under `/api/v1/rag` | Behavior |
|---|---|
| `GET /embedding-profiles` | Safe configuration readiness |
| `GET /index/status` | Index generation, pending/excluded notes and errors |
| `POST /index/run` | 202; incrementally reconcile; `{"retry_failed":true}` explicitly authorizes failed-call retry |
| `POST /index/rebuild` | 202; rebuild a new compatible generation |
| `POST /search` | `{"query":"索引有什么成本？","top_k":5}`; verified snippets and scores |
| `POST /ask` | `{"question":"索引有什么成本？","top_k":5}` plus optional generation `profile_id` |

Queries are limited to 2,000 characters; `top_k` defaults to 5, maximum 10. A fixed-format Knowledge projection is split into 1,200-character chunks with 200 overlap, up to 100,000 characters/200 chunks per note. Over-limit notes are errors, not truncated. The default background interval is five seconds. Deleted, conflicted, synchronization-error and stale index versions are excluded; a pending Markdown export alone does not block indexing. Source text and unadopted drafts are never indexed.

Search includes `index_incomplete`; incomplete indexing must not be interpreted as an empty knowledge base. Answers contain paragraphs plus checked quotes, Knowledge IDs/versions, current file paths and source information. No retrieved evidence returns an explicit insufficient-evidence response without a generation call. Unsupported quotes or malformed output fail with 502; a note changed during generation fails with `409 context_changed`. Citations prove traceability; faithful reasoning still requires real quality review. Drafts and answers share one generation slot; Embedding is separately limited.

Paid Embedding failures, unknown outcomes and interrupted calls are not automatically retried. Inspect status before explicitly submitting `retry_failed:true`; cache-backed Qdrant writes can recover without calling the model again. Qdrant failure affects RAG availability, while existing CRUD/import/sync and `/health` retain their behavior.

## Run with Docker

Prerequisites: Docker Desktop with Linux containers and the Compose plugin (`docker compose`). The image uses Python 3.12 slim, uv 0.13.0, locked runtime dependencies, one Uvicorn process, and non-root UID/GID 10001.

Docker Desktop and WSL are installed, and v0.4 isolated container engineering verification passed. To resume Docker and rerun isolated verification after a future Windows restart, use the project directory:

```powershell
docker desktop start
docker info
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_docker.ps1
```

Wait until `docker info` successfully reports the server before running verification. Before upgrading v0.4 to v0.5, stop the service and back up the database and entire vault including its marker. Explicitly migrate `0003` to `0004` before starting v0.5. For normal Docker operation after verification:

```powershell
docker compose build
docker compose run --rm api /app/.venv/bin/alembic upgrade head
docker compose up -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:18000/health
docker compose logs api
docker compose down
```

Compose binds `./data` to `/app/data`, `./knowledge` to `/app/knowledge`, and `./config` read-only to `/app/config`, fixing container paths independently of host `.env`. AI/RAG default off, so personal YAML may be absent until configured. It explicitly passes the example providers' named keys and the Embedding key; add a matching Compose environment entry for custom references. `.env` and personal YAML are excluded from the image; bundled prompts and both configuration examples are included. The API publishes `127.0.0.1:18000` to container port 8000 and allows 150 seconds for graceful shutdown. Migrations remain explicit. Start the optional Qdrant service with the `rag` profile when enabling RAG; no Qdrant dependency is required while RAG is off.

On native Linux, allow both container UID/GID 10001 and the local service user to read/write the two shared directories. On Windows, check Docker Desktop directory sharing if a bind mount is inaccessible.

The verifier preserves explicit `HTTP_PROXY`/`HTTPS_PROXY` values. When missing, it adopts a valid HTTP(S) proxy from existing Windows system settings for its process, merges loopback entries into `NO_PROXY`, and restores all three original variables on exit, including failures. It does not write user/system proxy variables or embed a machine-specific port. Ordinary `docker compose build` does not invoke this helper; registry authentication network failures may require temporarily inheriting the same existing system proxy in that PowerShell process, then restoring its prior environment.

## Verification

v0.5 uses real Qdrant and deterministic offline model endpoints. Pull its pinned image once, then run both isolated modes (or select `--mode local` / `--mode docker`):

```powershell
docker pull qdrant/qdrant:v1.19.2
.\.venv\Scripts\python.exe scripts/v05_acceptance.py --mode all
```

The runner builds a separate validation image. Use `--skip-build --image <already-built-v0.5-image>` to reuse an explicitly selected image. It keeps reports, mock request counters, SQLite and Markdown under `.cache/v05-validation/<id>/`. Every mode uses an owned Compose project and Qdrant named volume; containers/networks/volumes are removed on exit while evidence is retained. Docker mock services have only an internal network and no published ports; local mock code performs no outbound requests. All model traffic targets those offline mocks, never personal providers. Formal storage hashes are checked before/after.

The workflow covers empty evidence without generation, automatic indexing, cited answers, Markdown edit/move, stale/deleted exclusion, restoration, rebuild and restart/recreation persistence. Engineering success does not establish real semantic relevance or answer quality. TASK-005 remains pending real Embedding and generation-service quality acceptance under a separately approved call budget.

v0.5 engineering acceptance passed on 2026-10-17: **609 tests passed, 2 Windows symlink-privilege skips, 1 existing upstream warning** in 21.76 seconds (`.cache/v05-pytest.log`). Real Qdrant 1.19.2 plus offline model local and Docker workflows/restarts both passed; evidence: `.cache/v05-validation/0e022cb9aae0471c8ac2b0efe3c98f32/report.json`, log `.cache/v05-acceptance-final.log`. Owned containers, networks and named volumes were removed without errors, and formal storage hashes were unchanged. Existing local/Docker regression scripts also exited 0 (`.cache/v05-legacy-local.log`, `.cache/v05-legacy-docker.log`). Real provider calls: **0**.

Formal v0.5 deployment passed after stopping the service, backing up SQLite/full vault to `data/backups/v0.4-before-v0.5-20261017-cf037130` and verifying the complete manifest. Explicit migration `0003 → 0004` and Compose startup succeeded. The API is healthy as `10001:10001`, restart count 0, on loopback 18000; OpenAPI reports 0.5.0. SQLite integrity is `ok`, the four business/import/run tables and three RAG tables remain empty, and vault hashes are unchanged. Personal Embedding YAML was copied from the example only because no file existed; no production credential was added. AI/RAG remain false, formal Qdrant was not started, and acceptance samples did not enter formal storage. Evidence: `.cache/v05-deployment-result.json`.

Earlier regression verifiers remain available:

```powershell
uv run --locked pytest
.\.venv\Scripts\python.exe scripts/verify_local.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_docker.ps1
```

The local verifier uses a free loopback port and temporary `.cache` database/vault with real Uvicorn and a stdlib-only mock model process. Docker uses an independent Compose project with isolated data/config/vault and a mock-only internal network; only its API receives a random loopback published port. Both retain earlier CRUD/sync/import/restart checks and add all four model protocols, generation/preview with unchanged Knowledge/vault, adoption, export, external edit, one-time adoption and persistence after restart. Mock profiles use synthetic credentials and original sample text, never personal configuration or real APIs. Both stop owned processes and validate cleanup boundaries; neither uses formal storage.

Real-provider preparation verification on 2026-10-17: **459 tests passed, 2 Windows symlink privilege cases skipped, 1 existing upstream warning** in 14.86 seconds. `--check` exited 2 with `ai_api_key_missing`, zero model calls and unchanged formal storage; evidence: `.cache/real-provider-validation/2e068b1e930a44d493fe91854cfd9749/report.json`. A separate AI-disabled smoke check started/stopped the local runtime, reused its isolated schema-`0003` database/vault in Docker, recreated the container and stopped it successfully. It retained empty business tables, made no model calls, cleaned up without errors and preserved formal storage hashes; evidence: `.cache/real-provider-validation/29191844ae894d32a3f343bab0749f12/runtime-smoke.json`. Formal health is good, synchronization is running, profiles report `enabled=false` and DeepSeek `configured=false`. Preparation is complete; live compatibility and quality acceptance remain pending.

Initial v0.4 engineering verification on 2026-10-17: **422 tests passed, 2 Windows symlink privilege cases skipped, 1 upstream deprecation warning**. Real-process local and Docker acceptance both exited 0, including all four protocols, zero-note preview, adoption/export/edit, repeat adoption and restart persistence. Docker also retained import/sync/persistence/host-SQLite checks and removed both owned containers/networks. Logs: `.cache/v04-local-verification.log`, `.cache/v04-docker-verification.log`. Formal database/vault hashes were unchanged by isolated verification. Docker uses a normal API bridge for reliable loopback port publication and a separate internal model network.

Formal v0.4 deployment passed after a stopped-service database/full-vault backup to `data/backups/v0.3-before-v0.4-20261017-c80de831` with a verified SHA-256 manifest, explicit `0002 → 0003` migration and Compose restart. Health/docs returned 200, OpenAPI reported 0.4.0, synchronization had no errors, and the non-root healthy container retained restart count 0. Config is mounted read-only; the prompt is present in the image and `/app/.env` is absent. SQLite integrity is `ok`, all Source/Knowledge/origin/run counts remain zero, and vault hashes are unchanged. The ignored personal YAML was created from the example only because it did not exist; AI remains off, 11 profiles are listed, DeepSeek is the default and is unconfigured without a key. No paid model or formal sample processing was run.

Engineering acceptance passed. **TASK-004 remains incomplete pending real-provider compatibility and quality acceptance.** Historical results below refer to earlier releases.

v0.3 acceptance on 2026-10-17: **270 tests passed, 2 Windows symlink privilege cases skipped, 1 upstream deprecation warning**. Both real local and Docker verifiers exited 0. The Docker run verified migration `0002`, host JSON preview/mixed import, repeated/changed/deleted-source preservation, post-recreation deduplication, unchanged Knowledge/vault, host SQLite reads and cleanup. Logs: `.cache/v03-local-verification.log` and `.cache/v03-docker-verification.log`.

Formal v0.3 deployment also passed on 2026-10-17 (Asia/Shanghai): full storage backup `data/backups/v0.2-before-v0.3-20261017-3815b32d` with a hash manifest, explicit `0001` to `0002` migration, and healthy non-root Compose startup on port 18000. Health/docs returned 200, OpenAPI reported 0.3.0 with the import route, and synchronization had no reported errors. The sample CLI was used only with `--dry-run` (`would_create=2`, `created=0`, `invalid=0`); no example was actually imported into formal storage.

Final formal checks confirmed revision `0002`, SQLite integrity `ok`, and zero Source/Knowledge/origin rows. All vault-file hashes matched the pre-upgrade state, every backup-manifest hash verified, and logs contained no errors.

Current results and historical acceptance are in [IMPLEMENTATION_TASKS.md](IMPLEMENTATION_TASKS.md). TASK-001, TASK-002 and TASK-003 have passed both local and Docker acceptance. The following deployment/test entries describe the earlier v0.2 checkpoint.

Local v0.2 acceptance on 2026-10-16: 164 tests passed, 2 Windows symlink privilege cases skipped, and the full real-process workflow passed. The backed-up formal v0.1 database was explicitly migrated to revision `0001`.

Formal local startup also passed health/docs/OpenAPI checks on port 18000 with synchronization running and no reported errors. Source/Knowledge storage remained empty; verification examples were kept in isolated storage.

Docker verification passed image build, explicit migration, health, API-to-Markdown export, host edit import, container recreation persistence, host SQLite reads, and cleanup under Windows PowerShell 5.1. Formal storage hashes were unchanged by isolated verification. Before the formal switch to Compose, the database and complete vault were backed up to `data/backups/v0.2-before-docker-20261016-a3fe0a78` with a SHA-256 manifest. The non-root formal container is healthy on `127.0.0.1:18000`, synchronization reports no errors, and Source/Knowledge counts were both zero at verification.

## Troubleshooting

- Migration requested at startup: run Alembic against the same database configuration, then restart.
- Storage errors: check permissions, schema readiness, vault identity, and `/api/v1/sync/status`.
- Downloads fail: check connectivity and reuse existing proxy settings in the current PowerShell session.
- Port 18000 is occupied: stop the other local/Docker service before switching modes.
- An open conflict remains: inspect both snapshots, reload current state, and explicitly resolve it. Preserve database files and vault markers for diagnosis.
- Docker Engine unavailable: start Docker Desktop and check `docker info`; if Windows reports a required virtualization-feature restart, complete that restart before retrying.

See [ARCHITECTURE.md](ARCHITECTURE.md), [DATABASE_DESIGN.md](DATABASE_DESIGN.md), and [ROADMAP.md](ROADMAP.md) for architecture, storage decisions, and later stages.
