"""Resolve durable authenticated notifications; all network failures are retried by the worker."""

import json
import re
from email.utils import parseaddr

from revenue_system.governance.ingress import LeadInput, ReplyInput, TranscriptInput
from revenue_system.governance.provider_security import reply_token
from revenue_system.orchestration.events import DomainEvent


class ProviderEventResolver:
    def __init__(self, container):
        self.container = container

    async def resolve(self, event: DomainEvent) -> DomainEvent:
        c, payload = self.container, event.payload
        s, store = c.settings, c.store
        if event.event_type == "provider.hubspot.contact":
            if c.crm is None:
                raise ValueError("Live HubSpot adapter is not configured")
            contact_id = str(payload["contact_id"])
            fields = await c.crm.get_contact(contact_id, ["company", "firstname", "lastname", "email",
                                                         s.hubspot_segment_property, s.hubspot_fit_property, s.hubspot_intent_property])
            # Missing evidence is not invented by the model or defaulted to a high score.
            lead = LeadInput.model_validate({"lead_id": f"hubspot-contact-{contact_id}", "hubspot_contact_id": contact_id,
                "company_name": fields.get("company"), "contact_name": " ".join(filter(None, [fields.get("firstname"), fields.get("lastname")])),
                "email": fields.get("email"), "segment": fields.get(s.hubspot_segment_property),
                "fit": fields.get(s.hubspot_fit_property) or 0, "intent": fields.get(s.hubspot_intent_property) or 0,
                "evidence_source": f"hubspot:contacts:{contact_id}"})
            return DomainEvent("lead.created", event.event_id, lead.model_dump())
        if event.event_type == "provider.fireflies.transcript":
            deal_id = payload.get("deal_id")
            if not deal_id:
                matches = [row["id"] for row in store.connection.execute("SELECT id,payload FROM deals")
                           if json.loads(row["payload"]).get("fields", {}).get("fireflies_transcript_id") == payload["transcript_id"]]
                if len(matches) != 1:
                    raise ValueError("Transcript needs a unique deal link or client_reference_id")
                deal_id = matches[0]
            deal = store.get_deal(deal_id)
            if not deal:
                raise ValueError("Transcript references an unknown deal")
            # Reprocessed notes must not generate another commercial action.
            if payload.get("revision"):
                raise ValueError("Reprocessed transcript requires manual review; original commercial actions are retained")
            text = await c.transcripts.get_transcript(str(payload["transcript_id"]))
            normalized = TranscriptInput(deal_id=deal.id, transcript=text, transcript_id=payload["transcript_id"],
                                         deal_terms=deal.fields.get("commercial_terms", {}))
            return DomainEvent("transcript.ready", event.event_id, normalized.model_dump())
        if event.event_type == "provider.resend.reply":
            received = await c.mail.get_received(str(payload["email_id"]))
            addresses = {parseaddr(address)[1].lower() for address in received.get("to", [])}
            sender = parseaddr(received.get("from", ""))[1].lower()
            if not s.mail_thread_secret or not s.mail_reply_domain:
                raise ValueError("Mail reply correlation is not configured")
            matches = set()
            for row in store.connection.execute("SELECT id,deal_id,payload FROM outbox WHERE status='sent' AND action_type IN ('send_first_touch','send_follow_up')"):
                expected = f"reply+{reply_token(row['id'], s.mail_thread_secret)}@{s.mail_reply_domain}".lower()
                original = json.loads(row["payload"])
                if expected in addresses and sender == str(original.get("recipient", "")).lower():
                    matches.add(row["deal_id"])
            if len(matches) != 1:
                raise ValueError("Reply could not be correlated to one sent message and its recipient")
            reply = ReplyInput(deal_id=matches.pop(), text=received["text"])
            return DomainEvent("reply.received", event.event_id, reply.model_dump())
        if event.event_type == "provider.esign.completed":
            reference = str(payload["provider_id"])
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", reference):
                raise ValueError("Invalid signature request reference")
            matches = store.connection.execute("SELECT DISTINCT deal_id FROM outbox WHERE action_type='send_contract' AND status='sent' AND provider_id=?", (reference,)).fetchall()
            if len(matches) != 1 or not await c.esign.verify_completed(reference):
                raise ValueError("Signature completion is not verified against a sent contract and provider state")
            return DomainEvent("contract.signed", event.event_id, {"deal_id": matches[0]["deal_id"], "provider_id": reference})
        raise ValueError("Unsupported provider event")
