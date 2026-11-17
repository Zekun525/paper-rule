import importlib.util
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def history_scanner(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "history_privacy_check.py"
    spec = importlib.util.spec_from_file_location("synthetic_history_scanner", script)
    assert spec is not None and spec.loader is not None
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)
    repository = tmp_path / "synthetic-repository"
    repository.mkdir()
    scanner.ROOT = repository

    def git(*args):
        return subprocess.run(
            ["git", "-c", f"safe.directory={repository.as_posix()}",
             "-c", "core.hooksPath=", "-c", "user.name=Synthetic Reviewer",
             "-c", "user.email=synthetic@example.invalid", *args],
            cwd=repository, check=True, capture_output=True, text=True,
        )

    git("init", "-b", "main")
    return scanner, repository, git


def test_deleted_credential_is_still_detected_in_reachable_history(history_scanner, capsys):
    scanner, repository, git = history_scanner
    synthetic_token = "gh" + "p_" + "x" * 30
    evidence = repository / "synthetic-fixture.txt"
    evidence.write_text(synthetic_token, encoding="utf-8")
    git("add", "--", evidence.name)
    git("commit", "--no-gpg-sign", "-m", "Synthetic historical fixture")
    evidence.write_text("Synthetic clean replacement", encoding="utf-8")
    git("add", "--", evidence.name)
    git("commit", "--no-gpg-sign", "-m", "Replace synthetic fixture")
    with pytest.raises(SystemExit) as exc:
        scanner.main()
    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "BLOCKED" in output
    assert "github-token" in output
    assert evidence.name in output
    assert synthetic_token not in output


def test_clean_history_passes_without_printing_file_contents(history_scanner, capsys):
    scanner, repository, git = history_scanner
    evidence = repository / "synthetic-fixture.txt"
    evidence.write_text("Synthetic non-sensitive test material", encoding="utf-8")
    git("add", "--", evidence.name)
    git("commit", "--no-gpg-sign", "-m", "Synthetic clean fixture")
    scanner.main()
    output = capsys.readouterr().out
    assert "no configured secret patterns or credential filenames found" in output
    assert "Synthetic non-sensitive test material" not in output


def test_credential_filename_blocks_even_without_a_recognized_secret(history_scanner, capsys):
    scanner, repository, git = history_scanner
    evidence = repository / ".env"
    evidence.write_text("SYNTHETIC_SETTING=placeholder", encoding="utf-8")
    git("add", "--", evidence.name)
    git("commit", "--no-gpg-sign", "-m", "Synthetic forbidden filename")
    with pytest.raises(SystemExit) as exc:
        scanner.main()
    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "credential-file-name" in output
    assert "SYNTHETIC_SETTING=placeholder" not in output
