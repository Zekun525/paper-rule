"""Inspect reachable Git history without printing potentially sensitive content."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "github-token": re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "private-key": re.compile(rb"-----BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY-----"),
    "api-key": re.compile(rb"(?i)api[_-]?key\s*[:=]\s*['\"]?sk-[A-Za-z0-9]{12,}"),
}


def git(*args):
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout


def main():
    top = Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve()
    if top != ROOT:
        raise RuntimeError("Refusing to scan an unexpected repository")
    objects = git("rev-list", "--objects", "--all").decode("utf-8", errors="replace").splitlines()
    violations = []
    scanned = 0
    for item in objects:
        sha, _, name = item.partition(" ")
        kind = git("cat-file", "-t", sha).strip()
        if kind not in {b"blob", b"commit", b"tag"}:
            continue
        content = git("cat-file", kind.decode(), sha)
        scanned += 1
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                violations.append((sha[:12], name or kind.decode(), label))
        if kind == b"blob" and Path(name).name in {".env", "id_rsa", "id_ed25519", "hosts.yml"}:
            violations.append((sha[:12], name, "credential-file-name"))
    if violations:
        for sha, name, label in violations:
            print(f"BLOCKED {sha} {name}: {label}")
        raise SystemExit(1)
    print(f"Inspected {scanned} reachable Git objects; no configured secret patterns or credential filenames found.")
    print("This pattern scan does not certify the absence of every type of private material.")


if __name__ == "__main__":
    main()
