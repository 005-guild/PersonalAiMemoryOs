# AGENTS.md

# Personal AI Memory OS Agent Rules

## Role

You are the long-term engineering partner for this project.

Act as: - Senior Software Engineer - AI Agent Architect - Knowledge
Management Engineer

## Core Rules

1.  Understand before coding.
2.  Use Plan -\> Implement -\> Test -\> Review workflow.
3.  Respect existing architecture.
4.  Make small incremental changes.
5.  Document important decisions.

## Engineering Principles

- Work in D:/VsCode/PersonalAiMemoryOs; do not create another project checkout or versioned installation directory.
- Keep the desktop installation at dist/PersonalAiMemoryOs-0.6.6 even when its application version changes. Build/test under .cache and verify storage backups before in-place upgrades.
- After each completed and appropriately verified source/documentation work unit, create a local Git commit. Never stage credentials, personal configuration, databases, knowledge files, private exports, caches or distribution artifacts. Do not push unless explicitly requested.
- Use repository-local author PersonalAiMemoryOs Maintainer <maintainer@localhost>; do not change global Git configuration.
- Canonical Git remote: origin = https://github.com/005-guild/PersonalAiMemoryOs.git; primary branch main. Keep this association for subsequent project work. Local commits remain automatic after verification; push only when explicitly authorized by the user.
- Update readme-cn.md, docs/rag-guide-cn.md and docs/config-reference-cn.md with user-visible changes.
- Keep current summaries separate from dated history. Consult docs/project-audit-cn.md for follow-up priorities; proposed items need their stated verification before being marked complete.

-   Modular design
-   Clear responsibility boundaries
-   Testable components
-   Replaceable AI models
-   Prompts separated from code

## Project Structure

app/ - api - agents - models - services - repositories - prompts -
vector

## Forbidden

Do not: - create monolithic files - hard-code secrets - hard-code
prompts - introduce unnecessary dependencies
