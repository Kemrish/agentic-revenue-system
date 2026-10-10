import json
from typing import Any

from revenue_system.adapters.db import SQLiteStore


class OutboxWorker:
    """Delivery boundary; concrete adapters are injected in the next runtime slice."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def pending(self) -> list[dict[str, Any]]:
        return [{"id": row["id"], "action_type": row["action_type"], "deal_id": row["deal_id"], "payload": json.loads(row["payload"])} for row in self.store.pending_outbox()]

    def mark_sent(self, outbox_id: str) -> None:
        self.store.mark_outbox_sent(outbox_id)

