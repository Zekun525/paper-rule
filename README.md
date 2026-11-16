# PaperRule

PaperRule stores approved academic writing guidance separately from public code. It keeps source feedback, scope, proposal revisions, and explicit approval events together so a conversation cannot silently change active rules.

## Quick start

Requires Python 3.12+. From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,ingest]"
paperrule doctor
paperrule init --workspace "$HOME\paperrule-memory"
paperrule app
```

Open `http://127.0.0.1:8765/docs` for the local API. React/Vite sources are in `frontend/`; build them with Node/npm. The local API currently provides the backend interface; frontend development requires the Vite dev server and an API proxy configuration.

```powershell
paperrule paper add --id sample-paper --path . --research-type information-theory --venue TIT --article-type full
paperrule ingest .\examples\feedback.txt --paper sample-paper --reviewer advisor_01
paperrule rules search proof
paperrule install-codex --paper .
```

Create a proposal with `paperrule proposal draft G-001 "Proof clarity" "State the reason for each implication"`, discuss through `/api/proposals/{id}/chat`, inspect its hash, then approve through the API or CLI. Until explicit approval, no active rule is written.

## Privacy

Memory is local and user-selected; the default is under the user data directory. This repository contains only synthetic examples. No provider is enabled by default. Do not put private feedback or paper files in this repository. GitHub publishing is intentionally not automated by the package.

## Current implementation boundary

This release provides a local-first core: JSON-backed private memory, evidence-preserving text/PDF/DOCX import, Pydantic records, explicit proposal approval, content-hash and baseline checks, Git-backed local authority, context filtering, a localhost FastAPI service, CLI basics, a React review surface, deterministic regression cases, and a deterministic offline provider. The UI and API clearly identify offline provider behavior. Optional provider adapters, SQLite/FTS indexing, and browser E2E are tracked as follow-up work; they are never represented as completed semantic validation.

## Development

```powershell
python -m pip install -e ".[dev,ingest]"
pytest -q
python -m ruff check src tests
```

See [中文说明](README.zh-CN.md), [architecture](docs/architecture.md), [privacy and sync](docs/privacy-and-sync.md), [approval workflow](docs/approval-workflow.md), and [release checklist](docs/release-checklist.md).
