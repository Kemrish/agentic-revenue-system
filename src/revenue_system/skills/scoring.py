from typing import Any

from revenue_system.domain.models import Score, Tier
from revenue_system.segments.schema import SegmentPack


def calculate_score(features: dict[str, Any], pack: SegmentPack) -> Score:
    raw = {name: float(features.get(name, 0)) for name in ("fit", "intent", "engagement")}
    weights = dict(pack.scoring.weights)
    if raw["engagement"] == 0:
        engagement_weight = weights.pop("engagement", 0)
        total_weight = sum(weights.values()) or 1
        weights = {key: value / total_weight for key, value in weights.items()}
    total = round(sum(raw[key] * weights.get(key, 0) for key in raw), 2)
    if total >= pack.scoring.tiers.get("A", 75) and raw["fit"] >= pack.scoring.fit_gate_for_a:
        tier = Tier.A
    elif total >= pack.scoring.tiers.get("B", 50):
        tier = Tier.B
    else:
        tier = Tier.C
    reason = f"Fit {raw['fit']:.0f}; intent {raw['intent']:.0f}; engagement {raw['engagement']:.0f}; total {total:.0f}; tier {tier.value}."
    return Score(raw["fit"], raw["intent"], raw["engagement"], total, tier, reason)

