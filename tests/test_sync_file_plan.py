from hashlib import sha256

import pytest
from test_sync_preview import RULE_PATH, amend, authority, devices

from paperrule.domain.models import digest
from paperrule.sync.inventory import MemoryBlob, MemoryInventory, read_memory_inventory
from paperrule.sync.plan import prepare_file_plan
from paperrule.sync.preview import preview_rule_divergence


def inventory(commit, files):
    entries = {
        path: MemoryBlob(
            path, mode, sha256(data).hexdigest()[:40], "record", data,
            sha256(data).hexdigest(),
        )
        for path, (data, mode) in files.items()
    }
    return MemoryInventory(
        commit * 40, entries, sum(len(blob.data) for blob in entries.values()),
        digest({"commit": commit, "files": [
            {"path": path, "sha256": blob.sha256, "mode": blob.mode}
            for path, blob in sorted(entries.items())
        ]}),
    )


@pytest.mark.parametrize("base,local,remote,state,side", [
    ("old", "old", "old", "same", "local"),
    ("old", "new", "new", "same", "local"),
    ("old", "old", "new", "remote_change", "remote"),
    ("old", "new", "old", "local_change", "local"),
    ("old", "here", "there", "conflict", None),
    ("old", None, "new", "conflict", None),
    ("old", "new", None, "conflict", None),
    ("old", "old", None, "remote_change", "remote"),
    ("old", None, "old", "local_change", "local"),
    (None, "new", None, "local_change", "local"),
    (None, None, "new", "remote_change", "remote"),
    (None, "here", "there", "conflict", None),
    ("old", None, None, "same", "local"),
])
def test_three_way_decisions_remain_recommendations(base, local, remote, state, side):
    path = "history/R-SYNTHETIC-v2.json"

    def snapshot(commit, value):
        files = {} if value is None else {path: (value, "100644")}
        # Serialize synthetic content before building the in-memory blob.
        return inventory(commit, {
            key: (data.encode(), mode) for key, (data, mode) in files.items()
        })

    snapshots = [snapshot(commit, value) for commit, value in zip("abc", (base, local, remote))]
    result = prepare_file_plan(*snapshots)
    row = result["files"][0]
    assert row["state"] == state
    assert row["recommended_side"] == side
    assert row["requires_decision"] == (side is None)
    assert result["conflict_count"] == int(side is None)
    assert result["requires_approval"] is True
    assert result["applies_changes"] is False
    assert result["plan_sha256"] == digest({
        key: value for key, value in result.items() if key != "plan_sha256"
    })
    assert prepare_file_plan(*snapshots) == result


def test_mode_and_inventory_bindings_are_part_of_plan():
    path = "analyses/AN-SYNTHETIC.json"
    base = inventory("a", {path: (b"synthetic", "100644")})
    local = inventory("b", {path: (b"synthetic", "100755")})
    remote = inventory("c", {path: (b"remote synthetic", "100644")})
    result = prepare_file_plan(base, local, remote)
    assert result["files"][0]["state"] == "conflict"
    rebound = MemoryInventory(remote.commit, remote.entries, remote.total_bytes, "d" * 64)
    assert prepare_file_plan(base, local, rebound)["plan_sha256"] != result["plan_sha256"]


def test_actual_divergent_approved_histories_are_not_silently_overwritten(tmp_path):
    first, local, second, other, base_commit = devices(tmp_path)
    amend(second, other, "Explain the synthetic remote inventory assumption.")
    amend(first, local, "Explain the synthetic local inventory assumption.")
    preview = preview_rule_divergence(local.git)
    before = authority(first, local)
    status = local.git.run("status", "--porcelain")
    snapshots = [
        read_memory_inventory(local.git, commit)
        for commit in (base_commit, local.git.head(), preview["remote_commit"])
    ]
    result = prepare_file_plan(*snapshots)
    rows = {row["path"]: row for row in result["files"]}
    assert rows[RULE_PATH]["state"] == "conflict"
    history = "history/R-SYNTHETIC-SYNC-v2.json"
    assert rows[history]["state"] == "conflict"
    assert rows[history]["recommended_side"] is None
    assert rows[history]["local"]["sha256"] != rows[history]["remote"]["sha256"]
    assert any(
        row["path"].startswith("decisions/") and row["state"] == "remote_change"
        for row in result["files"]
    )
    assert result["inventory_bindings"] == {
        side: snapshot.inventory_sha256
        for side, snapshot in zip(("base", "local", "remote"), snapshots)
    }
    assert authority(first, local) == before
    assert local.git.run("status", "--porcelain") == status
