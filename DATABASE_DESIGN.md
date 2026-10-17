# DATABASE_DESIGN.md

## v0.8.0: Purpose-Specific Prompt Defaults (`0006`)

Application `0.8.0` explicitly upgrades `0005` to `0006`. Migration, full regression and portable deployment passed; retain historical acceptance below as release-specific evidence.

| Change | Persistence and compatibility |
| --- | --- |
| `prompt_templates.purpose` | Non-null `knowledge` or `rag_qa`, with `knowledge` as the migration/server default |
| `prompt_revisions.purpose` | Same purpose recorded on immutable revisions; old revision content, hash and version are preserved |
| `uq_prompt_default` | Unique partial index on purpose where `is_default=1`; each purpose may have its own default |
| Purpose checks | SQLite insert/update triggers reject unsupported purposes while avoiding a table rebuild and preserving incoming foreign keys |

Existing templates and revisions migrate to `knowledge` without content/version changes. Startup seeds the cited-answer built-in only when its identity is absent and does not replace user edits or another default of the same purpose. Template APIs reject knowledge templates for question answering and answer templates for note analysis. Selecting/archiving defaults operates within one purpose; historical run/batch template snapshots remain self-contained. User-editable answer style does not change the fixed validated citation output schema.

No draft/history duplication, question-history table, Source indexing, content rewrite or Markdown schema change is introduced. Existing drafts continue living in `processing_runs` and batches/items retain their previous lifecycle. The independent draft workspace uses lightweight projections and detail reads over the same records. Paginated synchronization/index diagnostics likewise query existing storage; they do not create new business entities or mutate the index.

Visual RAG configuration stays outside SQLite: personal Embedding YAML and `.env` contain next-start settings and write-only key updates through the shared recoverable file transaction. Neither configuration reads/saves nor explicit connection probes add Knowledge, processing or vector-cache rows. Embedding tests have a separate explicit confirmation, make one request and return only safe dimension/usage metadata. Default RAG remains off; no real-provider quality claim follows from local preflight or a simulated probe.

Ordinary Python/Docker startup continues to require an explicit migrated schema. Portable upgrades require a stopped instance and a verified complete database/vault/configuration backup; the fixed existing installation directory is retained. Full regression: 1,088 passed/3 Windows skips (`.cache/v08/pytest-release.log`). Real old-to-new EXE migration preserved all legacy columns/rows, edited templates/default/revisions and v1 file bytes (`.cache/desktop-upgrade-validation/7c15136934064799a76db88b4cd784f3/report.json`). The actual 571 Sources, 2 notes, 3 runs and 1 batch were verified before/after deployment; startup only adds the missing QA built-in and refreshes normal sync observation timestamps. See `.cache/v08/installed-audit.json` and `IMPLEMENTATION_TASKS.md` for delivery evidence. After QA templates exist, downgrade refuses to delete them automatically; restore a verified matching `0005` backup instead.

Additional local/Docker HTTP acceptance passed with isolated empty storage migrated to `0006`, real Qdrant `v1.19.2`, synthetic models and post-restart SQLite integrity checks. Both modes retain one Source/one Knowledge/zero processing runs while custom RAG template revisions and literal citations remain usable. Evidence `.cache/v08-rag/f61cb47e7d2044539184c58ed8509154/report.json` confirms unchanged formal storage and complete owned-resource cleanup; this does not establish real model quality.

## v0.7.0: Versioned Prompts, Persistent Processing and Multiple Sources (`0005`)

Current implementation: application `0.7.0`, explicit migration `0004 → 0005`, engineering acceptance complete. This section supersedes the single-source-only descriptions in historical release sections without rewriting their recorded results. Ordinary Python/Docker startup still checks the schema rather than migrating it. Portable startup recognizes known old schemas, requires confirmation and a verified database/full-vault backup before upgrading, and rejects unknown or newer structures.

| Table/change | Persistent contract |
| --- | --- |
| `knowledge_sources` | Ordered provenance: composite PK `(knowledge_id, source_id)`, restricted FKs, integer `position`, unique `(knowledge_id, position)`, checked `0 <= position < 20` |
| `knowledge.source_id` | Retained as the first ordered source, or `null`; existing APIs remain compatible while `source_ids` exposes the complete ordered list |
| `prompt_templates` | Optimistically versioned name, description, original content/hash, output schema, default flag, archive time and timestamps; at most one default |
| `prompt_revisions` | Immutable template revisions keyed by `(template_id, version)`; historical runs never depend on the latest editable template |
| `processing_batches` | Unique client request token/hash, individual/merged mode, ordered source snapshots, non-secret profile/prompt/generation snapshots, lifecycle/version/cancellation metadata |
| `processing_batch_items` | Ordered work items with source IDs, status, current run ID, attempt history and safe error; `(batch_id, position)` is unique |
| `processing_runs` additions | Nullable `source_snapshots`, `prompt_snapshot`, `generation_settings`, `finish_reason` and `failure_stage`; old single-source/result records remain readable |

Migration backfills every old non-null Knowledge `source_id` into `knowledge_sources` at position zero, including soft-deleted notes. It does not rewrite Source/Knowledge text, increment content versions, alter old sync baselines/hashes, replace existing Markdown or invalidate vectors merely because provenance storage changed. Independent notes retain no source links. Repeating the migration is safe through Alembic revision tracking.

Content creation/adoption writes Knowledge and all ordered source associations in one transaction. API writes accept up to 20 unique canonical UUIDs; each linked Source must exist and be active. If both legacy `source_id` and `source_ids` are supplied, the legacy field must equal the first item, or `null` for an empty list. An old request containing only `source_id` replaces the association with that single source or clears all links. Version checks cover association changes. Any source in an active note blocks that Source's soft deletion; restoring a deleted note checks every retained source, or accepts an explicitly revised/empty association list.

Markdown v1 keeps the existing single-source projection/hash/rendering contract. Multi-source notes use frontmatter v2 with ordered `source_ids` and a compatible first `source_id`. Existing Markdown cannot reassign source associations; a new unidentified v2 file may specify them, and normal UUID-backfill journaling applies. Conflict snapshots and filesystem-operation recovery retain all source IDs. Removing extra associations may return the exported representation to v1; format metadata alone does not count as a business edit.

Processing output v1 remains the historical eight-field knowledge schema. V2 carries `title`, `summary`, `category`, `tags`, `concepts`, the full Markdown `body`, and `source_quotes`; selected-source quotations must match exact input text and cover every selected Source. The complete body is adopted, not regenerated from a short outline. Drafts still create no Knowledge until explicit adoption. Merged runs retain every input version; any changed/deleted input prevents stale adoption. Repeated adoption returns the existing note.

Batch submission freezes its ordered inputs and non-secret execution configuration. `client_request_id` plus request hash prevents an unknown submission response from duplicating the same work. Batch states are `pending/running/paused/completed/cancelling/cancelled`; item states are `pending/running/ready/failed/interrupted/cancelled`. Call intent/run identity is durable before the remote request. Restart preserves results and pauses unfinished work; continuing pending items and retrying failed/unknown attempts are separate explicit actions. Cancellation stops later calls and lets an already dispatched call finish. Safe available usage/finish-stage diagnostics may survive failures; raw upstream responses and credentials are not stored.

RAG remains Knowledge-only. Search hits and answer citations include ordered `source_ids`/`sources`, with legacy first-source fields preserved. Source IDs, paths and source metadata are outside the semantic text hash: changing only provenance re-publishes the current Knowledge version using compatible cached vectors. SQLite remains authoritative for freshness and visibility.

Validation: final full suite **1,030 passed**, 3 Windows skips and 1 existing warning (`.cache/v070-release-verified.log`). Multi-source regression includes `0004 → 0005` backfill, unchanged v1 files/baselines/versions and unchanged semantic hashes. Actual old/new EXEs passed same-directory migration and verified backups (`.cache/v07-upgrade/cc366586c1ba4944881524beaf3f8b8d/report.json`); selected portable deployment preserved every old row and full vault/configuration bytes (`.cache/v070-installed-audit.json`). Real-provider quality remains pending.

## v0.6.3 Import Compatibility

Schema remains `0004`. Markdown folder import reuses Source and SourceOrigin with per-source transactions; no import-job or attachment table is added. SourceOrigin's existing string `resource_type` also accepts `pin`, alongside `answer` and `article`, under the same `(provider, resource_type, external_id)` uniqueness constraint. The imported export ID is external identity only. Original publication/collection/download dates do not replace database creation/update times. Imports create no Knowledge or vector entries.

## v0.5 Index State (revision `0004`)

Explicit migration `0003 → 0004` adds durable index-generation, per-note publication and task records; it preserves content, import identities, processing drafts and synchronization data. Startup checks the revision and never auto-migrates. Stop services and back up SQLite plus the entire paired vault before upgrading.

- A generation identifies its Embedding profile, non-secret semantic configuration fingerprint, output dimension, chunking version and separately owned Qdrant collection. Incompatible model/revision/dimension/chunking changes require an explicit new generation.
- A per-note state binds Knowledge UUID/version/content hash to the currently published chunk manifest and generation. It tracks pending/excluded/error state. Deleted, conflicted, synchronization-error and stale content is filtered from search even before remote cleanup completes.
- Durable tasks retain observed content, current stage, call intent, normalized error and successful vectors/chunks needed for recovery. Vectors are committed to SQLite before upload. Unknown or interrupted Embedding requests do not automatically repeat; explicit retry is required. Qdrant replay from saved vectors is idempotent and does not incur another Embedding request.

These records are stored respectively in `rag_index_generations`, `rag_note_index_states` and `rag_index_jobs`.

Qdrant is a derived retrieval store using Cosine distance and deterministic UUID point IDs, with an ownership marker in collection metadata. Uploads precede conditional SQLite publication; old cache/points are cleaned after replacement. Search accepts only points matching the SQLite publication and current eligible Knowledge. A missing or faulty index is unavailable; partial coverage is reported explicitly rather than presented as an empty knowledge base. A rebuilt collection can use current cached vectors after Qdrant storage loss. The SQLite database and full Markdown vault remain the required paired backup; Qdrant's Docker named volume is disposable derived storage.

No question history, Source vectorization, draft vectorization, new business note or Opinion table is introduced. Keys, authentication headers and raw upstream failures are not stored in index rows. Real-provider relevance and answer quality remain pending until separate credentials/budget and human review are supplied.

Actual v0.5 migration, full regression and real-Qdrant local/Docker engineering acceptance passed on 2026-10-17 (609 tests passed, two Windows privilege skips, one existing warning). Formal storage was backed up while stopped to `data/backups/v0.4-before-v0.5-20261017-cf037130`, every manifest entry verified, then explicitly upgraded `0003 → 0004`. SQLite integrity is `ok`; all four existing business/import/run tables and all three RAG tables remain empty, and full vault hashes are unchanged. Formal AI/RAG are disabled and no real model request was made. Evidence: `.cache/v05-deployment-result.json`; isolated workflow report: `.cache/v05-validation/0e022cb9aae0471c8ac2b0efe3c98f32/report.json`. These are engineering results, not real retrieval/answer quality acceptance.

# Core Data Model

## Source

Original information.

Fields: - id - source_type - title - author - url - content

## Knowledge

AI understanding.

Fields: - source_id - summary - category - tags - concepts

## Opinion

Viewpoints.

Fields: - knowledge_id - statement - comment

## Experience

Personal lessons.

## Decision

Important choices and results.

## v0.2 Implemented Storage Model (2026-10-16)

The sections above are the original conceptual model. This release implements Source and Knowledge only; Opinion, Experience and Decision remain future work.

| Table | Purpose and important fields |
|---|---|
| `sources` | UUID `id`, `source_type`, `title`, nullable `author`/`url`, original `content` |
| `knowledge` | UUID `id`, nullable indexed `source_id`, `title`, Markdown `body`, `summary`, nullable `category`, JSON `tags`/`concepts` |
| `sync_vault` | Singleton vault UUID paired with `.memory-os-vault` |
| `sync_states` | One row per note: relative file path, shared projection/hash, observed file hash, state, missing-file timing and last error |
| `sync_conflicts` | Baseline, database snapshot/version, file snapshot/raw content/path/hash, reason and resolution state |
| `sync_operations` | Recoverable filesystem intention, expected version/hash, target/previous content, target snapshot and completion state |
| `alembic_version` | Applied explicit schema revision |

Source and Knowledge share integer `version`, UTC `created_at`/`updated_at`, and nullable `deleted_at`. IDs are UUID strings. Optimistic updates match the expected revision; soft delete and restore also participate in version checks. `tags` and `concepts` are arrays, not comma-separated strings.

One Source has zero or more Knowledge notes; independent Knowledge uses `source_id = null`. Foreign keys restrict physical parent deletion, and application rules require an active source for a linked active note. A Source with active notes cannot be soft-deleted. Restore can provide an updated or null source link when the original parent is no longer active. No physical-delete endpoint is provided.

SQLite and Markdown are both editable. Successful synchronization stores their common note projection as a baseline. One-sided changes propagate; divergent changes produce a durable conflict retaining both sides. A restored or moved file is matched by UUID rather than filename. Unknown/duplicate UUIDs and illegal existing-file source reassignment produce errors without importing ambiguous identity.

Markdown uses YAML frontmatter with `schema_version: 1`, required nonempty `title`, optional `id` for new files, optional `source_id`, `summary`, `category`, `tags`, and `concepts`. The content below frontmatter is `body`. Existing IDs are preserved; new files receive an ID written back to disk. API-only version/timestamp/deletion state is not editable frontmatter.

Alembic revision `0001` in `0001_knowledge_storage.py` initializes this schema. Operators run `alembic upgrade head`; startup checks revision readiness and never substitutes `create_all` for migration management. Future PostgreSQL support requires schema/data migration and compatibility checks beyond changing a URL.

## v0.3 Persistent Source Identity

Alembic revision `0002` adds `source_origins` without rewriting existing Source, Knowledge or synchronization data:

| Column | Meaning |
|---|---|
| `source_id` | Primary key and restricted foreign key to `sources.id` |
| `provider` | Import provider, currently `zhihu` |
| `resource_type` | `answer` or `article` |
| `external_id` | Positive resource ID extracted from the supported URL |
| `imported_at` | UTC timestamp for the initial import |

The unique `(provider, resource_type, external_id)` constraint persists deduplication across restarts and concurrent import attempts. Each new Source and its origin are committed in one per-item transaction. A failed origin insertion rolls back that Source, so uniqueness races do not leave orphan duplicates.

Origin identity is independent of editable Source title/author/content/URL. Existing identities, including soft-deleted Sources, are skipped without overwrite or restore; only title/author/content differences are reported. Imported answers are keyed by answer ID even if a later URL uses a different question ID. Legacy Sources lacking origins are matched conservatively by normalized URL identity and only skipped; ambiguous multiple matches are reported, and no origin is retroactively assigned.

Dry-run uses read-only lookups and an in-memory same-batch simulation. Valid/invalid outcomes are reported independently; earlier successful per-item transactions remain committed if a later database failure produces a 503 partial report. Import does not create Knowledge, Markdown or sync operations. Operators must explicitly migrate to `0002`; isolated local/Docker migration and runtime verification passed, including identity persistence across container recreation.

The formal database was explicitly upgraded from `0001` to `0002` on 2026-10-17 (Asia/Shanghai), after backing up the database and entire vault to `data/backups/v0.2-before-v0.3-20261017-3815b32d` with a SHA-256 manifest.

Final verification confirmed revision `0002`, `PRAGMA integrity_check = ok` and zero rows in `sources`, `knowledge` and `source_origins`. The vault hashes remained identical to pre-upgrade values and all backup-manifest hashes verified.

## v0.4 Durable Processing Drafts

Alembic revision `0003` adds `processing_runs` without rewriting existing content, origins or synchronization state:

| Fields | Purpose |
|---|---|
| `id`, `version`, timestamps | UUID, optimistic version, lifecycle timing |
| `source_id`, `source_version`, `source_snapshot`, `input_hash` | Restricted source FK, original version and immutable input provenance |
| `profile_id`, `protocol`, `model`, `config_fingerprint` | Selected model configuration without storing secrets |
| `prompt_version`, `prompt_hash`, `output_schema_version` | Reproducible prompt/output contract identifiers |
| `status`, `error_code`, `usage` | Running/ready/failed/interrupted/adopted state, safe error and available normalized token usage |
| `result`, `proposal` | Validated structured output and frozen ordinary Knowledge fields awaiting adoption |
| `adopted_knowledge_id` | Nullable unique restricted FK to the one adopted note |

Each run belongs to one Source; a Source can have many runs. Source soft deletion preserves existing drafts, but a changed version or deleted Source blocks adoption. The snapshot contains original text as expected application data; keys, raw upstream HTTP responses and arbitrary error bodies are not persisted.

The lifecycle is `running → ready/failed/interrupted`, then `ready → adopted`. Source snapshots/run creation and completion each use short transactions around the remote call. Startup converts leftover running rows to interrupted; there is no automatic paid retry. First adoption creates Knowledge and updates the run in a single transaction; conditional versions plus the shared mutation lock prevent duplicate creation. Repeated adoption returns the linked note, including soft-deleted notes, without restoration.

Generation and previews do not alter Knowledge, sync operations or Markdown. After adoption the existing operation/baseline machinery exports the note. The `opinions` array remains in the run result and is rendered in the body; no Opinion table is introduced. Explicitly upgrade `0002 → 0003` after stopping and backing up the paired database/vault.

Actual v0.4 local and Docker migration/runtime acceptance passed on 2026-10-17. The formal service was stopped, its database/full vault were backed up to `data/backups/v0.3-before-v0.4-20261017-c80de831` with all SHA-256 manifest entries verified, then explicitly migrated `0002 → 0003`. Final SQLite integrity was `ok`, Source/Knowledge/origin/run row counts remained zero and vault-file hashes were unchanged. AI remains disabled until real configuration; no draft/sample was created in formal storage.
