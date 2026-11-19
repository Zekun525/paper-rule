"""Classify committed memory paths without touching the filesystem."""

import re
from pathlib import PurePosixPath

from paperrule.persistence.store import MemoryStore, identifier

RULE_FOLDERS = {folder for folder in MemoryStore.folders if folder.startswith("rules/")}
JSON_FOLDERS = {
    folder for folder in MemoryStore.folders if "/" not in folder and folder != "attachments"
} | {"analyses"}
ATTACHMENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,180}")
RESERVED = (
    {"CON", "PRN", "AUX", "NUL", "CLOCK$"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


def _record_name(name: str) -> bool:
    if not name.endswith(".json"):
        return False
    try:
        identifier(name[:-5])
    except ValueError:
        return False
    return True


def classify_memory_path(path: str) -> str:
    """Accept only canonical, Windows-safe paths in the current memory layout."""
    if not isinstance(path, str) or not path:
        raise ValueError("A nonempty committed memory path is required")
    if chr(92) in path or ":" in path or any(ord(character) in range(32) for character in path):
        raise ValueError("Windows separators, streams and control characters are not allowed")
    parsed = PurePosixPath(path)
    parts = parsed.parts
    if (
        not parts or parsed.is_absolute() or str(parsed) != path
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("Committed memory paths must be canonical and relative")
    for part in parts:
        if (
            part.endswith((".", " ")) or part.casefold() == ".git"
            or part.split(".", 1)[0].upper() in RESERVED
        ):
            raise ValueError("Reserved Windows or Git path component")
    if path == "manifest.json":
        return "manifest"
    if path == ".gitignore":
        return "ignore"
    if len(parts) == 2 and parts[0] == "attachments" and ATTACHMENT_NAME.fullmatch(parts[1]):
        return "attachment"
    if (
        len(parts) == 2 and parts[0] in JSON_FOLDERS
        and _record_name(parts[1])
    ):
        return "record"
    if (
        len(parts) == 3 and "/".join(parts[:-1]) in RULE_FOLDERS
        and _record_name(parts[-1])
    ):
        return "record"
    raise ValueError("Unsupported committed memory path")


def validate_memory_entries(entries: list[tuple[str, str, str]]) -> dict[str, str]:
    """Reject links, submodules and names that collide on Windows.

    Each tuple is a Git path, its tree mode, and its object kind. This is a
    committed-tree boundary, not permission to follow or write a filesystem path.
    """
    result = {}
    seen = set()
    for path, mode, kind in entries:
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError("Only regular committed memory blobs are supported")
        category = classify_memory_path(path)
        folded = path.casefold()
        if folded in seen:
            raise ValueError("Committed paths collide on Windows")
        seen.add(folded)
        result[path] = category
    return result
