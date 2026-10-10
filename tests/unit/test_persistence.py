from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Deal
from revenue_system.orchestration.events import DomainEvent
from revenue_system.orchestration.worker import EventWorker


def test_event_idempotency_and_deal_round_trip(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'test.db'}")
    worker = EventWorker(store)
    event = DomainEvent("lead.created", "hubspot:lead:1", {"lead_id": "l1"})
    assert worker.ingest(event) is True
    assert worker.ingest(event) is False
    assert worker.pending()[0].event_id == event.event_id

    deal = Deal("d1", "brand", "Example Foods", "Amina")
    store.save_deal(deal)
    assert store.get_deal("d1").company_name == "Example Foods"

