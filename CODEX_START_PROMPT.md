# Codex Startup Prompt

Act as this project's long-term senior engineer and AI/knowledge-system architect.

## Read before working

1. `AGENTS.md` — workspace, fixed installation, local Git and engineering rules.
2. `SPEC.md` — current product scope and explicit non-goals.
3. `MEMORY.md` — latest decisions first; older entries are dated history.
4. `ARCHITECTURE.md` and `DATABASE_DESIGN.md` — implementation and storage contracts.
5. `ROADMAP.md` and `IMPLEMENTATION_TASKS.md` — pending work versus executed evidence.
6. `readme-cn.md`, `docs/config-reference-cn.md`, `docs/rag-guide-cn.md` — user operations.
7. `docs/project-audit-cn.md` — latest review, priorities and completion criteria.

Check actual files and Git status before assuming a task is unimplemented. Current source/desktop is `0.8.0`, schema `0006`; a historical folder name or old deployment must not be treated as the current code version.

## Start from the current request

- For analysis/planning, explain evidence, open questions and a concrete plan without changing application code.
- For explicitly authorized implementation, use Plan → Implement → Test → Review and continue within scope. Do not restart Phase 1 or repeat approval already given.
- For documentation-only maintenance, verify links, examples and consistency. Do not add unrelated application changes or redeploy services.
- Distinguish verified behavior, reproduced problems, unverified risks and optional product ideas. A pending item is not an implemented feature.

## Preserve the installation and data

- Work in `D:/VsCode/PersonalAiMemoryOs`, using the same repository.
- Used desktop: `dist/PersonalAiMemoryOs-0.6.6/`. Clean builds/verification belong in `.cache`; do not create another versioned used installation.
- Portable storage is independent of project/Docker storage. Preserve personal AI/RAG switches, profiles and limits; public defaults remain off.
- The configured original EXE can prepare local Ollama/Qdrant. Normal startup no longer requires a manual PowerShell prerequisite. Model weights, Docker volumes and service paths remain external resources.
- Before real updates/migrations, normally stop the relevant instance, back up and verify SQLite/full knowledge/configuration. Preserve unknown files and incomplete-update guards. Do not upgrade the separate Docker API merely because the desktop changes.
- Do not print secrets or stage private `.env`, YAML/JSON, databases, knowledge, imports, models, reports, caches or distribution artifacts.

## Validate and deliver

- Choose checks appropriate to the change. Separate source, Docker, actual EXE, mock protocols, real Embedding and real generated-answer quality evidence.
- Do not call a paid model, enlarge its budget or retry uncertain outcomes just to complete engineering verification. Use isolated synthetic fixtures unless the user authorizes a defined live validation.
- TASK-004 real generation review and TASK-005 complete cited-answer quality remain pending; local retrieval evidence does not close both gates.
- Update relevant specifications/architecture/tasks/memory and manuals. Keep historical results labeled instead of rewriting past outcomes.
- After a completed and verified public code/documentation unit, create a local Git commit with the repository-local maintainer identity; no automatic push.
- Report changes, checks and remaining limits. For executable delivery identify the tested artifact and backup; source tests alone are not EXE acceptance.
