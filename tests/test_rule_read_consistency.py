from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from threading import Event

import pytest

from paperrule.domain.models import RuleRecord, RuleScope
from paperrule.persistence.store import MemoryStore


def original_rule():
    return RuleRecord(
        id="R-SYNTHETIC-CONSISTENCY", short_title="Synthetic guidance",
        statement="Preserve synthetic assumptions.", status="active",
    )


def test_failed_replacement_does_not_delete_previous_active_rule(tmp_path, monkeypatch):
    store = MemoryStore(tmp_path / "synthetic-memory")
    original = original_rule()
    store.save_rule(original)
    updated = original.model_copy(update={"version": 2, "statement": "Synthetic revised guidance."})

    def fail_write(*args, **kwargs):
        raise OSError("Synthetic failed replacement")

    monkeypatch.setattr(store, "_write", fail_write)
    with pytest.raises(OSError, match="failed replacement"):
        store.save_rule(updated)
    assert store.rule(original.id) == original


def test_reader_waits_for_scope_move_and_returns_one_complete_rule(tmp_path, monkeypatch):
    root = tmp_path / "synthetic-memory"
    writer = MemoryStore(root)
    reader = MemoryStore(root)
    original = original_rule()
    writer.save_rule(original)
    updated = original.model_copy(update={
        "version": 2,
        "scope": RuleScope(levels=["paper"], paper_ids=["synthetic-paper"]),
    })
    writing = Event()
    release = Event()
    write = writer._write

    def paused_write(folder, key, model):
        if folder == "rules/paper":
            writing.set()
            if not release.wait(timeout=5):
                raise TimeoutError("Synthetic writer was not released")
        return write(folder, key, model)

    monkeypatch.setattr(writer, "_write", paused_write)
    with ThreadPoolExecutor(max_workers=2) as executor:
        saving = executor.submit(writer.save_rule, updated)
        try:
            assert writing.wait(timeout=5)
            reading = executor.submit(reader.rules)
            with pytest.raises(FutureTimeout):
                reading.result(timeout=0.2)
        finally:
            release.set()
        saving.result(timeout=5)
        assert reading.result(timeout=5) == [updated]


def test_transaction_lock_is_reentrant_across_stores_in_same_thread(tmp_path):
    root = tmp_path / "synthetic-memory"
    first = MemoryStore(root)
    second = MemoryStore(root)
    with first.locked():
        second.save_rule(original_rule())
        assert second.rules() == [original_rule()]
        assert (root / ".transaction.lock").exists()
    assert not (root / ".transaction.lock").exists()
