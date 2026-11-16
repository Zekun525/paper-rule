# Architecture

PaperRule is local-first. Pydantic domain records are stored as JSON in a user-selected memory directory. FastAPI exposes local endpoints, Typer provides command-line operations, and the React client provides a proposal review surface. Approved rules are scoped against a paper profile before context is returned. The storage adapter is intentionally small but is not yet a Git-backed authority or SQLite index.
