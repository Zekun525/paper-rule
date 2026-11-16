import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAD = [re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
       re.compile(r"-----BEGIN (?:OPENSSH|RSA|EC) PRIVATE KEY-----"),
       re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?sk-[A-Za-z0-9]{12,}")]
violations = []
for path in ROOT.rglob("*"):
    if not path.is_file() or any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in path.parts):
        continue
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    for pattern in BAD:
        if pattern.search(content):
            violations.append(str(path.relative_to(ROOT)))
if violations:
    print("Potential secret patterns found:", *sorted(set(violations)), sep="\n")
    sys.exit(1)
print("No configured secret patterns found in tracked-source candidates.")
