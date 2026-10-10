from revenue_system.adapters.db import SQLiteStore
from revenue_system.orchestration.events import DomainEvent


class EventWorker:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def ingest(self, event: DomainEvent) -> bool:
        return self.store.add_event_once(event.event_id, event.event_type, event.payload)

    def pending(self) -> list[DomainEvent]:
        return [DomainEvent(row["event_type"], row["id"], __import__("json").loads(row["payload"])) for row in self.store.pending_events()]

    def mark_processed(self, event_id: str) -> None:
        self.store.mark_event_processed(event_id)

