"""Presenter endpoints: system description, interactive agent lab, and demo seeding.

Every endpoint calls the same production code paths (scoring, policy, agents,
validation, routing). Nothing here re-implements a business rule.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from .adapters.db import SQLiteStore
from .agents.call_intelligence import CallIntelligenceAgent
from .agents.deal_desk import IODraft
from .agents.reply_triage import ReplyTriageAgent
from .agents.tools import TOOL_SCOPES
from .container import agent_runner
from .domain.models import Action, ActionType, Deal, Score, Tier
from .domain.stages import ALLOWED_TRANSITIONS, STAGES
from .governance.guardrails import wrap_untrusted_content
from .governance.policy import PolicyEngine
from .orchestration.actions import route_action
from .orchestration.demo_flow import run_pipeline
from .segments.registry import PackRegistry
from .settings import Settings
from .skills.io_validation import validate_io
from .skills.scoring import calculate_score, effective_weights
from .skills.templating import TemplateRenderer

ROOT = Path(".")
router = APIRouter(prefix="/api")

AGENTS = [
    {"name": "research", "title": "Research", "input": "Lead and company records",
     "output": "Evidence and scoring features", "untrusted": False, "status": "scoped",
     "job": "Extracts fit and intent evidence that deterministic scoring rules consume."},
    {"name": "outreach", "title": "Outreach", "input": "Deal, segment pack, active lessons",
     "output": "OutreachDraft (subject, body, confidence, lessons_used)", "untrusted": False, "status": "implemented",
     "job": "Drafts first-touch and follow-up messages from pack messaging and retrieved lessons."},
    {"name": "reply_triage", "title": "Reply triage", "input": "Inbound email (untrusted)",
     "output": "ReplyClassification (label, confidence, injection flag)", "untrusted": True, "status": "implemented",
     "job": "Classifies replies and flags instruction-like content. Has no tools at all."},
    {"name": "call_intelligence", "title": "Call intelligence", "input": "Fireflies transcript (untrusted)",
     "output": "CallDigest (qualification fields, objections, next steps, lesson)", "untrusted": True, "status": "implemented",
     "job": "Turns a discovery call into deal fields and a lesson candidate."},
    {"name": "deal_desk", "title": "Deal desk", "input": "Qualified deal fields",
     "output": "IODraft (entity, budget, dates, line items)", "untrusted": False, "status": "implemented",
     "job": "Maps deal data into IO fields. Trusted upstream numbers override its output."},
    {"name": "pipeline_analyst", "title": "Pipeline analyst", "input": "Pipeline rows",
     "output": "Stall reports and digests", "untrusted": False, "status": "scoped",
     "job": "Detects stalled deals against pack SLAs and summarises the pipeline."},
]

# Evaluation order of PolicyEngine.evaluate; rule ids match its return values.
POLICY_RULES = [
    {"rule_id": "kill_switch", "decision": "KILL_SWITCH", "when": "Global kill switch is enabled"},
    {"rule_id": "unsafe_action", "decision": "DENY", "when": "Payload is unsafe or injection was detected"},
    {"rule_id": "change_pricing", "decision": "REQUIRE_APPROVAL", "when": "Pricing change"},
    {"rule_id": "send_contract", "decision": "REQUIRE_APPROVAL", "when": "IO or contract send"},
    {"rule_id": "first_touch_tier_a", "decision": "REQUIRE_APPROVAL", "when": "First touch to a tier A lead"},
    {"rule_id": "low_risk", "decision": "AUTO", "when": "Enrich, score, generate IO, follow-up"},
    {"rule_id": "default_approval", "decision": "REQUIRE_APPROVAL", "when": "Anything without a rule"},
]


class ScoreRequest(BaseModel):
    segment: str
    fit: float = Field(ge=0, le=100)
    intent: float = Field(ge=0, le=100)
    engagement: float = Field(ge=0, le=100)


class PolicyRequest(BaseModel):
    action_type: ActionType
    tier: Tier = Tier.A
    injection_detected: bool = False
    kill_switch: bool = False


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    segment: str = "brand"


class IORequest(BaseModel):
    deal_id: str = ""
    segment: str = "brand"
    legal_entity: str = ""
    budget: float = 0
    start_date: str = ""
    end_date: str = ""
    line_items: list[dict[str, float | int | str]] = Field(default_factory=list)


class ResetRequest(BaseModel):
    confirm: str


def packs() -> PackRegistry:
    return PackRegistry(ROOT / "packs")


def pack_or_404(segment: str):
    try:
        return packs().get(segment)
    except KeyError as exc:
        raise HTTPException(404, f"Unknown segment pack: {segment}") from exc


lab_runner = agent_runner


def fixture(path: str) -> str:
    return (ROOT / "fixtures" / path).read_text(encoding="utf-8")


@router.get("/system")
def system():
    return {
        "stages": list(STAGES),
        "transitions": sorted([list(pair) for pair in ALLOWED_TRANSITIONS], key=lambda p: (STAGES.index(p[0]), STAGES.index(p[1]))),
        "agents": [agent | {"tools": [tool.__name__ for tool in TOOL_SCOPES[agent["name"]]]} for agent in AGENTS],
        "policy_rules": POLICY_RULES,
        "segments": [{"segment": p.segment, "display_name": p.display_name, "weights": p.scoring.weights,
                      "tiers": p.scoring.tiers, "fit_gate_for_a": p.scoring.fit_gate_for_a,
                      "qualification_fields": p.qualification_fields, "messaging": p.messaging,
                      "contract_template": p.templates.contract, "require_approval": p.autonomy.get("require_approval", [])}
                     for p in packs().all()],
        "fixtures": {"interested": fixture("replies/interested.txt"), "injection": fixture("replies/prompt_injection.txt"),
                     "transcript": fixture("transcripts/brand-discovery.txt")},
        "runner": lab_runner(Settings())[1],
    }


@router.post("/lab/score")
def lab_score(request: ScoreRequest):
    pack = pack_or_404(request.segment)
    features = request.model_dump(include={"fit", "intent", "engagement"})
    weights = effective_weights(features, pack)
    score = calculate_score(features, pack)
    return {"total": score.total, "tier": score.tier.value, "reason": score.reason, "weights": weights,
            "contributions": {key: round(features[key] * weights.get(key, 0), 2) for key in features},
            "thresholds": pack.scoring.tiers, "fit_gate_for_a": pack.scoring.fit_gate_for_a,
            "engagement_redistributed": request.engagement == 0}


@router.post("/lab/policy")
def lab_policy(request: PolicyRequest):
    deal = Deal("simulated", "brand", "Simulated account", "Simulated contact",
                score=Score(80, 70, 0, 80, request.tier, "simulated"))
    payload = {"injection_detected": True} if request.injection_detected else {}
    decision = PolicyEngine().evaluate(Action(request.action_type, deal.id, payload), deal, pack_or_404("brand"), request.kill_switch)
    rule_id = decision.rule_id if decision.rule_id in {r["rule_id"] for r in POLICY_RULES} else "low_risk"
    return {"decision": decision.decision, "reason": decision.reason, "rule_id": rule_id}


@router.post("/lab/triage")
async def lab_triage(request: TextRequest):
    runner, label = lab_runner(Settings())
    try:
        result = await ReplyTriageAgent(runner).classify(request.text)
    except Exception as exc:
        raise HTTPException(502, f"Agent run failed: {exc}") from exc
    consequence = None
    if result.injection_detected:
        deal = Deal("simulated", "brand", "Simulated account", "Simulated contact")
        decision = PolicyEngine().evaluate(Action(ActionType.SEND_CONTRACT, deal.id, {"injection_detected": True}), deal, pack_or_404("brand"))
        consequence = {"decision": decision.decision, "reason": decision.reason}
    return {"result": result.model_dump(), "runner": label, "tools": [t.__name__ for t in TOOL_SCOPES["reply_triage"]],
            "wrapped": wrap_untrusted_content(request.text, "inbound_email"), "consequence": consequence}


@router.post("/lab/call")
async def lab_call(request: TextRequest):
    pack = pack_or_404(request.segment)
    runner, label = lab_runner(Settings())
    try:
        digest = await CallIntelligenceAgent(runner).digest(request.text, pack.qualification_fields)
    except Exception as exc:
        raise HTTPException(502, f"Agent run failed: {exc}") from exc
    missing = [name for name in pack.qualification_fields if not digest.qualification_fields.get(name)]
    return {"digest": digest.model_dump(), "runner": label, "required": pack.qualification_fields,
            "missing": missing, "exit_criteria_met": not missing}


@router.post("/lab/io")
def lab_io(request: IORequest):
    pack = pack_or_404(request.segment)
    draft = IODraft(legal_entity=request.legal_entity, budget=request.budget, start_date=request.start_date,
                    end_date=request.end_date, line_items=request.line_items)
    errors = validate_io(draft.as_io_data())
    rendered = "" if errors else TemplateRenderer(ROOT / "packs").render(
        f"{pack.segment}/{pack.templates.contract}", {**draft.model_dump(), "line_items": draft.line_items})
    return {"errors": errors, "rendered": rendered, "template": f"packs/{pack.segment}/{pack.templates.contract}"}


@router.post("/lab/io/submit")
def lab_io_submit(request: IORequest):
    result = lab_io(request)
    if result["errors"]:
        raise HTTPException(400, "Fix validation errors before requesting signature.")
    settings = Settings()
    store = SQLiteStore(settings.database_url)
    try:
        deal = store.get_deal(request.deal_id)
        if deal is None:
            raise HTTPException(404, "Choose a deal from the pipeline. Run the demo pipeline first if it is empty.")
        if store.get_approval(f"approval:send_contract:{deal.id}"):
            raise HTTPException(409, "A contract approval already exists for this deal. Review it in the Approval center.")
        payload = {"document": result["rendered"], **request.model_dump(exclude={"deal_id", "segment"})}
        decision = route_action(store, Action(ActionType.SEND_CONTRACT, deal.id, payload), deal, pack_or_404(deal.segment))
        return {"decision": decision, "message": f"Policy decision: {decision}. "
                + ("The contract is waiting in the Approval center." if decision == "REQUIRE_APPROVAL" else "No approval was created.")}
    finally:
        store.connection.close()


def require_demo():
    settings = Settings()
    if not settings.demo_enabled or settings.app_env.lower() == "production":
        raise HTTPException(403, "Fixture seeding and workspace reset are disabled in production.")


@router.post("/demo/run", dependencies=[Depends(require_demo)])
async def demo_run():
    settings = Settings()
    runner, label = lab_runner(settings)
    recipient = next((v.strip() for v in settings.mail_allowed_recipients.split(",") if v.strip()), None)
    store = SQLiteStore(settings.database_url)
    try:
        lines = await run_pipeline(store, runner, ROOT, recipient)
    except Exception as exc:
        raise HTTPException(502, f"Pipeline run failed: {exc}") from exc
    finally:
        store.connection.close()
    return {"runner": label, "lines": lines, "message": f"Pipeline run complete ({label})."}


@router.post("/demo/reset", dependencies=[Depends(require_demo)])
def demo_reset(request: ResetRequest):
    if request.confirm != "RESET":
        raise HTTPException(400, "Type RESET to confirm.")
    store = SQLiteStore(Settings().database_url)
    try:
        with store.connection:
            for table in ("deals", "events", "approvals", "outbox", "audit_log", "lessons", "system_flags", "timers"):
                store.connection.execute(f"DELETE FROM {table}")
    finally:
        store.connection.close()
    return {"message": "Workspace cleared. Run the demo pipeline to repopulate it."}

