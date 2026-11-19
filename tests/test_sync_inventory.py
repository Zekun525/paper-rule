import json
from hashlib import sha1

import pytest

from paperrule.domain.models import PaperProfile
from paperrule.ingestion.pipeline import ingest_revision_pair
from paperrule.persistence.store import MemoryStore
from paperrule.sync.git import GitSync, SyncError
from paperrule.sync.inventory import InventoryLimits, read_memory_inventory

COMMIT = "a" * 40
MANIFEST = b'{"schema_version":1,"product":"PaperRule"}'


class SyntheticGit:
    def __init__(self, root, files, modes=None):
        self.root = root.resolve()
        self.files = {"manifest.json": MANIFEST, **files}
        self.modes = modes or {}
        self.blobs = {sha1(data).hexdigest(): data for data in self.files.values()}

    def validate_sha(self, commit):
        assert commit == COMMIT
        return commit

    def run(self, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(self.root)
        assert args == ("ls-tree", "-r", "-z", "--full-tree", COMMIT)
        return chr(0).join(
            self.modes.get(path, "100644") + " blob " + sha1(data).hexdigest()
            + chr(9) + path for path, data in self.files.items()
        ) + chr(0)

    def read_blob(self, object_id, *, max_bytes):
        data = self.blobs[object_id]
        if len(data) > max_bytes:
            raise SyncError("Blob exceeds inventory size limit")
        return data


@pytest.mark.parametrize("data", [
    b'{"analysis_id":"AN-SYNTHETIC","analysis_id":"AN-SYNTHETIC"}',
    b'{"analysis_id":"AN-SYNTHETIC","nested":{"value":1,"value":2}}',
    b'{"analysis_id":"AN-SYNTHETIC","value":NaN}',
    b'{"analysis_id":"AN-SYNTHETIC","value":1e9999}',
    b'{"analysis_id":"AN-SYNTHETIC","value":-1e9999}',
    bytes([255]), b"[]", b'{"analysis_id":"AN-OTHER"}',
])
def test_invalid_committed_json_is_rejected(tmp_path, data):
    git = SyntheticGit(tmp_path, {"analyses/AN-SYNTHETIC.json": data})
    with pytest.raises(SyncError, match="invalid"):
        read_memory_inventory(git, COMMIT)


@pytest.mark.parametrize("files,modes", [
    ({"attachments/CON.txt": b"synthetic"}, {}),
    ({"attachments/SRC-SYNTHETIC.txt": b"synthetic"},
     {"attachments/SRC-SYNTHETIC.txt": "120000"}),
    ({"analyses/AN-SYNTHETIC.json": b"{}",
      "analyses/an-synthetic.json": b"{}"}, {}),
])
def test_inventory_integrates_windows_path_and_mode_guards(tmp_path, files, modes):
    with pytest.raises(SyncError, match="invalid"):
        read_memory_inventory(SyntheticGit(tmp_path, files, modes), COMMIT)


def test_inventory_limits_count_individual_files_and_total_bytes(tmp_path):
    git = SyntheticGit(tmp_path, {"attachments/SRC-SYNTHETIC.txt": b"x" * 40})
    for limits in (
        InventoryLimits(files=1),
        InventoryLimits(attachment_bytes=10),
        InventoryLimits(total_bytes=len(MANIFEST) + 10),
    ):
        with pytest.raises(SyncError):
            read_memory_inventory(git, COMMIT, limits=limits)


def test_real_committed_revision_pair_ignores_changed_working_tree_and_metadata_paths(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    store.initialize()
    pair = ingest_revision_pair(
        b"Synthetic original statement.", b"Synthetic revised statement.",
        "synthetic.txt", store,
    )
    store.save_paper(PaperProfile(
        paper_id="P-SYNTHETIC", project_path="D:/synthetic-external-unavailable",
    ))
    store.write_json("analyses", "AN-SYNTHETIC", {"analysis_id": "AN-SYNTHETIC"})
    store.write_json("runs", "RUN-SYNTHETIC", {"run_id": "RUN-SYNTHETIC"})
    git = GitSync(store.root)
    git.init()
    commit = git.commit_approved("Synthetic committed inventory fixture")
    before = git.run("status", "--porcelain")
    inventory = read_memory_inventory(git, commit)
    assert inventory.commit == commit
    assert inventory.entries["analyses/AN-SYNTHETIC.json"].record["analysis_id"] == "AN-SYNTHETIC"
    assert inventory.entries["runs/RUN-SYNTHETIC.json"].record["run_id"] == "RUN-SYNTHETIC"
    attachment = pair["source"]["attachment"]
    original = inventory.entries[attachment].data
    assert original == pair["diff"].encode("utf-8")
    assert git.run("status", "--porcelain") == before
    (store.root / attachment).write_bytes(b"Synthetic uncommitted alteration.")
    changed = git.run("status", "--porcelain")
    reread = read_memory_inventory(git, commit)
    assert reread.inventory_sha256 == inventory.inventory_sha256
    assert reread.entries[attachment].data == original
    assert git.run("status", "--porcelain") == changed
    assert git.head() == commit


@pytest.mark.parametrize("failure", ["missing", "hash", "identity", "pair"])
def test_source_attachment_and_original_bindings_are_checked(tmp_path, failure):
    source = {
        "id": "SRC-SYNTHETIC", "filename": "synthetic.txt",
        "sha256": "0" * 64, "kind": "text", "reviewer_id": "synthetic",
        "attachment": "attachments/SRC-SYNTHETIC.txt",
    }
    files = {}
    if failure != "missing":
        from hashlib import sha256
        data = b"Synthetic original."
        source["sha256"] = sha256(data).hexdigest()
        files[source["attachment"]] = data
    if failure == "hash":
        source["sha256"] = "0" * 64
    elif failure == "identity":
        source["id"] = "SRC-OTHER"
    elif failure == "pair":
        source["revision_pair"] = {
            "before_source_id": "SRC-MISSING", "after_source_id": source["id"],
            "before_sha256": "0" * 64, "after_sha256": source["sha256"],
        }
    files["sources/SRC-SYNTHETIC.json"] = json.dumps(source).encode("utf-8")
    with pytest.raises(SyncError, match="invalid"):
        read_memory_inventory(SyntheticGit(tmp_path, files), COMMIT)
