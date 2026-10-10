from datetime import datetime, timezone
from pathlib import Path

from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Deal
from revenue_system.domain.stages import transition
from revenue_system.orchestration.events import DomainEvent
from revenue_system.segments.registry import PackRegistry
from revenue_system.skills.scoring import calculate_score


class DealOrchestrator:
    """Applies deterministic lifecycle work and persists each result."""

    def __init__(self, store: SQLiteStore, packs_root: Path = Path("packs")) -> None:
        self.store = store
        self.packs = PackRegistry(packs_root)

    def handle(self, event: DomainEvent) -> Deal | None:
        if event.event_type == "lead.created":
            return self._create_and_score(event)
        return None

    def _create_and_score(self, event: DomainEvent) -> Deal:
        payload = event.payload
        deal = Deal(
            id=payload.get("deal_id", payload["lead_id"]),
            segment=payload["segment"],
            company_name=payload["company_name"],
            contact_name=payload["contact_name"],
            fields=payload,
        )
        deal.stage = transition(deal.stage, "enriched")
        deal.fields["enrichment_status"] = "complete"
        pack = self.packs.get(deal.segment)
        features = {
            "fit": float(payload.get("fit", 0)),
            "intent": float(payload.get("intent", 0)),
            "engagement": float(payload.get("engagement", 0)),
        }
        deal.score = calculate_score(features, pack)
        deal.stage = transition(deal.stage, "scored")
        deal.updated_at = datetime.now(timezone.utc)
        self.store.save_deal(deal)
        self.store.audit("orchestrator", "lead_scored", deal.score.reason, deal.id)
        return deal

