import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from revenue_system.adapters.db import LeaseLostError, SQLiteStore
from revenue_system.orchestration.events import DomainEvent
from revenue_system.orchestration.orchestrator import DealOrchestrator

logger = logging.getLogger(__name__)


class EventWorker:
    """Processes durable events: one transaction per event, bounded retries, dead letters."""

    def __init__(self, store: SQLiteStore, max_attempts: int = 5, lease_seconds: int = 300, retry_base_seconds: float = 0) -> None:
        self.store = store
        self.max_attempts = max_attempts
        self.lease_seconds = lease_seconds
        self.retry_base_seconds = retry_base_seconds
        self.owner = f"worker:{uuid4().hex}"

    def ingest(self, event: DomainEvent) -> bool:
        return self.store.add_event_once(event.event_id, event.event_type, event.payload)

    def pending(self, event_types: set[str] | None = None) -> list[DomainEvent]:
        events = [DomainEvent(row["event_type"], row["id"], json.loads(row["payload"])) for row in self.store.pending_events()]
        return [event for event in events if event_types is None or event.event_type in event_types]

    def mark_processed(self, event_id: str) -> None:
        self.store.mark_event_processed(event_id)

    def fire_due_timers(self, now: datetime | None = None) -> int:
        rows = self.store.due_timers(now or datetime.now(timezone.utc))
        for row in rows:
            self.store.fire_timer(row)
        return len(rows)

    async def process(self, event: DomainEvent, orchestrator: DealOrchestrator) -> bool | None:
        """Apply one event atomically. A failure rolls back every write it made."""
        if not self.store.claim("events", event.event_id, self.owner, self.lease_seconds, self.max_attempts):
            return None
        try:
            async with asyncio.timeout(self.lease_seconds * .8):
                with self.store.transaction():
                    await orchestrator.process(event)
                    self.store.assert_claim("events", event.event_id, self.owner)
                    self.mark_processed(event.event_id)
            return True
        except LeaseLostError:
            logger.warning("Event lease lost: %s", event.event_id)
            return None
        except asyncio.CancelledError:
            self.store.release_claim("events", event.event_id, self.owner)
            raise
        except Exception as exc:
            status = self.store.record_event_failure(event.event_id, f"{type(exc).__name__}: {exc}", self.max_attempts, self.retry_base_seconds)
            self.store.audit("worker", "event_dead_letter" if status == "dead" else "event_retry",
                             f"{event.event_type} {event.event_id}: {exc}", event.payload.get("deal_id"))
            logger.warning("Event %s failed (%s): %s", event.event_id, status, exc)
            return False

    async def run_once(self, orchestrator: DealOrchestrator, event_types: set[str] | None = None) -> dict[str, int]:
        release = getattr(orchestrator, "release_routine_reviews", None)
        if event_types is None and release is not None:
            release()
        timers = self.fire_due_timers() if event_types is None or "timer.due" in event_types else 0
        processed = failed = 0
        for event in self.pending(event_types):
            result = await self.process(event, orchestrator)
            if result is True:
                processed += 1
            elif result is False:
                failed += 1
        return {"timers_fired": timers, "processed": processed, "failed": failed}

    async def run_forever(self, orchestrator: DealOrchestrator, poll_seconds: float = 5.0, stop: asyncio.Event | None = None,
                          delivery=None) -> None:
        stop = stop or asyncio.Event()
        while not stop.is_set():
            self.store.heartbeat()
            result = await self.run_once(orchestrator)
            if delivery is not None:
                await delivery.deliver_pending(continue_on_error=True)
                # Delivery acknowledgements are deterministic and should not
                # require another operator step or poll cycle to update stages.
                await self.run_once(orchestrator, {"action.delivered"})
            if result["processed"] or result["failed"] or result["timers_fired"]:
                logger.info("Worker cycle: %s", result)
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
