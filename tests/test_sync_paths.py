import pytest

from paperrule.sync.paths import classify_memory_path, validate_memory_entries


@pytest.mark.parametrize(("path", "category"), [
    ("manifest.json", "manifest"),
    (".gitignore", "ignore"),
    ("rules/global/R-SYNTHETIC.json", "record"),
    ("rules/research-type/R-SYNTHETIC.json", "record"),
    ("rules/publication/R-SYNTHETIC.json", "record"),
    ("rules/paper/R-SYNTHETIC.json", "record"),
    ("rules/section-task/R-SYNTHETIC.json", "record"),
    ("feedback/F-SYNTHETIC.json", "record"),
    ("sources/SRC-SYNTHETIC.json", "record"),
    ("history/R-SYNTHETIC-v2.json", "record"),
    ("proposals/P-SYNTHETIC.json", "record"),
    ("decisions/A-SYNTHETIC.json", "record"),
    ("snapshots/A-SYNTHETIC.json", "record"),
    ("tasks/P-SYNTHETIC.json", "record"),
    ("analyses/ANALYSIS-SYNTHETIC.json", "record"),
    ("runs/RUN-SYNTHETIC.json", "record"),
    ("papers/SYNTHETIC.json", "record"),
    ("attachments/SRC-SYNTHETIC.pdf", "attachment"),
    ("attachments/SRC-SYNTHETIC.docx", "attachment"),
])
def test_current_memory_layout_has_explicit_safe_categories(path, category):
    assert classify_memory_path(path) == category


@pytest.mark.parametrize("path", [
    "", ".", "..", "../synthetic.json", "/synthetic.json",
    "//synthetic-server/share/file.json", "D:/synthetic/file.json",
    "attachments" + chr(92) + "synthetic.txt",
    "sources/F-SYNTHETIC.json:stream", "sources//F-SYNTHETIC.json",
    "./sources/F-SYNTHETIC.json", "sources/../F-SYNTHETIC.json",
    "sources/F-SYNTHETIC.json/", "sources/F-SYNTHETIC.json.",
    "sources/F-SYNTHETIC.json ", "attachments/CON.txt", "attachments/NUL.pdf",
    "attachments/COM1.txt", "attachments/LPT9.txt", "attachments/aux.docx",
    "attachments/PRN", ".git/config", "attachments/.git/config",
    ".gitattributes", ".env", "cache/synthetic.json", "unknown/synthetic.json",
    "sources/nested/F-SYNTHETIC.json", "rules/unknown/R-SYNTHETIC.json",
    "rules/global/R-SYNTHETIC.txt", "sources/" + chr(10) + "synthetic.json",
])
def test_unsafe_or_unsupported_git_names_are_rejected_without_filesystem_access(path):
    with pytest.raises(ValueError):
        classify_memory_path(path)


@pytest.mark.parametrize(("mode", "kind"), [
    ("120000", "blob"), ("160000", "commit"), ("040000", "tree"),
])
def test_links_and_submodules_cannot_be_treated_as_regular_memory_files(mode, kind):
    with pytest.raises(ValueError, match="regular"):
        validate_memory_entries([("sources/SRC-SYNTHETIC.json", mode, kind)])


@pytest.mark.parametrize("second", [
    "sources/SRC-SYNTHETIC.json", "sources/src-synthetic.json",
])
def test_duplicate_and_case_colliding_names_are_rejected(second):
    with pytest.raises(ValueError, match="collide"):
        validate_memory_entries([
            ("sources/SRC-SYNTHETIC.json", "100644", "blob"),
            (second, "100644", "blob"),
        ])


def test_distinct_record_directories_remain_distinct_on_windows():
    assert validate_memory_entries([
        ("sources/SYNTHETIC.json", "100644", "blob"),
        ("feedback/SYNTHETIC.json", "100644", "blob"),
    ]) == {
        "sources/SYNTHETIC.json": "record", "feedback/SYNTHETIC.json": "record",
    }
