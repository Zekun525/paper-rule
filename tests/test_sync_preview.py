import pytest

from paperrule.domain.models import RuleRecord, digest
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore
from paperrule.sync.git import SyncError
from paperrule.sync.preview import preview_rule_divergence

RULE_ID = "R-SYNTHETIC-SYNC"
RULE_PATH = "rules/global/" + RULE_ID + ".json"


def devices(tmp_path):
    first = MemoryStore(tmp_path / "synthetic-device-a")
    governance = Governance(first)
    proposal = governance.propose(RuleRecord(
        id=RULE_ID, short_title="Synthetic synchronized rule",
        statement="Explain the synthetic base assumption.",
    ))
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    remote = tmp_path / "synthetic-private-remote.git"
    governance.git.run("init", "--bare", str(remote))
    governance.git.run("remote", "add", "origin", str(remote))
    assert governance.git.push()["status"] == "synced"
    base = governance.git.head()
    second_path = tmp_path / "synthetic-device-b"
    governance.git.run("clone", str(remote), str(second_path))
    second = MemoryStore(second_path)
    return first, governance, second, Governance(second), base


def amend(store, governance, statement):
    rule = store.rule(RULE_ID).model_copy(update={"statement": statement}, deep=True)
    proposal = governance.propose(rule, "amend")
    governance.approve(proposal.proposal_id, proposal.proposal_hash)


def authority(store, governance):
    return store.rules(), store.decisions(), governance.git.head()


def test_divergent_preview_binds_all_three_versions_without_applying_either(tmp_path):
    first, local, second, other, base = devices(tmp_path)
    amend(second, other, "Explain the synthetic remote assumption.")
    amend(first, local, "Explain the synthetic local assumption.")
    before = authority(first, local)
    status = local.git.run("status", "--porcelain")
    preview = preview_rule_divergence(local.git)
    assert preview["status"] == "diverged"
    assert preview["base_commit"] == base
    assert preview["local_commit"] == local.git.head()
    assert preview["remote_commit"] == other.git.head()
    assert preview["applies_changes"] is False
    assert preview["requires_approval"] is True
    assert len(preview["changes"]) == 1
    change = preview["changes"][0]
    assert change["rule_id"] == RULE_ID
    assert change["kind"] == "both_changed"
    assert change["base"]["rule"]["version"] == 1
    assert change["local"]["rule"]["statement"] == "Explain the synthetic local assumption."
    assert change["remote"]["rule"]["statement"] == "Explain the synthetic remote assumption."
    assert change["local"]["rule"]["version"] == change["remote"]["rule"]["version"] == 2
    assert change["local"]["blob_sha"] != change["remote"]["blob_sha"]
    assert preview["preview_sha256"] == digest({
        key: value for key, value in preview.items() if key != "preview_sha256"
    })
    assert preview_rule_divergence(local.git, fetch=False) == preview
    assert authority(first, local) == before
    assert local.git.run("status", "--porcelain") == status


def test_remote_only_preview_keeps_the_local_active_record(tmp_path):
    first, local, second, other, _ = devices(tmp_path)
    amend(second, other, "Explain the synthetic remote addition.")
    before = authority(first, local)
    preview = preview_rule_divergence(local.git)
    assert preview["status"] == "behind"
    assert preview["changes"][0]["kind"] == "remote_change"
    assert first.rule(RULE_ID).version == 1
    assert authority(first, local) == before


def test_dirty_and_staged_records_are_disclosed_without_changing_the_index(tmp_path):
    first, local, _, _, _ = devices(tmp_path)
    note = first.root / "synthetic-note.txt"
    note.write_text("Synthetic unapproved note.", encoding="utf-8")
    local.git.run("add", "--", note.name)
    staged = local.git.run("diff", "--cached", "--name-only")
    before = authority(first, local)
    preview = preview_rule_divergence(local.git)
    assert preview["status"] == "same"
    assert preview["changes"] == []
    assert preview["working_tree_dirty"] is True
    assert preview["staged_changes"] is True
    assert local.git.run("diff", "--cached", "--name-only") == staged
    assert authority(first, local) == before


@pytest.mark.parametrize("corruption", ["invalid-json", "invalid-utf8", "identity", "symlink"])
def test_untrusted_remote_rule_entries_are_rejected_without_application(tmp_path, corruption):
    first, local, second, other, _ = devices(tmp_path)
    target = second.root / RULE_PATH
    if corruption == "symlink":
        blob = other.git.run("rev-parse", "HEAD:" + RULE_PATH)
        other.git.run("update-index", "--cacheinfo", "120000", blob, RULE_PATH)
    else:
        if corruption == "invalid-json":
            target.write_text("{}", encoding="utf-8")
        elif corruption == "invalid-utf8":
            target.write_bytes(bytes([255]))
        else:
            rule = second.rule(RULE_ID).model_copy(update={"id": "R-SYNTHETIC-OTHER"})
            target.write_text(rule.model_dump_json(), encoding="utf-8")
        other.git.run("add", "--", RULE_PATH)
    other.git.commit("Synthetic malformed remote rule fixture")
    assert other.git.push()["status"] == "synced"
    before = authority(first, local)
    with pytest.raises(SyncError):
        preview_rule_divergence(local.git)
    assert authority(first, local) == before
    assert not local.git.run("diff", "--cached", "--name-only")


def test_bounded_blob_read_rejects_large_content_and_non_object_inputs(tmp_path):
    _, local, _, _, _ = devices(tmp_path)
    blob = local.git.run("rev-parse", "HEAD:" + RULE_PATH)
    with pytest.raises(SyncError, match="size limit"):
        local.git.read_blob(blob, max_bytes=5)
    with pytest.raises(SyncError, match="object ID"):
        local.git.read_blob("HEAD:" + RULE_PATH)
    with pytest.raises(SyncError, match="Git blob"):
        local.git.read_blob(local.git.head())
