# DATABASE_DESIGN.md

## 当前数据设计（2026-10-18，应用 `0.8.0` / Alembic `0006`）

本节汇总实际实现。后面的发布记录和概念模型是历史材料，其中单来源、一套 Prompt 默认值、空库及 RAG 关闭等描述只适用于当时版本。实际 ORM 见 [`app/models/`](app/models/)，完整迁移链见 [`migrations/versions/`](migrations/versions/)；不能据原始概念模型创建未实施的表。

### 当前表与关系

当前有 **16 张应用表**，另有 `alembic_version`。JSON 是 SQLite 列中的持久字段，不代表额外实体表。

| 表 | 当前用途、关系和关键约束 |
| --- | --- |
| `sources` | 原始资料；UUID、标题/作者/URL/正文、来源类型、乐观版本与软删除。相同标题或通用 URL 不具有数据库唯一性 |
| `source_origins` | 可选导入身份，一条 Source 至多一条；`source_id` 为 PK/FK，`(provider, resource_type, external_id)` 唯一。知乎 `answer/article/pin` 互相区分；删除不释放去重身份 |
| `knowledge` | 已保存知识笔记；UUID、Markdown 正文、摘要、分类、JSON 标签/概念、乐观版本和软删除；`source_id` 是可空的首来源兼容字段 |
| `knowledge_sources` | 笔记与 Source 的有序多对多关联；PK `(knowledge_id, source_id)`，`(knowledge_id, position)` 唯一，位置 `0..19`。列表 `source_ids` 的顺序有含义 |
| `sync_vault` | `id=1` 的知识目录身份；token 与目录中的 `.memory-os-vault` 配对，不能单独重建或混用 |
| `sync_states` | 每笔记一条（PK/FK `knowledge_id`）；当前路径、共同内容基线及哈希、原始文件哈希、缺失计时/次数、同步状态和错误 |
| `sync_conflicts` | 笔记一对多冲突；保留共同基线、数据库版本/快照、文件快照/原文/路径/哈希及解决状态 |
| `sync_operations` | 笔记一对多持久文件意图；预期版本/哈希、目标及先前内容、路径、阶段和错误，用于身份回填、写入、删除和恢复 |
| `prompt_templates` | 可编辑模板身份、乐观版本、正文/hash、用途、默认与归档状态；用途限 `knowledge/rag_qa`，每用途至多一个默认 |
| `prompt_revisions` | 不可变修订，PK `(template_id, version)`；冻结当时用途、正文/hash 和输出协议。模板归档不删除历史修订 |
| `processing_runs` | 草稿/生成尝试；首来源 FK 加完整来源快照、Prompt/模型/参数快照、结果与待采纳投影、用量/安全错误、版本/状态；采纳后 `adopted_knowledge_id` 唯一指向原笔记 |
| `processing_batches` | 持久批次；唯一 `client_request_id` 和请求哈希、逐篇/合并方式、有序来源与执行快照、状态/取消意图及乐观版本 |
| `processing_batch_items` | 批次一对多有序明细，`(batch_id, position)` 唯一；保存来源 ID 列表、当前 run FK、历史尝试 IDs/次数及状态。JSON 历史列表不等同于数据库 FK |
| `rag_index_generations` | 独立 collection 的代次/所有权、Embedding profile/非敏感配置指纹、维度和状态；collection 唯一 |
| `rag_note_index_states` | PK `(generation_id, knowledge_id)`；笔记版本/语义哈希、已发布/待处理 job ID、状态与错误。两个 job ID 是逻辑引用，并非 SQL 外键 |
| `rag_index_jobs` | 代次与笔记的任务 FK；冻结版本/内容哈希、笔记快照、分块、成功向量缓存、调用意图、待清理点及阶段/安全错误 |

模型定义分别位于 [`content.py`](app/models/content.py)、[`imports.py`](app/models/imports.py)、[`sync.py`](app/models/sync.py)、[`prompts.py`](app/models/prompts.py)、[`processing.py`](app/models/processing.py)、[`batches.py`](app/models/batches.py) 和 [`rag.py`](app/models/rag.py)。没有独立 `Opinion`、`Experience`、`Decision`、问答历史、附件或分组实体表；观点保留于分析结果/笔记正文，同标题分组是查询投影。

### 写入、删除和历史兼容

[`VersionedRecord`](app/models/base.py) 为 Source/Knowledge 提供整数版本、UTC ISO 时间和 `deleted_at`。模板、草稿和批次有各自版本；同步/索引状态表不是通用内容版本记录。每次 SQLite 连接启用外键约束，见 [`database.py`](app/repositories/database.py)。外键主要使用 `RESTRICT`，**软删除限制另由业务层检查**：任何正常笔记关联的 Source 都不能软删除；恢复笔记须保证所有保留来源有效，或显式调整/清空关联。现有 API 不提供永久物理删除或自动历史清理。

`source_ids` 最多 20 个唯一有效 UUID；`source_id` 保留为首项或 `null`。旧单字段请求仍可设置/清空整个来源关联；同时提交两种字段时必须一致。关联写入与笔记内容在同一事务完成，筛选、删除限制和 RAG 引用覆盖全部来源。JSON 中冻结的历史来源、Prompt、参数不是随当前记录级联更新的实时关系。任一来源变化或删除会阻止旧草稿采纳；重复采纳定位既有笔记，包括已进入回收站的笔记，不创建或自动恢复副本。

Markdown v1 保留单来源协议；多来源笔记用 v2 `source_ids`。已有文件不批量改写，数据库兼容迁移也不替换同步基线或改变文件字节。原始知乎导入 Markdown 与软件知识笔记 frontmatter 是不同协议。同步冲突与未完成文件意图必须随数据库保留，不能因文件当前看似正常而手工删除恢复记录。

### 版本、恢复与索引缓存

| 迁移 | 增量 |
| --- | --- |
| `0001` | Source、Knowledge、知识目录身份与同步记录 |
| `0002` | 持久导入身份 |
| `0003` | 生成运行与草稿 |
| `0004` | 索引代次、笔记发布状态及含向量缓存的任务 |
| `0005` | 多来源、模板/修订、持久批次与运行快照扩展；原首来源回填关联表 |
| `0006` | 模板与修订用途，以及按用途唯一的默认索引；旧模板迁为 `knowledge`，不改正文/版本/hash |

[`0006`](migrations/versions/0006_prompt_purposes.py) 用 SQLite insert/update 触发器约束用途，避免重建被引用的表；ORM 中的用途检查并不意味着生产库经过了 `create_all`。常规 Python/Docker 只检查已迁移 schema，须停止服务、备份后显式 `alembic upgrade head`。便携版允许空库初始化，对已知旧版本先确认并验证备份再迁移；未知/更高版本、缺失知识目录或身份不匹配则拒绝启动，见 [`bootstrap.py`](app/desktop/bootstrap.py)。不要将 `0006` 库直接交给旧版应用；降级优先恢复匹配版本的完整备份。

SQLite 是 RAG 发布依据，Qdrant 仅保存派生点。查询必须同时匹配当前代次、已发布 job、笔记版本和语义哈希，并排除删除/开放冲突/同步错误。缓存保存于 `rag_index_jobs.vectors`，不是单独磁盘缓存数据库；成功替换后清除旧向量，历史任务快照不因此全部删除。内容相同且配置指纹兼容可复用缓存，模型/revision/维度/分块不兼容则显式重建；缺失缓存的重新编码可能产生调用，失败/未知调用不能自动重试。见 [`rag.py`](app/repositories/rag.py) 与 [`rag_search.py`](app/services/rag_search.py)。

### 备份、敏感数据与部署范围

SQLite 备份必须与**完整知识目录（含身份标记）**配套，并停服务避免同步期间跨介质不一致；只复制某篇 Markdown 不足以恢复资料、草稿、模板、冲突和向量缓存。[`storage_backup.py`](app/desktop/storage_backup.py) 使用 SQLite backup API、完整目录复制和 SHA-256 清单。配置由升级/维护流程另行保留；该底层存储备份函数本身只保证数据库和知识目录。跨 SQLite/Markdown/Qdrant 没有分布式事务，恢复依靠基线、意图日志和条件发布。

数据库可能包含原文、未采纳草稿、多次来源快照、冲突双方原文、Prompt 和检索片段；备份/验收报告不能视作已脱敏公开资料。API 密钥不写入业务表，但 `.env`、个人配置及配置恢复日志可能含凭证，须单独保护并排除版本控制。当前没有数据库/备份加密、自动保留期限或安全销毁功能。Qdrant 命名卷是独立的外部服务数据；可用 SQLite 当前缓存重建，是否另做卷备份要单独安排。模型权重、外部项目启动路径也不随便携目录数据库备份自动保存。

当前仅支持一个应用进程/worker 写同一份 SQLite 与知识目录，不能本机服务和 Docker 同时共用；桌面按便携目录互斥不代替跨部署存储锁。近期交付审计中的固定安装已有 571 篇资料/2 篇笔记，已启用本地 BGE-M3 的真实编码和小样本检索；新发行默认关闭 RAG。历史记录中的空表及 RAG-off 是当时验收快照。真实 DeepSeek 生成质量与完整引用问答质量仍待单独验收，不能从索引表发布成功推导回答正确。

## 历史版本记录与原始概念模型

以下保留各发布时点的设计与验收证据，不作为当前运行状态。

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

## 原始概念模型（历史设计，非当前实际表清单）

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
