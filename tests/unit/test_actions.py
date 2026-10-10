from pathlib import Path

from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Action, ActionType, Deal, Score, Tier
from revenue_system.orchestration.actions import route_action
from revenue_system.segments.schema import load_pack


def test_top_tier_outreach_is_routed_to_approval(tmp_path):
    store = SQLiteStore(f"sqlite:///{tmp_path / 'actions.db'}")
    deal = Deal("d1", "brand", "Example", "Amina", score=Score(90, 80, 0, 86, Tier.A, "reason"))
    result = route_action(store, Action(ActionType.SEND_FIRST_TOUCH, "d1"), deal, load_pack(Path("packs/brand/pack.yaml")))
    assert result == "REQUIRE_APPROVAL"
    assert store.connection.execute("SELECT count(*) FROM approvals").fetchone()[0] == 1

