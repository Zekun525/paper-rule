# Implementation and verification ledger

The full task specification is the acceptance authority. This ledger records verified work; passing automated checks does not claim semantic accuracy or completion of every optional production integration.

## Verified baseline

- Python 3.12 and editable package installation succeeded after explicit dependency-install authorization.
- 55 Python tests pass, including transactional approval, API decisions, source ingestion, provider safety, FTS indexing, article-type scope, paper-workspace context recalculation, and web-serving isolation.
- Frontend TypeScript checking and Vite production build pass. Two Playwright browser workflows pass against disposable synthetic memory: the complete governance flow and paper-workspace scope recalculation.
- Ruff and the configured secret-pattern scan pass. The scan covers repository candidates while excluding generated dependencies; it is not a substitute for an external historical secret scanner.
- The project already has a public GitHub repository; this worktree contains a newer local change set that still must be pushed and checked remotely.

## Work in progress

- Official portable Node/npm and GitHub CLI downloads were requested into the sibling workspace directory `.tools`. No system-wide tool installation is intended. Inspect the download process result before using these tools.
- Live OpenAI/Codex calls and semantic accuracy are environment-dependent; unavailable providers are preserved as drafts or unavailable regression results.
- Private-memory remote synchronization needs a user-configured private remote; public project publishing never includes private memory.

## Required before claiming delivery

1. Transactional approval, cross-process concurrency protection, immutable approval hashes, idempotency, source validation, and approval-bound Git commits.
2. Immutable source attachments, PDF locations/previews, DOCX OOXML comments/revisions, exemplar and revision-pair import, failure/correction queues.
3. AI adapters with strict schemas, real chat revisions, unavailable-provider handling, read-only Codex invocation, and optional API provider.
4. Scope conditions, publication article types, conflict relations, explainable bounded context, index rebuild and search.
5. Git push/pull queue, non-fast-forward handling, rule version history, single-rule revert and whole-memory restore proposals.
6. Persisted reviews/regressions, report exports, semantic-unavailable results, and validated review import.
7. A built and packaged React application implementing the workbench, source import, proposal discussion/decisions, rule history/revert, paper context, regression reports, and real API operations.
8. All required CLI equivalents, safe Codex installation/uninstallation, diagnostics, schema migrations and portable installation.
9. Meaningful automated coverage, frontend typecheck/build, real-browser E2E, security/privacy checks, and a clean installation rehearsal.
10. Complete bilingual documentation, screenshots from the running product, dependency locks, CI, and verification that the newest commit is published to the authorized public repository.

## Workspace constraints

Project file changes and portable tool downloads stay within the authorized workspace. Dependency installation outside it was separately authorized. Do not inspect or copy private papers or account credentials into public examples. Use project-local test temporary directories and project-external private demo memory within the authorized workspace. Never publish real data.
