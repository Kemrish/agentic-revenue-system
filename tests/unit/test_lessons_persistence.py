from revenue_system.adapters.db import SQLiteStore


def test_lesson_can_be_saved_and_retrieved_when_active(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'lessons.db'}")
    store.save_lesson("l1", "brand", "Measurement improves replies", ["call-1"], "active")
    assert store.active_lessons("brand")[0]["id"] == "l1"

