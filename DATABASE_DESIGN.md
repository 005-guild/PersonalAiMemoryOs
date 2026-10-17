# DATABASE_DESIGN.md

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
