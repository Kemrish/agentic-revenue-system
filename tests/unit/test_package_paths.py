from revenue_system.adapters.db import SQLiteStore
from revenue_system.orchestration.orchestrator import DealOrchestrator
from revenue_system.segments.paths import packs_path
from revenue_system.segments.registry import PackRegistry


def test_default_packs_are_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert {p.segment for p in PackRegistry().all()} == {"brand", "publisher"}
    assert packs_path().is_absolute()
    store = SQLiteStore("sqlite:///:memory:")
    assert DealOrchestrator(store).packs.get("brand").segment == "brand"
    store.connection.close()
