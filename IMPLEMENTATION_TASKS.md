# IMPLEMENTATION_TASKS.md

## Approved follow-up implementation — in progress (2026-11-15)

Summary integration source unit verified at **0.13.0 / 0008**: shared production/pilot evidence contract, one-request detailed summaries for new arrivals, durable version-checked candidates, explicit idempotent adoption, previous-note snapshots and cache-only pilot importer. Monthly reservation includes external pilot accounting metadata. Focused verification: 42 passed; earlier collection/pilot/reading group 63 passed; 54 ESM modules, docs/release checks and source Chromium bookshelf passed (`.cache/reading-verification/338c4c29a15a41f1928df242bd139a48/report.json`). Desktop packaging and actual adoption remain pending this implementation run.

User approved the existing detailed-summary style for the ten pilot articles and future arrivals, with older articles upgraded on demand. Topic synthesis is manual and marks member changes stale. New organization, topic generation and this task's real quality checks share CNY 30 per calendar month. Preserve all previous ledgers and user edits. Implementation proceeds through summary integration, classification/draft review, topic synthesis, targeted quality/performance verification and fixed-directory desktop delivery. Physical reboot/second-PC and account-dependent coverage require their actual environments. The pre-change audit passed 1342 tests with three existing symlink skips; 53 ESM modules, docs and release checks passed. This entry records authorized scope, not completion.

## Ten-article summary quality pilot — delivered for review (2026-11-15)

Status: **implemented and generated; user style approval pending**. A separate maintenance CLI provides `prepare`, explicit `generate --allow-paid`, and offline `report`. It freezes two long articles, two image-heavy articles (including the previously approved partial-image sample), and six ordinary articles spread across available themes. Current titles, categories, tags, note versions and original/image hashes are preserved. No production API, table, migration, automatic adoption or desktop upgrade was added; fixed desktop remains 0.12.0 / schema 0008.

Real pilot completed **10/10 candidates**, using the configured OpenAI default with a 4096-output-token request override. Exactly **10 generation requests**, conservative accounting **3.671420 yuan**, within the shared **5-yuan** authorization. The durable budget survives new output directories; uncertain requests keep reservations and are not retried. Cached replies were revalidated after correcting caption/excerpt validation boundaries, with no additional generation. Existing clear image observations were reused; no new vision request. Full original text was supplied for both long articles, without silent truncation.

Offline report: `.cache/summary-quality/pilot-20261115/report.html`; complete Markdown, frozen samples, candidate results and `review.json` are alongside it. Codex source-comparison preliminary review: **8 improved / 2 same**, no fatal findings recorded. Short source articles showed limited benefit from expansion; future rollout should retain concise treatment for them. This is not user approval, independent factual verification or authorization to replace all existing summaries. The report exposes literal Q quotations and existing O image observations for inspection.

Verification: **43 targeted tests passed**, one existing Starlette warning; docs/release checks passed. Offline Chromium verified all ten three-column comparisons, local images, narrow layout, zero external requests and no page errors. Evidence: `.cache/summary-quality-regression.log`, `pilot-20261115/browser-verification.json`, `report-status.json`, and the shared `budget.json`. `.cache/summary-quality/formal-integrity.json` confirms the same 578 Sources, 580 Knowledge, 702 historical collection calls and all checked business rows, plus identical hashes for 1903 original and 1892 mirror files. Personal artifacts and credentials stay outside Git; source changes are locally committed, not pushed.

## Reading bookshelf — final delivery (2026-11-15)

Status: **complete, 0.12.0 / schema 0008, installed in `dist/PersonalAiMemoryOs-0.6.6`**. The sidebar bookshelf covers **578 published Zhihu favorites / 9 first-level topics**: overview, combined filters, keyword excerpts, stable pagination, current edited notes, original snapshots, complete long-form reading, keyboard image gallery and return state. Existing summaries, manual edits and partial-image warnings remain intact. General knowledge, semantic retrieval and cited answers retain their existing pages; topic synthesis and paid regeneration are outside this delivery.

Final regression: **1333 passed, 3 existing Windows symlink skips, one existing Starlette warning**. The 129 targeted reading/collection/sync checks, 53 JavaScript modules, lock, docs and release checks passed. Source browser: `.cache/reading-verification/232cc13fb70e46759887323a798bef91/report.json`; final frozen bookshelf/reopen: `.cache/reading-verification/9e7f5eac4644492588ca4ec59d8d21ce/report.json`. Earlier same-version full desktop workflow (editing, import, trash, external edits, restart, relocation and draining): `.cache/desktop-validation/41a63b6176854478aad1ab9186b1a5ad/report.json`. The final read-lock optimization was checked by the final frozen bookshelf and regression.

Real-size read-only copy: `.cache/reading-real-verification/c9b68e531ea44335af58e9bdc856fb81/report.json`, all 578 unique records reachable without changing the database. Live workers enabled, 20 requests per case: p95 **230 ms overview / 185 ms list / 146 ms keyword / 207 ms detail**. These are local observations, not a scale guarantee. Reading now uses short independent SQLite snapshots and asset-configuration reads instead of waiting for the background filesystem scan lock. Legacy pages retain their initial-refresh navigation behavior.

Verified database/vault/configuration/program backup: `dist/PersonalAiMemoryOs-0.6.6/backups/upgrade-20261115-040803-0cd0ebef`. External completion ledger and organized mirror copied and hash-verified: `dist/PersonalAiMemoryOs-0.6.6/backups/reading-external-20261115-040742-2cf22055`. All 1903 original files and 1892 mirror files retained their bytes. Formal checks preserved 578 Sources, 580 Knowledge, 702 model-call rows and prior accounting, OpenAI defaults, the 30-yuan monthly budget, hourly sync and 580 published RAG notes. **Zero new model calls**. Installed UI/API/performance evidence: `.cache/reading-delivery/formal-ui.json`, `formal-verification.json`, `live-performance.json` and `delivery.json`.

Final clean bundle: `.cache/desktop-build/e47a093b825f4fcaa500332557dd10ce/dist/PersonalAiMemoryOs`; source fingerprint `110f838fd175bcfad2177529ae2f6966359bb1107d533e6251ba6554d6d91451`. ZIP SHA-256 `eed1887d5d37db3ace1857ab8e47993772ee9626dec4c15ec81e7fc9e71fe963`; EXE SHA-256 `9d67b4257d04cff72bf3654d459b0ad2c203995e948edf983ee688a564a1088d`. No migration, new runtime dependency, framework replacement, OS restart or remote push. Earlier checkpoints below are retained history.

## Reading bookshelf — earlier implementation checkpoint (2026-11-15)

Source version **0.12.0 / schema 0008**. Approved scope: already organized Zhihu favorites, existing summaries retained, no topic synthesis or paid regeneration. Read-only API and modular bookshelf UI are implemented. Focused backend checks: 70 passed; web/UI checks: 46 passed; 53 JavaScript modules parsed. Synthetic browser checks cover topics, keyword excerpts, pagination/scroll return, full long documents, original snapshots, keyboard tabs/gallery, narrow screens, sanitization and zero reading writes/external requests. Full regression, real-size read-only timings, frozen acceptance and fixed-installation delivery remain pending at this checkpoint.


## OpenAI default — final delivery (2026-11-14)

Status: **complete, 0.11.0 / schema 0008, delivered in the existing fixed installation**. Active and persisted default profile is `openai-responses` / `gpt-6.1-sol`; collection processing uses the same profile, retains style approval and `initial_complete`, is enabled/unpaused and has a 30-yuan monthly budget. The key was saved through the validated settings service only in the stopped installation's private configuration. The protected AI restart returned 202 and produced a new PID with the saved default active and no pending configuration change. No key appears in public files, reports or command arguments.

Real acceptance passed grounded summary, image reading and literal-citation QA. Conservative validation accounting is **0.457660 yuan** including two initial failure reservations, below the authorized 2-yuan cap. Three generations returned successfully. An explicitly reviewed extra QA request completed the acceptance after the JSON-input format repair; successful requests were not repeated. Formal library and model-call history were not used as test records.

After restart, all old columns/rows in Sources, provenance, Knowledge, note relationships, organization items/jobs/calls match the verified pre-upgrade backup exactly. Counts remain **578 Sources / 580 Knowledge / 578 published collection items / 702 historical calls**; all old price snapshots are null and the initial 7.587728-yuan ledger is unchanged. The one profile-switch audit record is separate from published content. All 1903 original files retain their hashes, every mirror passes content verification, and RAG remains 580 published with zero pending/failed. All seven actual search cases passed with no generation call. Hourly Zhihu synchronization remains enabled.

Verification: **1313 full-suite passes, 3 existing Windows skips, one upstream warning**, `.cache/openai-delivery-regression.log`; subsequent pricing/budget checks **68 passed**, `.cache/openai-reviewed-focused.log`; final schema-0007 compatibility/storage/updater checks **83 passed, one existing skip**, `.cache/openai-upgrade-focused.log`. All 46 ESM modules, offline lock, documentation/release checks passed. Final frozen smoke: `.cache/collection-desktop/ce383fc566754d2790f46c95093af495/report.json`; synthetic browser provider switch: `.cache/collection-browser/7eaee5dd4d134389afaec8116e9e0ffa/report.json`. An isolated old-EXE upgrade passed at `.cache/desktop-upgrade-validation/4ef4bd9484de459eaaab2e7eb3d2b06f/report.json`; the final version-specific fix is additionally covered by the targeted suite and actual formal 0007 upgrade.

Final build: `.cache/desktop-build/59c0b04f1f6b40bba86796aa83ecb80a/report.json`, source fingerprint `6861823fc774124d765cfeff1b098bba34b9fa604c05eb7a8c584bd76667b781`. Fixed path remains `dist/PersonalAiMemoryOs-0.6.6`. Verified database/vault/configuration/program backup: `backups/upgrade-20261114-110828-2234cd43`; external sync ledger and all 1892 mirror files were copied and hash-verified too. Private evidence: `.cache/openai-acceptance/{delivery,configuration,activation,restart,final-verification,real-validation}.json`, `.cache/openai-validation-budget.json`, and the existing collection integrity/search/idempotency reports. No OS reboot, global proxy change, new installation directory or separate Docker API deployment. Local commits only; no new remote push. Earlier checkpoints below describe their respective states and are superseded by this final record.

Post-restart deduplication passed: manual scanning skipped all 578 items and a full-job request returned `no_pending_articles`; during an 89-second automatic-enabled observation, calls, fees, notes, job count, mirror hashes and file modification times stayed identical. No additional generation was triggered. Evidence: `.cache/collection-acceptance/idempotency.json`.

## OpenAI default — earlier implementation checkpoints (2026-11-14)

Source targets **0.11.0 / schema 0008**. The user selected GPT-6.1 Sol for all new generation, a 30-yuan monthly collection budget, and at most 2 yuan for real validation. Added Responses JSON/image contracts and token counting, explicit collection-profile switching with retained style approval and immutable published items, frozen per-request provider prices, and an additive nullable price snapshot migration. Unknown billable OpenAI extensions are rejected. Windows model transport now honors an enabled system proxy even when NO_PROXY is the only proxy environment variable, preserving explicit routes and bypass rules without changing Windows settings.

Full regression: **1313 passed, 3 existing Windows skips, one upstream warning**, `.cache/openai-delivery-regression.log`. Subsequent focused review of pricing options and the verification budget: **68 passed**, `.cache/openai-reviewed-focused.log`. All 46 browser modules, lock, documentation and release checks passed. Synthetic Chromium flow including explicit OpenAI switch and new-item-only generation passed at `.cache/collection-browser/7eaee5dd4d134389afaec8116e9e0ffa/report.json`. A candidate frozen smoke passed; final fixed-install delivery is still pending.

Actual OpenAI permission check returned 200. Two initial generation requests were rejected because JSON-mode validation did not find the contract in input messages; the adapter now places the existing contract in a developer input message. The reviewed validation used **five HTTP generation attempts: two format rejections and three successful generations** covering grounded summary, image reading and literal-citation QA. One additional QA request was explicitly performed after reviewing the format repair; successful requests were not repeated. The original 2-yuan total cap and both uncertain reservations were retained. Conservative validation accounting is **0.457660 yuan**, `.cache/openai-acceptance/real-validation.json`, with a durable private ledger at `.cache/openai-validation-budget.json`. Credentials stayed in memory during these tests; no formal article or note was added. Ordinary verifier invocations still default to four requests and reject an existing ledger instead of silently resuming.

The first attempted formal upgrade was refused before mutation because the pre-upgrade inspector incorrectly required the new price column in schema 0007. Added a version-specific column expectation and explicit 0006/0007 upgrade coverage; missing legacy columns remain rejected. Related storage, updater, migration and OpenAI verification tests: **83 passed, one Windows skip**, `.cache/openai-upgrade-focused.log`. Formal storage remains schema 0007 until the corrected bundle is delivered.

## Collection organization — final delivery (2026-11-14)

Status: **complete and delivered in place, 0.10.0 / schema 0007**. The user approved ten real samples, all 578 articles and automatic processing, with 20 yuan initial / 10 yuan monthly limits. All 578 items are published with summaries, new titles, categories, retained full originals and categorized Markdown mirrors. There are 578 Sources and 580 Knowledge records including the original two notes; the local vector index has 580 published, zero pending/failed. Twelve items use the approved fallback category and remain searchable. One explicitly approved partial-image article excludes uncertain regions from summary evidence and visibly states its limitation. No other article's uncertainty rule was relaxed.

Actual-data verification: all 1903 source files retain their hashes; all legacy business rows remain intact. Every export hash, note version, original-text tail, literal quotation and image byte was checked. All six long documents cover the complete input; all 18 image-centric documents retain expected image/tile records. The mirror has 578 Markdown files and 1314 distinct image assets. Successful requests were not repeated. Final conservative accounting is **7.587728 yuan across 702 request records**, including failed/uncertain reservations. `initial_complete=true`, automatic processing enabled and unpaused; subsequent new content uses the monthly budget while the application runs. Real keyword/semantic/category/tag acceptance passed seven queries with no generation call. Manual rescan skips all 578 and submitting another full job returns `no_pending_articles` without another model call. After the final restart, a 76.5-second automatic-enabled observation retained identical job/call/note counts, fees, export hashes and file modification times; no additional call or note was created. Hourly Zhihu synchronization remains enabled and unpaused.

Verification evidence stays private under `.cache/collection-acceptance/`: `full-verification.json`, `search.json`, `progress.json`, `idempotency.json` and `delivery.json`. Latest complete regression before two scoped performance fixes: **1290 passed, 3 existing Windows symlink skips, one upstream warning**, `.cache/collection-delivery-regression.log`; 46 browser modules and browser flow passed. The refresh optimization skips unchanged FTS writes while preserving file-conflict checks and missing-index recovery. Real search timing then exposed SQLite reordering escaped short-LIKE queries into a full-text rescan for every item; fixing FTS-first join order retains all filters and reduces the isolated real keyword queries to about 0.1 seconds. The final focused suite covers both fixes: **50 passed**, `.cache/collection-final-search-tests.log`, including the actual query-plan regression. Frozen-package acceptance passed at `.cache/collection-desktop/7e95722cc11b41b79bb1f8b521815bd2/report.json`. Documentation/release checks passed. The full suite was not rerun for these scoped optimizations.

Final build: `.cache/desktop-build/96b23fd0d1bf4a75867edbcd833cb6f9/report.json`; source fingerprint `14cc28d1695c3718213c3bad39e7ed85eba01f5d7d474f70b5863c7807a6f9cf`. Fixed installation remains `dist/PersonalAiMemoryOs-0.6.6`, upgraded after a normal close and verified backup at `backups/upgrade-20261114-052340-d13d2aab`. Database, vault, configuration and program backup passed verification; the external completion ledger and all 1892 mirror files were also copied and hash-verified after the entire collection completed. Original configuration and legacy data were preserved. Installed search acceptance passed all seven queries (0.063–7.859 seconds in this run, including startup/background activity and semantic retrieval); the isolated 0.1-second result is not a promise for every end-to-end query. Source/documentation commits are local; no push, Windows reboot or independent Docker API upgrade. Existing TASK-004/005 broader real-generation quality gates remain separate.

## Collection organization — earlier checkpoints (2026-11-14)

The paragraphs below retain the sequence of implementation and validation. Their “running”, “pending” and earlier build/count statements describe those checkpoints; the final status above supersedes them.

Partial-image follow-up: the user explicitly allowed one partly unreadable screenshot article to be summarized from clear content with a visible limitation. Added a protected per-item review action bound to the current input hash; it does not relax other items. Uncertain OCR regions are excluded from summary input and published text, while original images and raw cached responses remain available. All-uncertain inputs still fail. Added a review panel, a separate partial-image prompt, and mandatory note/export/search-summary warnings. An explicit global uncertainty flag can fill missing row flags; fully missing flags require explicit correction rather than assumed certainty. Explicit vision retries use a separate schema-repair prompt, whose response is cached for later unpaid continuation. Final regression: **1290 passed, 3 existing Windows skips, one upstream warning**; 46 browser modules, documentation and release checks passed. Browser verification: `.cache/collection-browser/f2cc4fafec174812b028fda45a025d1a/report.json`; frozen verification: `.cache/collection-desktop/7a1f28b3a7e84259b20c0f9dc45ea715/report.json`. Build: `.cache/desktop-build/f55555578faa4659bd2e9914782ced43/report.json`, fingerprint `4c9cb012850e81badc710559ffabeba7ff6aeade861a55228fedb962efb32a40`. Final real completion is being checked.

Current checkpoint: all ten real samples completed with 24 first-attempt requests, conservatively accounted at 0.270712 yuan. The user approved the current style and authorized all 578 articles plus automatic processing, with 20 yuan initial and 10 yuan monthly limits. The full job is running in the fixed installation. Its first three failed responses contained only Markdown/whitespace differences or an overlong literal quotation. Local revalidation now maps formatting-only differences uniquely back to actual source slices and bounds long quotations at complete sentence endings; all three saved responses pass without another HTTP request. A separate continuation action handles failed items without implicitly repeating failed or uncertain requests. Focused validation: 38 tests passed; 45 browser modules, documentation and release checks passed; real Chromium workflow passed (`.cache/collection-browser/f0362ec76b514e3b997dbf6ada7aae45/report.json`). Full publication and final real search verification remain in progress.

Later full-run checkpoint: processing was paused at 418 published articles after a burst of connection failures. The conservative ledger retains all uncertain reservations. Two earlier HTTP 400 responses were traced to screenshots taller than DeepSeek's documented 8192-pixel limit; a third oversized article was found by offline preflight. Pillow 13 is now the one additional runtime dependency, needed for portable image decoding and complete in-memory PNG tiling. Original and exported images stay byte-identical, normal request bytes retain cache compatibility, and all tile coordinates are kept. All 18 image-centric articles passed offline image preparation, with 3 requiring tiles. Three consecutive upstream failures now pause the job. Bounded extra summary points are retained (maximum 12). Focused checks: 44 passed; complete regression: **1286 passed, 3 existing Windows skips, one upstream warning**. Browser workflow passed (`.cache/collection-browser/ffa6ab99529340ce84ac2645de13f950/report.json`), as did frozen validation (`.cache/collection-desktop/169c9bb89070480ea57585ab31f78519/report.json`). Build: `.cache/desktop-build/3bc68ab105cd4276bc6f83dbedb8ca72/report.json`, fingerprint `c3aec7e0ac2454ab93cff807a09f84953153b418578c0052b5f809d974a3c6f2`. A direct search shortcut and collapsed approved samples also passed browser and frozen checks. Full-run completion is still pending; earlier no-new-dependency statements below describe the initial implementation.

Source targets 0.10.0 / schema 0007. Added a separate durable collection pipeline, cached taxonomy/chunk/vision/summary calls, conservative paid-call reservations, sample approval gate, idempotent Source/Knowledge publication, conflict-checked categorized Markdown mirrors, SQLite trigram/short-Chinese search and prefiltered semantic retrieval. Prompts remain separate files; no new runtime dependency. Existing article files remain read-only. Default automatic processing is off; 10 samples must be reviewed before publishing or processing all articles.

Engineering verification passed: **1273 tests, 3 existing Windows skips, one upstream warning**, 45 ESM modules, documentation and release checks. Synthetic browser workflow covers sample approval, full publication without repeat model calls, long inputs, images and short-Chinese search (`.cache/collection-browser/150ba9336f3a4e74bb9547eec335c244/report.json`). Frozen settings/scan/approval-gate/reopen acceptance passed (`.cache/collection-desktop/df4a8c70e11343249b123fcfe52cef21/report.json`). Build: `.cache/desktop-build/4ecf6976873e46639c841fe7ef7a627b/report.json`, source fingerprint `6817380a2e6c443519848a15c1aa16a5f69a6fd36d107d9b0b348fb38bd58f20`. No additional runtime dependencies.

The real read-only preflight found 578 articles, 6 long articles and 18 image-centric articles. Existing Source matches: 571 reusable, 7 new, zero content conflicts. Original-file hashes were saved under `.cache/collection-acceptance/`. Full desktop regression passed (`.cache/desktop-validation/0df47c4e16fc407dbef1359c29e0610b/report.json`), as did old-EXE upgrade after stopping the formal instance (`.cache/desktop-upgrade-validation/6d622f3e54c54998a7419b8c7d70b53a/report.json`). The first upgrade rehearsal passed every migration check but failed its formal-storage hash check while that instance was running; it was repeated in a quiescent state rather than weakening the check.

The fixed installation was upgraded with a verified backup (`backups/upgrade-20261113-181948-b1465472`). All legacy business rows and 1903 original files remain unchanged. The first real sample run made 17 requests, conservatively accounted at 0.171410 yuan: seven summaries passed, three responses needed validation repair. One quoted image OCR as original text; one supplied five literal quotes and an 819-character chunk summary; another mixed two literal quotes with one unsupported quote. The repair keeps at most three exact original quotations, discards unsupported ones, and permits bounded chunk summaries up to 1200 characters without truncation. Text-only results still require literal evidence. A cache-continuation action revalidates saved responses and executes only previously unrequested stages; uncertain calls are never repeated by continuation. Focused repair checks: 35 passed; real Chromium workflow passed (`.cache/collection-browser/a83e741aed174458b62ef2dc1f5a8c4d/report.json`). This was the earlier sample checkpoint; current acceptance is recorded at the start of this section. Older quality gates and previous release records below remain historical.

## Authenticated Zhihu sync — delivered in place (2026-11-14)

Real login exposed the current `CollectionDetailPageItem` markup and asynchronous placeholder cards; both are now covered. A 30-page authenticated preview reports 581 declared entries, 571 existing files, 7 new answers, and 3 entries not returned by the site. Pages 2, 14 and 28 each return 19 entries for their 20-position range. Missing entries are reported only after verifying the complete server pagination chain and every supported content ID; they never enter the completion ledger.

Direct answer-detail navigation was restricted by Zhihu. The collection page already supplies accessible full answer/article bodies for its “read more” action, so these are reused without extra detail requests. One real expanded answer matched all 3466 characters of the received body. The 7 new answers contain no images; this is not evidence of live new-image export. Restricted, incomplete or mismatched bodies are rejected.

Engineering verification: **1242 tests passed, 3 existing Windows permission skips, one upstream warning**; 43 browser modules, documentation and release consistency passed. Build evidence: `.cache/desktop-build/99f108a27cba49a689006f410218fa36/report.json`; actual EXE lifecycle/storage acceptance: `.cache/desktop-validation/b54f169e17d04559910fe801daa6fda3/report.json`. The reproducible `scripts/verify_zhihu_sync_authenticated.py` defaults to preview; its explicit `--sync` option writes new files and verifies a repeated run.

Authenticated EXE acceptance passed: first run created **7** Markdown files and skipped **571**, repeat created **0** and skipped **578**, both with zero failures and 3 unlisted entries. All 1896 original files retained their exact hashes; the folder now holds 578 Markdown files and 1325 images. New files passed the existing Markdown-import contract. Evidence: `.cache/zhihu-authenticated-validation/629c27e57d41489e822b11b4b1dcfd2a/report.json`.

Upgraded the existing `dist/PersonalAiMemoryOs-0.6.6` in place, preserving all database rows and original configuration. Verified database/vault/configuration/program backup: `dist/PersonalAiMemoryOs-0.6.6/backups/upgrade-20261113-172118-ec56b740`; the external completion ledger was additionally copied and hash-verified there. The user's application-owned login profile was copied locally and hash-verified, never packaged or committed. Enabled hourly synchronization in this installation only. The opened fixed EXE completed its automatic startup run with 0 created, 578 skipped, 3 unlisted and no failures. Existing app records remain 571 Sources and 2 Knowledge; no automatic import or model call. Delivery evidence: `.cache/zhihu-authenticated-acceptance/delivery.json` and `formal-verification.json` in the same directory.

Version/schema remain **0.9.0 / 0006** for this local build. Delivered source fingerprint `263d964c0767bc62242cb49798b17217a00ccae24879e514ec73803ad176a060` matches current source; the pristine ZIP excludes personal state. Live acceptance covers these 7 text answers, complete collection traversal and deduplication. New image/article/pin export was not exercised against this account in this batch; image continuation and other content contracts retain engineering-test coverage. No push, OS restart or Docker API redeployment. Earlier sections below describe prior checkpoints, not the current installation state.

## Zhihu incremental export — implementation, authenticated acceptance pending (2026-11-14)

Implemented a separate append-only collection exporter: typed string IDs, adoption of existing Markdown, durable completion history, per-target writer exclusion, staged Markdown/images, interruption recovery and immutable completed files. Added protected settings/task APIs, a settings panel, one browser-owning worker, interactive login, preview, hourly scheduling and graceful shutdown. Playwright/Chromium are included in the candidate desktop bundle; authentication and private exports remain excluded. Existing imports and RAG remain separate, with no model calls.

Final engineering verification: **1217 tests passed, 3 existing Windows permission skips, one upstream warning**; this includes 4 real-Chromium synthetic-page checks. 43 ESM modules, documentation and release-consistency checks passed. Final candidate: `.cache/desktop-build/2aa6520163344b11b21dd20acf7b5803/report.json`. Actual EXE CRUD/import/reopen/move/in-flight-close checks passed at `.cache/desktop-validation/a27ed8e32ac64fe39403293cac8caeb6/report.json`. Packaged settings save and the anonymous login-wall check passed at `.cache/zhihu-desktop-validation/e50a40bce6b94a5c8a6b694a54827e8f/report.json`; this does **not** prove authenticated export.

An earlier EXE lifecycle restart failed because Windows assigned blocked port 6668. The server now reserves exclusive random ports in 49152–65535, with collision-retry coverage; the final complete EXE run passed. Publication also uses a separate staged copy so subsequent staging writes cannot modify an already published file through a hard-link alias. Regression checks cover local edits/removal, missing/corrupt state, image continuation and crash recovery.

The public collection was reachable, but its contents require login. The interactive verification window closed without establishing an authenticated session. The original 571 Markdown files and 1325 images have not been exported again, no formal synchronization has been enabled, and the fixed desktop installation has not been upgraded. Remaining release gates: user login, real pagination and full new-item body/image extraction, repeated-run deduplication against the existing folder, and verified-backup in-place upgrade. Do not mark these gates complete based on synthetic pages or the anonymous login-wall check. Use `scripts/verify_zhihu_sync_desktop.py --bundle <candidate>` for isolated settings acceptance; its explicit `--check-login-wall --collection <URL>` option contacts Zhihu anonymously.

The candidate still reports 0.9.0 and is not a promoted release; the build fingerprint distinguishes it from the installed 0.9.0 desktop. All source work stays in the existing checkout and local commits only.

## v0.9.0 — note-level retrieval and local reranking (2026-10-19)

Delivery and acceptance completed: full final 1186 passed/3 existing skips/one warning; 42 ESM modules; source browser, actual EXE flow/reopen, desktop CRUD/lifecycle regression and opt-in service reuse/protected restart passed. User query 回避型 reads the correct 5704-character note in full. Real DeepSeek: exactly three budgeted calls, fixed-case semantic review passed (10212 input/456 output tokens); no retries and no additional budget remains. Report paths and limitations are in MEMORY.md and docs/maintenance-cn.md. Eight-stage draft quality and broader multi-note/long-note real quality remain separate.

Fixed directory upgraded after verified SQLite/vault/config/resource backup at backups/upgrade-20261018-165107-b2ac3dcd. Preserved all legacy rows and original AI/RAG/key settings, explicitly enabled local rerank, retained embedding fingerprint. Formal health/version/retrieval passed, 571 Sources and 2 Knowledge remain. Pristine ZIP and SHA-256 generated; no Windows restart or Docker API redeployment. New candidate-only search median 104/237ms for synthetic 100/1000-note fixtures versus legacy 708/6520ms; no inference included, no first-index improvement claimed.

Implemented candidate-only reads, optional pinned TEI service, grouped note search, bounded full-note/section reading, new retrieve/answer endpoints and answer-first UI. Existing index/schema/API contracts retained. Local real-BGE/TEI/isolated-Qdrant/Chromium acceptance used mock generation. First regression's missing-field documentation failure was fixed before the final full run.

## Seven Follow-up Maintenance Delivery (2026-10-18)

Application remains **0.8.0 / 0006** with the installed resource fingerprint unchanged. No new EXE/migration/runtime dependency, paid model call, Windows reboot, production write or remote push. Current execution table: [project audit](docs/project-audit-cn.md#execution); repeatable commands: [maintenance manual](docs/maintenance-cn.md).

- NEXT-02/04: full isolated SQLite/vault/configuration restore and SQLite-vector-cache recovery passed; actual clean EXE service reuse/single instance/protected restart passed from tracked scripts. Nonempty frozen templates, interrupted draft and paused-task restoration have a dedicated no-model-resume test. Recovery suite: 13 passed.
- NEXT-01/03: fixed quality corpus/review packet and read-only boot comparison delivered. Same-boot verification remains pending as designed. No paid quality review, physical reboot or actual whole-stack relocation was claimed.
- NEXT-05/07: metadata-only storage inventory, conservative retention rules, explicit stopped-log rotation, offline release consistency, pinned read-only CI and explicit public OSV queries delivered. Inventory deleted nothing; logs were under the 8MiB threshold. OSV returned no advisories for 48 version combinations; scan exclusions and license status are documented.
- NEXT-06: real local six-note/ten-query evaluation measured Recall@5=1/MRR@5=1. Independent synthetic 100/1000-note Qdrant/SQLite baseline completed; 1000-note first indexing 972.70s and median search 6.55s identify a performance follow-up. No 10,000-note performance or general answer-quality claim. Capacity report: .cache/capacity-baseline/466c80ace32e4ea68c244f95ea97fcfd/report.json. Separate cached-vector storage measurement distinguishes logical file length from Linux allocated blocks, with no source mutation or model request.
- Unified non-paid checks passed: **1,163 tests / 3 Windows skips / 1 existing Starlette-HTTPX warning**, 42 ESM modules, lock/docs/release checks. Later focused additions also passed, including resource-ownership refusal and cache-free/private-config-free documentation validation. Full report .cache/project-check/report.json; this number describes that full run, not a fabricated rerun after each small tool addition.
- All temporary benchmark containers/volumes and isolated desktop processes were released. Shared Ollama/Qdrant were left running, test collections removed only after ownership checks, and private/formal installation data were not deployed or restored. Reports and synthetic SQLite remain under .cache for review.


## NEXT-01/03 quality and cold-boot preparation (2026-10-18)

- Added a tracked six-note/ten-query Chinese corpus and a zero-call human-review packet generator. Three draft-analysis cases and four cited-QA review cases remain not_run; no paid budget was consumed and no real generation-quality gate is marked complete. Packet: .cache/quality-review/589aa2da510e4a28bbadfff8cf02291b/.
- Added read-only Windows boot evidence and comparison. Baseline .cache/cold-boot/5c789d7e30cb48ec8dd95e47804faccf/report.json records existing services and the desktop being closed/unavailable; subsequent same-boot verification correctly returned pending. The user explicitly forbids reboot. No reboot, service stop or formal configuration change.
- Desktop-service/cold-boot focused suite: 32 passed. Added moved relative-project binding and missing-resource rejection tests; physical cold boot and real entire-stack relocation remain pending, distinct from these path-contract tests.


## NEXT-02 isolated full restore drill (2026-10-18)

- Added strict backup/configuration manifest verification and new-directory restoration support, with 12 tests passed. Reject incomplete, tampered, duplicate, traversal/device-path and unlisted-vault inputs before publishing a copy. SQLite connections are explicitly closed before Windows directory rename.
- Real local BGE-M3/Qdrant drill passed: .cache/recovery-validation/08b3e7c22a0745c8a213ff7b4b6fda8d/report.json. All database rows, multi-source relationships, full vault and configuration bytes retained before startup; AI/RAG-off first boot used no model call. The isolated original stayed stopped while its restored owner recovered lost Qdrant data using SQLite vectors with zero re-embedding for recovery; the confirming query alone used local Embedding. No paid generation, formal data changes or shared collection changes. Qdrant snapshot restoration is not claimed.


## NEXT-04 reproducible checks (2026-10-18)

- Public documentation checker: 15 manuals, 198 links, 7 JSON and 9 YAML examples passed; three focused checker tests passed.
- Public EXE local-service verifier passed against the existing clean bundle: .cache/desktop-local-startup/a6e50841787f4de48aa89699212883a4/report.json. It verified isolated startup, same-directory single instance, guarded restart, retained configuration, released ports, zero model calls and unchanged shared service/storage ownership. No Windows reboot.
- Added unified offline/non-paid check entry and read-only GitHub CI definition. Full unified run follows the remaining maintenance units; remote CI has not executed.


## Project Documentation Review and Follow-ups (2026-10-18)

Scope: documentation only, based on source revision `fc0d505` and existing verification records. Inventoried 350 tracked files, then reviewed main/API/model/service/desktop/vector/web, tests, scripts, build/configuration and documentation boundaries. No application/runtime configuration, business data, model weights or distribution was modified; no service or paid model was run. The 1,135-test result below remains previous executed evidence, not a test rerun for this review.

Completed: current `SPEC.md`; current architecture and 16-application-table/schema-0006 database summaries; request-aware startup prompt; historical structure labeling; source/desktop/old-Docker instance matrix; explicit single-worker/storage boundaries; complete restoration checklist and maintainer verification matrix. Added [docs/project-audit-cn.md](docs/project-audit-cn.md) with evidence and completion criteria, and linked it from the manuals and engineering rules. Older records remain historical.

Registered pending work in `ROADMAP.md` as NEXT-01 through NEXT-07: real generation/answer quality, full isolated restoration, physical cold boot/local-stack relocation, version-controlled verification entry points, log/artifact retention, retrieval/capacity baselines, and release/dependency/licensing decisions. No task is marked implemented merely by being listed. Existing pagination/Prompt/draft/backup/cache-recovery/upgrade features were checked before proposing gaps, to avoid duplicating completed work. TASK-004/005 quality status and budgets are unchanged.

Validation for this documentation unit: **14 Markdown documents and 195 local links/anchors** passed, including directory targets; 7 JSON/9 YAML examples and the existing Settings/profile field coverage passed. ORM inventory confirmed 16 application tables; historical/current consistency and whitespace were reviewed. Application/build fingerprint and distribution SHA-256 remain unchanged. Detailed local check results remain in `.cache/project-audit/`; no private configuration is loaded and the full application suite was not re-run. Public documentation is committed locally after checks, with no remote push.

## Desktop Automatic Local RAG Preparation (2026-10-18)

Status: complete and delivered in place, retaining application `0.8.0`, schema `0006`. Double-clicking the original desktop now prepares the configured local services without a separate PowerShell step. No new dependency or schema change; model weights and Docker remain external.

- Add modular opt-in configuration/runner and host-process environment helpers. Strict bounded JSON, portable-path/link checks, exact local endpoint matching, a fixed bundled script, absolute system PowerShell and argument lists prevent treating configuration as an arbitrary shell command. Run after taking the single-instance lock, before backend start. Strip application secrets/bundled library paths from helper environment, restore Windows DLL search around spawn and merge proxy bypass into the desktop itself.
- Package only the disabled JSON example and public startup script; exclude private startup JSON. Include both resources in the build fingerprint/manifest, and pass `-ProjectRoot` explicitly so bundled resources cannot accidentally select `_internal` for model storage. Check ownership after a fresh Ollama bind before writing its service record. Services are reused, not killed. Failure/timeout offers Chinese basic-management fallback with RAG disabled for this launch and no persisted switch change; no automatic pull/model call/API redeployment.
- Full regression **1,135 passed, 3 Windows symlink skips, 1 existing warning**, 69.97s, `.cache/desktop-local-startup-tests.log`. The 31 new tests cover zero-side-effect opt-out, strict configuration, local/remote endpoints, unsafe paths, Chinese/spaced arguments, credentials/environment, timeout without termination, DLL restoration and launch-only fallback. Independent read-only review passed. PowerShell syntax/manual explicit-root service reuse passed.
- Final real EXE management/import/Markdown/relocation/unsaved-close/drained-call regression passed: `.cache/desktop-validation/c76f81c9383b4a64b8c81445923b22d4/report.json`. Dedicated automatic-preparation flow passed: `.cache/desktop-local-startup/1e9a3f14e21c4a32aade5980a6404cd5/report.json`. It uses a Chinese/spaced isolated portable copy, real existing Ollama/Qdrant, system proxy enabled, PATH limited to System32 plus Docker, and no input proxy exceptions. Probe success proves parent-process loopback bypass; duplicate double-click reuses the same instance, invalid restart token returns403, protected RAG restart hands over to a new PID and releases old ports, saved config survives and no page error occurs. Model counters stayed 51→51; shared service/container/collection identity and formal storage remain unchanged. The owned isolated collection was safely removed. This verifies reuse and restart, not a physical Windows cold-boot test.
- Closed the original desktop normally, verified data/configuration backup `dist/PersonalAiMemoryOs-0.6.6/backups/upgrade-20261017-162717-811af92d/`, and used the existing resource updater on the same installation. Added only its personal startup JSON (`enabled:true`, project root `../..`), reopened the actual EXE from another working directory with no proxy exceptions supplied and confirmed readiness. Installed audit `.cache/desktop-local-startup-installed/report.json` verifies all 571 Sources/2 Knowledge/3 runs/1 batch plus provenance/templates, original configuration bytes, complete vault hashes and sync baselines, excluding normal observation timestamps; generation/index remain healthy with two published notes. Read-only Qdrant probe passed; no model request occurred. Formal API storage was unchanged and no sample data was added.

Final clean bundle contains 256 files, fingerprint `e1f8f86c114059bedecfe20e2b8ccba771f03a8bbd4c6589e2fa0ffa2d726680`. ZIP `dist/PersonalAiMemoryOs-windows-x64.zip` SHA-256 `a20ce7ba7e358807a9ce616f5c8b1997ae6b85fa8d0e18eed0b8cdd7aba9cd23`; EXE `6ccffca5855bc689c9b121e0b488cd70f7a572df3cd30fa3413cd245b3f59535`. The public changes are committed locally, with runtime configurations, models, backups and reports ignored. TASK-004/005 real generation/answer quality remains separately pending.

## Local Ollama / BGE-M3 RAG Deployment (2026-10-18)

Status: local deployment and real Embedding/retrieval acceptance complete; application `0.8.0`, schema `0006`, no product code/migration/rebuild. TASK-005 full real cited-answer quality and TASK-004's real DeepSeek review remain pending. Zero text-generation calls were made.

- Verified the official Ollama `v0.40.6` Windows AMD64 standalone ZIP (1,471,164,488 bytes), SHA-256 `e359637575302f288d76c0007c408a4be9c7376d59c4f28684d63b232a44b427`, before extraction into ignored `.tools/ollama`. BGE-M3 weights stay in ignored project `.cache/ollama/models`; no global installation/PATH/autostart. Full model revision `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`, F16/566.70M, native 1024 dimensions. RTX 4080 SUPER is used; observed `/api/ps` reports all 689,187,061 model bytes in VRAM, runtime context 4096 (model capability 8192).
- Start hidden Ollama on loopback 11434 and only Compose Qdrant `v1.19.2` on loopback 6333, named volume `personalaimemoryos_qdrant-storage`. The new startup script validates owned PID/executable/model-directory before reuse and does not pull models, call a provider, stop other listeners or recreate the formal API. First/repeated execution reused the same PID. Public download initially failed without the existing Windows HTTPS proxy; using that proxy completed the official download. Conversely, runtime HTTPX inherited the system proxy for loopback, returning 502; preserved user `NO_PROXY` exceptions plus a normal drained close/reopen resolved both desktop probes.
- Added three modular real-local acceptance scripts and 16 safety tests. Tests passed with one pre-existing Starlette/HTTPX warning. Full process acceptance exited 0: `.cache/local-rag-validation/47027502d6f94ec29b67b4cdc1869f93/report.json`. Twelve actual local Embedding calls, no generator/external model calls; finite/native dimensions, Chinese keyword/paraphrase expected top1 (0.79809/0.72765/0.66170), Source exclusion, Markdown edit, immediate stale/deleted filtering, restore, unchanged-content rebuild without another Embedding and lost-collection restart recovery from SQLite cache all passed. Owner-matched test collections were removed and formal project hashes match. An initial harness-only nullable-cache audit and cleanup proxy scope issue were fixed/tested; its owned residual collections were also cleaned and the full run repeated successfully.
- Closed the used desktop normally and backed up SQLite/full vault plus all private configuration at `dist/PersonalAiMemoryOs-0.6.6/backups/upgrade-20261017-155556-24c86bbf/`. Used existing same-origin/token/revision-protected APIs to preserve existing profiles, save `local_bge_m3` while RAG off, test Qdrant read-only and make exactly one default Embedding probe (1024 dimensions/10 tokens), then save RAG on. Existing DeepSeek/AI settings and user's 100000 input limit were preserved.
- Two actual protected desktop restarts passed with new PIDs and released old ports. Generation `02d3a77c-bdb8-40da-b488-685a55e1dec3` stayed unchanged: 2 published, 0 pending/failed/excluded, complete index, zero errors. Both current notes were top1 for their respective paraphrased queries before/after restart (0.6390377/0.5597719). Warm request examples were 0.110s/0.094s, not a throughput benchmark or comprehensive quality result. Final private audit `.cache/local-rag-setup/14d5ad580e654dccb7a39b4135b2a0b1/audit-1792253153772117600.json` checks all protected business rows, 571 Sources/2 Knowledge/3 runs/1 batch, provenance/templates, full vault bytes, unchanged AI config, permitted RAG-only `.env` changes, database integrity/foreign keys and unchanged separate project storage. No demonstration records entered the user's library.

Ollama/Qdrant and the existing desktop are left running. After Windows reboot run `scripts/start_local_rag.ps1`, then open the fixed EXE; no model service is bundled in the clean ZIP. DeepSeek cited-answer checks require a separate explicit user submission and human review. Public tooling and documentation are committed locally; runtime configs, weights, databases, private reports and backups remain ignored.

## v0.8.0 Prompt Center, Draft Library, Full Pagination and RAG Setup

Status: engineering complete and delivered in place on 2026-10-17. Version `0.8.0`, schema `0006`. Preserve earlier results below as historical evidence; TASK-004/005 real-model quality gates remain pending.

- Add `knowledge`/`rag_qa` purpose to template records and immutable revisions through `0006`; preserve old templates/revisions and their content hashes, with independent defaults and cross-purpose validation. Freeze chosen RAG template revisions and keep the non-editable citation/evidence output contract.
- Provide an independent Prompt center for both uses, an AI analysis submission/progress page, a draft library and draft detail page. Keep adoption explicit, stale-source checks complete and old draft links/output formats compatible. Preflight visible input lengths rather than returning only a generic over-limit error.
- Standardize all record lists on 10/20/50/100 with direct jump, number navigation, retained filter/return state and lazy body reads. Cover source groups/members, notes/selectors, drafts/runs/batches/items/attempts, templates/revisions, reports, conflicts, sync/index details and provider summaries. Page cached reports/search results without repeating work; preserve the 20-source generation cap.
- Add lightweight summary and paginated diagnostic projections while retaining old default API response contracts. Avoid background polling that reloads full bodies or overwrites editing state.
- Add loopback/token/revision-protected RAG settings with write-only shared-key updates, independent Embedding profiles, next-start RAG/Qdrant configuration and environment/read-only enforcement. Protect AI and Embedding YAML from overwriting one another and preserve unrelated `.env` values through the shared recoverable two-file commit.
- Keep read/save/local preflight zero-call. Expose an explicit read-only Qdrant check and separately confirmed one-attempt Embedding probe; do not create collections, start an index, automatically retry or persist model test data. Readiness, connectivity and real quality are distinct.
- Verify migrations, old data, cross-purpose snapshots, large-list pagination, no repeated paid calls, browser safety, frozen restart, backup and same-directory upgrade with isolated synthetic services. Update the complete Chinese manual/configuration/RAG guides and engineering records; do not broaden real-model budgets or enable RAG without user configuration.

Executed checkpoint: **106 passed, one existing Starlette/HTTPX warning**, 3.95s, `.cache/pytest-v08-rag-settings-04`. This includes next-start state, redaction, shared `.env` preservation, optimistic revision protection against AI/RAG concurrent saves, process-managed keys/fields, Docker-style read-only save rejection, mutual provider-file path protection, two-file replacement rollback, bounded/duplicate JSON rejection, same-origin/shared-token/no-store API guards, explicit Embedding confirmation, one-call/401/no-retry behavior, dimension validation, read-only Qdrant GET, stale-before-call rejection, busy rejection, cancellation lock cleanup and unexpected-error sanitization. All profiles/credentials are synthetic and no formal storage or real model is used.

Final full regression: **1,088 passed, 3 Windows symlink privilege skips, 1 existing Starlette/HTTPX warning**, 100.37s (`.cache/v08/pytest-release.log`). All 42 ESM modules passed syntax checks; the locked dependency set remains 47 packages. The final isolated source/browser workflow passed (`.cache/v08-web/617b2b5e30324693a817cb3f35386f4b/report.json`), including over 100 templates per purpose, all page sizes, lazy bodies, 22 configurations retained across editing pages, independent drafts/adoption, full report downloads, safe citations and 1440/1024/390 layouts. Controlled races verify busy-state pagination boundaries, in-flight page responses, revision response ordering and save feedback after cancelling navigation. Docker Chromium passed the same applicable workflow with read-only configuration and working pagination (`.cache/v08-web-docker/85061d1ad97b4ad2b57d39071e93d286/report.json`). Browser retrieval/answer transport is controlled separately from real-Qdrant HTTP integration below; neither establishes provider quality.

Actual frozen desktop baseline passed management/import/Markdown/relocation/unsaved-close and graceful in-flight-call completion (`.cache/desktop-validation/812fc4356cf142e892181fee73da75ae/report.json`). The final-artifact new-page and restart workflow passed (`.cache/v08-web-frozen/20818149155243ffa425b96fd938ec92/report.json`): full paged management, explicit synthetic Embedding test, RAG later/now choices, protected `scope=rag`, new PID, old port release, single-instance handoff and saved RAG-off configuration active after restart. Source and Docker browser checks and this frozen workflow each use isolated models; paging/restart causes no repeat calls. Owned resources are released, and no paid provider is used.

Final old-EXE `0.7.0/0005 → 0.8.0/0006` in-place upgrade passed (`.cache/desktop-upgrade-validation/7c15136934064799a76db88b4cd784f3/report.json`), preserving every old column/row, custom template/default/revisions, v1 Markdown bytes, configuration and unknown files. The first isolated run rolled back fully when long license directories plus temporary filenames exceeded Windows MAX_PATH (`c76f3b28d724463c944fa2d741bd4dbd`). The updater now reserves short exclusive sibling temporary files for replacement and rollback; 59 related checks/1 Windows skip plus the new full suite and final-artifact upgrade verify the fix. Program backups remain numbered/hash-verified. Initial browser verification timing/download issues are retained in cache; final reports above passed after correcting the harness, with no UI change after its freeze.

Clean delivery: `dist/PersonalAiMemoryOs-windows-x64.zip`, **22,136,791 bytes**, SHA-256 `0674f332119964ecfc1c00e7159498f961ed3da8c1819ae5e1e40b396f58d703`; EXE SHA-256 `c0873f80a4e4dc79f0e78a2699240209f106674710d818e982e082fcd8045e51`. `.cache/v08/artifact-audit.json` verifies 254 pristine files, source fingerprint `29096e6fe03de78bd445d1887370c5b83e5e79a2ecbc3d727d51108a5da35e9f`, all manifest resources, x64 GUI, ZIP CRC, no private/runtime data, unchanged original ZIP and formal project storage.

The existing `dist/PersonalAiMemoryOs-0.6.6/` installation was closed, backed up at `backups/upgrade-20261017-152603-89fb11df/`, upgraded and reopened as `0.8.0`. Its current **571 Sources, 2 Knowledge, 3 runs and 1 batch** were retained. All existing template/revision values, configuration bytes and complete vault bytes match; startup adds only the built-in QA template and refreshes normal synchronization observation timestamps. Existing AI enablement, provider/thinking/key settings and the user's 100,000-character input limit are preserved. RAG stays off; health is ok, both notes are synchronized and issue count is zero (`.cache/v08/installed-audit.json`). Formal Docker/data and other installations are unchanged. Public units are committed locally with no push; real-quality, native production Save As and second-clean-PC boundaries remain pending.

Executed RAG HTTP integration: **local and Docker passed** using `scripts/verify_v08_rag.py --mode all --image memory-os-v08-validation:latest`, report `.cache/v08-rag/f61cb47e7d2044539184c58ed8509154/report.json`. Real isolated Qdrant `v1.19.2` and deterministic local HTTP model fixtures verified automatic indexing, Source exclusion, empty-retrieval zero generation, knowledge/QA purpose rejection before calls, selected template ID/version/content hash, exact system-prompt hash, template edits during an in-flight answer preserving its frozen revision, new-revision use, literal citations, Markdown edits, deletion filtering, restoration and restart persistence. Both databases report schema `0006`, integrity `ok`, one Source/one Knowledge/zero processing runs. Both compose projects have no remaining owned containers/networks/volumes and cleanup error lists are empty. Formal SQLite/full-vault fingerprints match, and real provider calls remain zero. This is API/container engineering evidence, not browser/frozen acceptance or model quality review.

## v0.7.0 Multi-Source Processing, Prompt Management and Portable Continuity

Status: engineering complete and delivered in place on 2026-10-17. Application `0.7.0`, schema `0005`; the historical 0.6.x results below remain dated evidence. Real model quality gates remain pending.

- Implement searchable/paged multi-selection and lazy body preview; retain each selected Source UUID/version across pages. Offer individual and merged analysis with a maximum of 20 unique inputs, and show model/template/output/time settings before submission.
- Persist Prompt templates and immutable revisions. Seed the user's complete eight-stage analysis instructions as the default without replacing existing edits on later startup; retain legacy v1. Freeze the selected template and capability/output wrapper in each run/batch.
- Introduce complete-body JSON v2 and literal per-source quotations while retaining v1 run reading/adoption. Adopt only explicitly reviewed drafts, reject stale input sets and return the original note on repeated adoption.
- Add durable batch/idempotency/item-attempt state, short transactions and per-call shared generation gating. Separate continue from failed/unknown retry; let cancellation finish an in-flight call and stop subsequent dispatch. Pause unfinished work on restart.
- Add ordered `knowledge_sources`, all-source lifecycle constraints and summaries/filters; preserve the first `source_id`. Extend Markdown v2/sync conflicts/journaling and RAG provenance while preserving old v1 files/hash semantics and compatible cached vectors.
- Align AI controls, return to overview after successful note save and offer an explicit dirty-aware desktop restart after settings save. Keep host/environment-managed configuration rules intact and do not restart Docker or a Python service from the desktop-only endpoint.
- Build and verify a manifest-managed in-place resource update of the selected stopped portable directory, with backups/rollback/recovery and explicit schema upgrade. Preserve `.env`, personal model YAML, SQLite, full knowledge vault and unknown files. Keep the fixed existing directory; its old suffix does not identify the running app version. Commit public increments to local Git without private inputs, keys, data or build output.

Executed checkpoint: **184 passed, 1 existing Starlette/HTTPX warning**, 17.89s, for the owned multi-source plus legacy content/Markdown/sync/UI/RAG regression (`.cache/pytest-v070-sources-06`). This group includes 27 new tests: 20-source/ordering/legacy-source/any-source filtering, all-source delete/restore and stale-transaction rollback; v2 import/move/delete/restore, API-managed provenance, conflict resolution and interrupted identity/delete replay; `0004 → 0005` backfill including deleted notes, repeated upgrade with unchanged old file/baseline/version/vector hash; complete search/answer source metadata and source-only reordering without another Embedding call. Inputs and models are isolated/synthetic; no formal database, existing EXE or paid provider was changed by these tests.

Final regression: **1,030 passed, 3 Windows symlink privilege skips, 1 existing Starlette/HTTPX warning**, 114.70s (`.cache/v070-release-verified.log`); 47-package offline lock check and 34 ESM modules passed. The shutdown configuration-resolution race was fixed and tested so confirmation of exit prevents another queued call. Deep dependency backups use short numbered files plus original-path/hash mappings to avoid Windows MAX_PATH; backup/replacement rollback, collision, unknown-file and interrupted-upgrade protections passed.

Browser evidence: eight intercepted Chromium groups (`.cache/v07-ui/7f01b80c0b6c4870a64723f9c44c1f0b/report.json`), six settings regression groups (`.cache/settings-ui/c0de9583ef4e43a79c18e80f424b97c3/report.json`) and real isolated SQLite/API/Chromium individual/merged workflows (`.cache/v07-local/e102e6625bb946dbabfd63c200efeda7/report.json`) passed. These cover cross-page search/selection and the 20-input limit, lazy safe preview, late-response/dirty guards, explicit retry confirmation, multi-source adoption, unchanged/edited saves returning home, Prompt CRUD/default/copy and narrow-screen layouts without page errors or unwanted network requests.

Actual frozen EXE evidence: complete legacy desktop/relocation/import/unsaved-close/in-flight-drain regression passed (`.cache/desktop-validation/173ff48d6e6c4e92972f20bcbd94cb39/report.json`). Final-artifact v0.7 generation/template/settings restart/single-instance workflow passed (`.cache/v07-frozen/934822d6ae35489095dbc5f4ca373adc/report.json`). The blocked-call restart test passed (`.cache/v07-restart-drain/01fb5c0d3e4c43b3b283d2b8bfa45e84/report.json`): successor prepared, old process stayed alive until the first response completed, no second call started, first draft persisted ready, remaining item stayed pending in a paused batch after restart, AI-off configuration applied and all owned ports/processes were released.

Real same-directory old-EXE-to-new-EXE migration passed (`.cache/v07-upgrade/cc366586c1ba4944881524beaf3f8b8d/report.json`): live-instance refusal, verified full backup, all old table columns/rows retained, untouched v1 Markdown/configuration/unknown files, link backfill, schema `0005`, two built-in templates and normal shutdown. The first long-path failure was retained as evidence and fixed before this successful run. No test used private inputs or paid providers.

Delivery: clean ZIP `dist/PersonalAiMemoryOs-windows-x64.zip` is 22,074,802 bytes, SHA-256 `a020718d2c978269340a21edab1cb2fe67e5eaa87a65b21e8bbfc68384225dc8`; EXE SHA-256 `3462c55b3546f499b48218ddd0b2fddf4776b4d13d24341409f19176d5677afd`. `.cache/v070-artifact-audit.json` verifies 243 pristine files, manifest hashes, x64 GUI, ZIP CRC, source fingerprint `0fe96becbb85e95b6886a8346cfacaf70174a3e6bf98e91677eb4f93288a3776`, no personal runtime data and the unchanged original ZIP/project formal storage.

The selected installation `dist/PersonalAiMemoryOs-0.6.6/` was stopped, backed up and upgraded in place. Backup: `backups/upgrade-20261017-135320-96403d78/` inside that installation. All 571 Sources, 1 Knowledge, 2 runs, full vault bytes and configuration bytes were retained. The same-directory EXE was opened and reports `0.7.0`, health `ok`, 2 templates, no batch records and zero synchronization errors (`.cache/v070-installed-audit.json`). Existing AI enabled state was preserved; RAG stays off. Formal project Docker/data and other portable installations were not upgraded. Public units were committed locally; secrets/runtime data/distributions remain ignored and nothing was pushed.

TASK-004/005 real model quality remains pending, with no implication that mock providers or Prompt instructions enable real web research. Second-clean-Windows-PC and production native Save As validation boundaries remain unchanged.

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
