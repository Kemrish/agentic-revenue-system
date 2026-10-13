from revenue_system.domain.models import Action, ActionType, Deal, PolicyDecision
from revenue_system.segments.schema import SegmentPack


class PolicyEngine:
    def evaluate(self, action: Action, deal: Deal, pack: SegmentPack, kill_switch: bool = False) -> PolicyDecision:
        if kill_switch:
            return PolicyDecision("KILL_SWITCH", "Global kill switch is enabled", "kill_switch")
        if action.payload.get("unsafe") or action.payload.get("injection_detected"):
            return PolicyDecision("DENY", "Unsafe action or untrusted instruction detected", "unsafe_action")
        if action.action_type in {ActionType.CHANGE_PRICING, ActionType.SEND_CONTRACT}:
            return PolicyDecision("REQUIRE_APPROVAL", "Commercial or contract action requires approval", action.action_type.value)
        if action.action_type is ActionType.SEND_FIRST_TOUCH and deal.score and deal.score.tier.value == "A":
            return PolicyDecision("REQUIRE_APPROVAL", "First touch to a tier A lead requires approval", "first_touch_tier_a")
        if action.action_type in {ActionType.ENRICH, ActionType.SCORE, ActionType.GENERATE_IO, ActionType.SEND_FOLLOW_UP}:
            return PolicyDecision("AUTO", "Low-risk action is allowed", action.action_type.value)
        return PolicyDecision("REQUIRE_APPROVAL", "Action has no automatic policy rule", "default_approval")

