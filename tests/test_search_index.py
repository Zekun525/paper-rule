from paperrule.domain.models import RuleRecord
from paperrule.persistence.store import MemoryStore


def test_sqlite_fts_rebuilds_from_authoritative_records(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    store.initialize()
    store.save_rule(RuleRecord(id="G-search", short_title="Proof clarity", statement="Keep every algebraic step"))
    assert store.search("algebraic", kind="rule")[0]["record_id"] == "G-search"
    assert (store.root / "cache" / "index.sqlite3").exists()
