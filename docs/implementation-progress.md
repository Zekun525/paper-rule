# Implementation and verification ledger

The full task specification is the acceptance authority. This ledger records verified work, not full product acceptance. Every required feature, T01–T26 scenario, installation gate, privacy gate, and publication deliverable must have direct evidence before the project is declared complete.

## Latest verified checkpoint: 2026-11-17

This is the current local verification record. The older checkpoints below are historical and do not describe the latest test counts. The project remains in development; these results do not establish complete acceptance of the full task specification.

- Full Python suite: **119 passed, 1 skipped in 66.65 seconds**. Ruff passed across source, tests, and scripts. The skipped Windows directory-symlink test could not create a symlink; it is not a passed security assertion.
- Frontend TypeScript checking and Vite production build passed.
- All **5 Playwright browser workflows passed in 31.5 seconds**, against disposable synthetic memory, and the test server shut down successfully. They cover governance, paper scope, settings, structured review import/export, and history restoration.
- History restoration now lists real rule commits, previews affected records, creates a proposal, and opens the approval center. Previewing and creating the proposal do not change active rules. A stale baseline is rejected with HTTP 409.
- Approval displays all records in a batch proposal, including complete before/after contents. The backend diff includes every affected rule. Approval still requires the exact proposal hash.
- Restoration currently concerns rule records. It does not restore all sources, attachments, reviews, or other private-memory files.
- Structured review import/display/export and manuscript-diff checks have passing local tests. Complete checked-rule coverage, report snapshot binding, persisted check output, human confirmation editing, and real semantic-provider evaluation still require work.
- The latest committed local HEAD at this checkpoint is **54efbcf**. The newer work is uncommitted; it has not been published or verified by remote CI. Previous GitHub CI evidence does not validate this working tree.
- The earlier reachable-history scan covered 103 Git objects with no configured findings. It predates the current uncommitted changes and is limited pattern evidence. Fresh publication checks remain required.

## Earlier verification records

### Latest Codex integration checkpoint

- The latest full Python suite passed with 78 passed and 1 skipped in 51.30 seconds. The older counts below describe earlier checkpoints.
- Focused installer and CLI verification passed with 17 passed and 1 skipped. The skipped directory-symlink test could not create symlinks in this Windows environment.
- Documented --paper commands now work for installation, uninstallation, and context retrieval. CLI JSON context includes the same memory commit snapshot as the API.
- Repository and user installation scopes are implemented. User-scope tests inject a synthetic home under the authorized workspace; installation into the real user home was not performed.
- Existing project instructions, BOM, Windows newlines, later appended instructions, custom skills, and edited managed blocks are preserved by the tested installer workflows.
- These results do not complete T17: paper/diff review and structured review import still need implementation and acceptance evidence. Complete T01–T26 acceptance, current remote CI, packaging, and release verification remain outstanding.
- The preceding frontend checkpoint passed three browser workflows. Those browser checks have not been rerun for these subsequent Python integration changes.

- Python 3.12 and editable package installation succeeded after explicit dependency-install authorization.
- 55 Python tests pass, including transactional approval, API decisions, source ingestion, provider safety, FTS indexing, article-type scope, paper-workspace context recalculation, and web-serving isolation.
- Frontend TypeScript checking and Vite production build pass. Two Playwright browser workflows pass against disposable synthetic memory: the complete governance flow and paper-workspace scope recalculation.
- Ruff and the configured secret-pattern scan pass. The scan covers repository candidates while excluding generated dependencies; it is not a substitute for an external historical secret scanner.
- The first historical pattern scan inspected 103 reachable Git objects without finding configured secret patterns or credential filenames. Three additional targeted tests passed: a removed synthetic token remains detectable in Git history, clean history passes, and credential filenames are blocked. The scan reports locations and categories without printing file contents.
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
9. Requirement-by-requirement T01–T26 coverage, frontend typecheck/build, real-browser E2E, security/privacy checks, historical secret scanning, and a clean installation rehearsal.
10. Complete bilingual documentation, screenshots from the running product, dependency locks, CI, and verification that the newest commit is published to the authorized public repository.

## Remaining acceptance work

The following items remain required. Earlier passing tests do not establish their completion:

- Finish settings and diagnostics, private-memory synchronization and conflict review, feedback correction and manual transcription, and the remaining source-import workflows.
- Complete model-assisted proposal preparation, review persistence, semantic regression, and the separately reported real-provider evaluation. Provider adapters and unavailable-provider tests are not proof of these complete workflows.
- Verify bounded and explainable retrieval against the 500-rule scenario, rule relations and unresolved conflicts, and all specified scope conditions.
- Complete the specified CLI equivalents and safe Codex installation/uninstallation; verify that existing user instructions survive both operations.
- Package the production UI and Python application together, provide reproducible dependencies, and rehearse installation and the documented quick start in a clean environment.
- Assess each T01–T26 acceptance scenario against the actual implementation and executed tests. Record missing evidence instead of inferring completion from nearby tests.
- Inspect screenshots from the running product, finish bilingual user documentation, perform the remaining privacy checks, and verify the newest public commit, CI run, and release artifacts.
- Rerun the full checks after the newest changes. The 55-test result and the three targeted historical-scanner tests are separate verification checkpoints.

## Workspace constraints

All project writes, portable tool downloads, dependency caches, temporary files, and synthetic test data must stay inside the user-authorized workspace. Do not modify other computer directories, inspect private papers, or copy account credentials into public examples. Keep real private memory separate from public source code. Never publish real data.
