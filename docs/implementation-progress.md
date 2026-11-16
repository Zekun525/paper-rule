# Implementation and verification ledger

The full task specification is the acceptance authority. This project is not yet complete or published. Never describe passing smoke tests as full acceptance.

## Verified baseline

- Python 3.12 and editable package installation succeeded after explicit dependency-install authorization.
- Six offline tests passed: basic proposal approval, stale hash/base checks, scope filtering, API smoke, fake-provider labeling, and one deterministic regression case.
- The configured worktree secret-pattern scan passed; this is not a historical Git secret scan.
- Git repository exists locally with no commits or remote yet.

## Work in progress

- Official portable Node/npm and GitHub CLI downloads were requested into the sibling workspace directory `.tools`. No system-wide tool installation is intended. Inspect the download process result before using these tools.
- The standalone sync helper and fake provider are not yet integrated into production flows.
- Ruff has one explicit subprocess-check warning to fix.

## Required before claiming delivery

1. Transactional approval, cross-process concurrency protection, immutable approval hashes, idempotency, source validation, and approval-bound Git commits.
2. Immutable source attachments, PDF locations/previews, DOCX OOXML comments/revisions, exemplar and revision-pair import, failure/correction queues.
3. AI adapters with strict schemas, real chat revisions, unavailable-provider handling, read-only Codex invocation, and optional API provider.
4. Scope conditions, publication article types, conflict relations, explainable bounded context, index rebuild and search.
5. Git push/pull queue, non-fast-forward handling, rule version history, single-rule revert and whole-memory restore proposals.
6. Persisted reviews/regressions, report exports, semantic-unavailable results, and validated review import.
7. A built and packaged React application implementing all required pages and real API operations; no alert-only placeholders.
8. All required CLI equivalents, safe Codex installation/uninstallation, diagnostics, schema migrations and portable installation.
9. Meaningful T01–T26 automated coverage, frontend typecheck/build, real-browser E2E, clean installation, security/privacy checks and historical secret scanning.
10. Complete bilingual documentation, screenshots from the running product, dependency locks, CI, and verified publication to a new public repository in the authorized account.

## Workspace constraints

Project file changes and portable tool downloads stay within the authorized workspace. Dependency installation outside it was separately authorized. Do not inspect or copy private papers or account credentials into public examples. Use project-local test temporary directories and project-external private demo memory within the authorized workspace. Never publish real data.
