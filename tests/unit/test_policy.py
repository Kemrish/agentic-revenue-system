from pathlib import Path

from revenue_system.domain.models import Action, ActionType, Deal, Score, Tier
from revenue_system.governance.policy import PolicyEngine
from revenue_system.segments.schema import load_pack


def test_top_tier_first_touch_is_automatic():
    deal = Deal("d1", "brand", "Example", "Amina", score=Score(90, 80, 0, 86, Tier.A, "reason"))
    result = PolicyEngine().evaluate(Action(ActionType.SEND_FIRST_TOUCH, "d1", {"recipient":"a@example.com", "subject":"Hello", "body":"Could we discuss your needs?"}), deal, load_pack(Path("packs/brand/pack.yaml")))
    assert result.decision == "AUTO"


def test_kill_switch_is_distinct_from_policy_deny():
    deal = Deal("d1", "brand", "Example", "Amina")
    result = PolicyEngine().evaluate(Action(ActionType.ENRICH, "d1"), deal, load_pack(Path("packs/brand/pack.yaml")), kill_switch=True)
    assert result.decision == "KILL_SWITCH"


def test_unsafe_action_is_denied_without_stopping_the_system():
    deal = Deal("d1", "brand", "Example", "Amina")
    result = PolicyEngine().evaluate(
        Action(ActionType.SEND_FOLLOW_UP, "d1", {"injection_detected": True}),
        deal,
        load_pack(Path("packs/brand/pack.yaml")),
    )
    assert result.decision == "DENY"

