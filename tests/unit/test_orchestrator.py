from pathlib import Path

from revenue_system.adapters.db import SQLiteStore
from revenue_system.orchestration.events import DomainEvent
from revenue_system.orchestration.orchestrator import DealOrchestrator


def test_lead_event_creates_and_scores_deal(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'workflow.db'}")
    orchestrator = DealOrchestrator(store, Path("packs"))
    deal = orchestrator.handle(DomainEvent("lead.created", "lead:1", {
        "lead_id": "lead-1",
        "segment": "brand",
        "company_name": "Example Foods",
        "contact_name": "Amina Hassan",
        "fit": 88,
        "intent": 70,
        "engagement": 0,
    }))
    assert deal is not None
    assert deal.stage == "scored"
    assert deal.score is not None
    assert store.get_deal("lead-1").stage == "scored"

