from pathlib import Path

from revenue_system.segments.schema import load_pack
from revenue_system.skills.scoring import calculate_score


def test_brand_score_is_tier_a_when_fit_and_intent_are_strong():
    pack = load_pack(Path("packs/brand/pack.yaml"))
    score = calculate_score({"fit": 88, "intent": 70, "engagement": 0}, pack)
    assert score.tier.value == "A"
    assert score.total > 75
    assert "Fit 88" in score.reason

