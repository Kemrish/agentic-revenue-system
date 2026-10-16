from revenue_system.domain.models import Action, ActionType, Deal, PolicyDecision
from revenue_system.segments.schema import SegmentPack

from .messaging import outreach_error


class PolicyEngine:
    def evaluate(self, action: Action, deal: Deal, pack: SegmentPack, kill_switch: bool = False) -> PolicyDecision:
        if kill_switch:
            return PolicyDecision("KILL_SWITCH", "Global kill switch is enabled", "kill_switch")
        if "do_not_contact" in deal.flags and action.action_type in {ActionType.SEND_FIRST_TOUCH, ActionType.SEND_FOLLOW_UP, ActionType.SEND_CONTRACT}:
            return PolicyDecision("DENY", "Contact unsubscribed", "do_not_contact")
        if "suspicious_reply" in deal.flags and action.action_type in {ActionType.SEND_FIRST_TOUCH, ActionType.SEND_FOLLOW_UP, ActionType.SEND_CONTRACT}:
            return PolicyDecision("DENY", "Suspicious inbound content quarantines external contact", "suspicious_contact")
        if action.payload.get("unsafe") or action.payload.get("injection_detected"):
            return PolicyDecision("DENY", "Unsafe action or untrusted instruction detected", "unsafe_action")
        if action.action_type is ActionType.SYNC_CRM:
            return PolicyDecision("AUTO", "Bounded CRM score/stage synchronization; delivery requires explicit configuration", "crm_sync")
        if action.action_type is ActionType.CHANGE_PRICING:
            return PolicyDecision("DENY", "Agents cannot change pricing; edit sensitive terms in the contract review", "human_pricing_only")
        if action.action_type is ActionType.SEND_CONTRACT:
            return PolicyDecision("REQUIRE_APPROVAL", "Human must review sensitive terms and approve this exact contract version", "contract_review")
        if action.action_type in {ActionType.SEND_FIRST_TOUCH, ActionType.SEND_FOLLOW_UP}:
            if error := outreach_error(action.payload):
                return PolicyDecision("DENY", error, "unsafe_routine_message")
            if action.action_type is ActionType.SEND_FOLLOW_UP and (deal.fields.get("last_reply") or deal.stage != "outreach"):
                return PolicyDecision("DENY", "Follow-ups stop once a reply arrives or the deal leaves outreach", "follow_up_stop")
            return PolicyDecision("AUTO", "Non-commercial outreach is automatic for every lead tier", "automatic_outreach")
        if action.action_type in {ActionType.ENRICH, ActionType.SCORE, ActionType.GENERATE_IO}:
            return PolicyDecision("AUTO", "Low-risk action is allowed", action.action_type.value)
        return PolicyDecision("REQUIRE_APPROVAL", "Action has no automatic policy rule", "default_approval")

