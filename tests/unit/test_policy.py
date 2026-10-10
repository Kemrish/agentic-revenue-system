from pathlib import Path

from revenue_system.domain.models import Action, ActionType, Deal, Score, Tier
from revenue_system.governance.policy import PolicyEngine
from revenue_system.segments.schema import load_pack


def test_top_tier_first_touch_requires_approval():
    deal = Deal("d1", "brand", "Example", "Amina", score=Score(90, 80, 0, 86, Tier.A, "reason"))
    result = PolicyEngine().evaluate(Action(ActionType.SEND_FIRST_TOUCH, "d1"), deal, load_pack(Path("packs/brand/pack.yaml")))
    assert result.decision == "REQUIRE_APPROVAL"


def test_kill_switch_denies_action():
    deal = Deal("d1", "brand", "Example", "Amina")
    result = PolicyEngine().evaluate(Action(ActionType.ENRICH, "d1"), deal, load_pack(Path("packs/brand/pack.yaml")), kill_switch=True)
    assert result.decision == "DENY"

