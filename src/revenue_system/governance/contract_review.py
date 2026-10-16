"""The sole normal human checkpoint: sensitive terms -> exact version -> approval."""

import json

from pydantic import BaseModel, ConfigDict, Field

from revenue_system.adapters.db import SQLiteStore
from revenue_system.agents.deal_desk import IODraft
from revenue_system.segments.paths import packs_path
from revenue_system.segments.registry import PackRegistry
from revenue_system.skills.contracts import bind_contract, validate_contract
from revenue_system.skills.templating import TemplateRenderer


class ContractEdit(IODraft):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    legal_entity: str = Field(min_length=1, max_length=500)
    line_items: list[dict[str, float | int | str]] = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)
    signer_email: str = Field(min_length=3, max_length=254)
    signer_name: str = Field(min_length=1, max_length=300)
    additional_terms: str = Field(default="", max_length=10000)


class ContractApproval(BaseModel):
    revision: int = Field(ge=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def render_reviewed_contract(terms: dict, segment: str, root=None, additional_terms: str = "") -> str:
    root = packs_path(root)
    pack = PackRegistry(root).get(segment)
    text = TemplateRenderer(root).render(f"{segment}/{pack.templates.contract}", terms)
    if additional_terms.strip():
        text += "\n\n## Human-supplied additional terms\n\n" + additional_terms.strip()
    return text


def edit_contract(store: SQLiteStore, approval_id: str, changes: ContractEdit, actor: str, root=None) -> dict:
    """Compare-and-set keeps two operators from overwriting each other's edits."""
    with store.transaction():
        row = store.get_approval(approval_id)
        if not row or row["action_type"] != "send_contract" or row["status"] != "pending":
            raise ValueError("Only a pending contract can be edited")
        previous = json.loads(row["payload"])
        revision = int(previous.get("revision", 1))
        if revision != changes.expected_revision:
            raise ValueError("Contract changed since you opened it; reload and review the current version")
        deal = store.get_deal(row["deal_id"])
        if not deal or deal.stage != "proposal":
            raise ValueError("Contract edits require an existing deal in proposal stage")
        if previous.get("unsafe") or previous.get("injection_detected") or set(deal.flags) & {"do_not_contact", "suspicious_reply"}:
            raise ValueError("Blocked contracts cannot be edited into deliverable actions")
        terms = IODraft.model_validate(changes.model_dump()).model_dump()
        terms["legal_entity"] = terms["legal_entity"].strip()
        document = render_reviewed_contract(terms, deal.segment, root, changes.additional_terms)
        updated = bind_contract(previous | terms | {"document": document, "revision": revision + 1,
            "review_status": "ready", "review_errors": [], "additional_terms": changes.additional_terms,
            "terms_source": actor}, changes.signer_email.strip(), changes.signer_name.strip())
        validate_contract(updated)
        saved = store.connection.execute("UPDATE approvals SET payload=? WHERE id=? AND status='pending' AND payload=?",
                                         (json.dumps(updated), approval_id, row["payload"]))
        if saved.rowcount != 1:
            raise ValueError("Contract changed concurrently; reopen the review")
        store.connection.execute("INSERT OR IGNORE INTO contract_revisions VALUES(?,?,?,?,datetime('now'))",
                                 (approval_id, revision, row["payload"], "system:previous_version"))
        store.connection.execute("INSERT INTO contract_revisions VALUES(?,?,?,?,datetime('now'))",
                                 (approval_id, revision + 1, json.dumps(updated), actor))
        deal.fields["commercial_terms"] = terms
        store.save_deal(deal)
        store.audit(actor, "contract_edited", f"{approval_id} revision={revision + 1} sha256={updated['artifact_sha256']}; fresh approval required", deal.id)
    return updated


def verify_human_authorization(store: SQLiteStore, payload: dict, deal_id: str) -> None:
    evidence = payload.get("human_approval") or {}
    row = store.get_approval(evidence.get("approval_id", ""))
    without_evidence = {key: value for key, value in payload.items() if key != "human_approval"}
    if not row or row["status"] != "approved" or row["action_type"] != "send_contract" or row["deal_id"] != deal_id:
        raise ValueError("Contract has no matching human approval")
    if json.loads(row["payload"]) != without_evidence or evidence.get("revision") != payload.get("revision", 1) or evidence.get("artifact_sha256") != payload.get("artifact_sha256"):
        raise ValueError("Contract or signer changed after human approval; a new review is required")
