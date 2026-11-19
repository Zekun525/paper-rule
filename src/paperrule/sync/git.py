from __future__ import annotations

import re
import subprocess
from pathlib import Path


class SyncError(RuntimeError):
    pass

class GitSync:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def run(self, *args: str, check: bool = True) -> str:
        result = subprocess.run(["git", "-c", "core.hooksPath=", *args], cwd=self.root,
                                text=True, encoding="utf-8", errors="replace",
                                capture_output=True, check=False, timeout=30)
        if check and result.returncode:
            raise SyncError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    def read_blob(self, object_id: str, *, max_bytes: int = 2_000_000) -> bytes:
        """Read a bounded Git blob without replacement-decoding its evidence."""
        if not re.fullmatch(r"[0-9a-f]{40}", object_id):
            raise SyncError("Expected a full Git blob object ID")
        if self.run("cat-file", "-t", object_id) != "blob":
            raise SyncError("Expected a Git blob")
        size = int(self.run("cat-file", "-s", object_id))
        if size not in range(max_bytes + 1):
            raise SyncError("Blob exceeds preview size limit")
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=", "cat-file", "blob", object_id],
            cwd=self.root, capture_output=True, check=False, timeout=30,
        )
        if result.returncode or len(result.stdout) != size:
            raise SyncError("Git blob could not be read consistently")
        return result.stdout

    def init(self) -> str:
        if not (self.root / ".git").exists():
            self.run("init", "-b", "main")
        actual = Path(self.run("rev-parse", "--show-toplevel")).resolve()
        if actual != self.root:
            raise SyncError("Memory must be a dedicated Git repository")
        if not self.head():
            self.run("add", "--", "manifest.json", ".gitignore")
            self.commit("Initialize private PaperRule memory")
        return str(actual)

    def head(self) -> str:
        return self.run("rev-parse", "--verify", "HEAD", check=False)

    def commit(self, message: str) -> str:
        self.run("-c", "user.name=PaperRule", "-c", "user.email=paperrule@localhost",
                 "commit", "--no-gpg-sign", "-m", message)
        return self.head()

    def commit_approved(self, message: str = "Approve PaperRule memory change") -> str:
        self.init()
        self.run("add", "-A", "--", ".")
        if self.run("diff", "--cached", "--name-only"):
            return self.commit(message)
        return self.head()

    def status(self) -> dict:
        self.init()
        remotes = self.run("remote").splitlines()
        pending = self.run("rev-list", "--count", "@{upstream}..HEAD", check=False)
        return {"branch": self.run("branch", "--show-current"),
                "commit": self.head(), "dirty": bool(self.run("status", "--porcelain")),
                "remote_configured": "origin" in remotes,
                "pending_commits": int(pending) if pending.isdigit() else None,
                "status": "local" if "origin" not in remotes else "configured"}

    def push(self) -> dict:
        if "origin" not in self.run("remote").splitlines():
            return {"status": "local", "message": "No private remote configured"}
        try:
            self.run("push", "-u", "origin", "HEAD")
            return {"status": "synced", "commit": self.head()}
        except (SyncError, subprocess.TimeoutExpired) as exc:
            conflict = any(word in str(exc).casefold() for word in ("rejected", "non-fast-forward", "fetch first"))
            return {"status": "conflict" if conflict else "pending",
                    "message": "Remote changed; fetch and review differences" if conflict else "Push failed; approved local rules are safe. Retry when connected."}

    def pull(self) -> dict:
        if self.run("status", "--porcelain"):
            return {"status": "conflict", "message": "Uncommitted records exist; approve or back them up before pulling"}
        try:
            self.run("fetch", "origin")
            self.run("merge", "--ff-only", "@{upstream}")
            return {"status": "synced", "commit": self.head()}
        except (SyncError, subprocess.TimeoutExpired):
            return {"status": "conflict", "message": "Fast-forward pull unavailable. Local rules retained; inspect remote differences."}

    def differences(self) -> str:
        return self.run("diff", "HEAD", "@{upstream}", "--", "rules", check=False)

    def validate_sha(self, sha: str) -> str:
        if not re.fullmatch(r"[a-fA-F0-9]{7,40}", sha):
            raise ValueError("Expected a Git commit SHA")
        return self.run("rev-parse", "--verify", sha + "^{commit}")
