"""Conservative boundary for unattended, non-commercial outreach.

This is a deterministic backstop, not a claim to understand every legal promise.
Agents must also follow the versioned non-commercial drafting instructions.
"""

import re

COMMERCIAL = re.compile(
    r"[$€£¥]|\b(?:USD|EUR|GBP|ETB)\b|\b\d+(?:[.,]\d+)?\s*(?:%|dollars?|euros?|birr)"
    r"|\b(?:price|pricing|budget|discount|commission|revenue.share|payment|contract|agreement|guarantee[ds]?)\b",
    re.IGNORECASE,
)


def outreach_error(payload: dict) -> str | None:
    recipient = payload.get("recipient")
    if not isinstance(recipient, str) or recipient.count("@") != 1 or any(c.isspace() for c in recipient):
        return "A valid contact email is required for automatic outreach"
    if not isinstance(payload.get("subject"), str) or not payload["subject"].strip() or not isinstance(payload.get("body"), str) or not payload["body"].strip():
        return "Automatic outreach requires a subject and body"
    if COMMERCIAL.search(payload["subject"] + "\n" + payload["body"]):
        return "Routine messages cannot quote prices, discounts, commercial terms or guarantees; use the human-reviewed contract"
    return None
