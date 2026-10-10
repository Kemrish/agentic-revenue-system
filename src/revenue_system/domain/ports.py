from typing import Any, Protocol

from .models import Action, Deal


class CrmPort(Protocol):
    def get_deal(self, deal_id: str) -> Deal: ...
    def update_properties(self, object_type: str, object_id: str, properties: dict[str, str], source: str) -> None: ...


class MailPort(Protocol):
    async def send(self, recipient: str, subject: str, body: str, idempotency_key: str) -> str: ...


class TranscriptPort(Protocol):
    async def get_transcript(self, transcript_id: str) -> str: ...


class ESignPort(Protocol):
    async def send_for_signature(self, document: str, idempotency_key: str) -> str: ...


class DealRepository(Protocol):
    def get(self, deal_id: str) -> Deal | None: ...
    def save(self, deal: Deal) -> None: ...


class EventStore(Protocol):
    def add_once(self, event_id: str, event_type: str, payload: dict[str, Any]) -> bool: ...


class OutboxRepository(Protocol):
    def add_once(self, key: str, action: Action) -> bool: ...

