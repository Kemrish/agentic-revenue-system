"""Recorded agent responses used when no live model is configured."""

DEMO_RESPONSES = {
    "reply_triage": {"label": "interested", "confidence": 0.96, "summary": "Requested a meeting"},
    "call_intelligence": {
        "qualification_fields": {"budget": "250000", "timeline": "90 days", "decision_maker": "VP Marketing"},
        "objections": [], "next_steps": ["prepare IO"],
        "lesson_candidate": "Measurement proof improves campaign conversations.",
    },
    "deal_desk": {"legal_entity": "Example Foods", "budget": 250000, "start_date": "2026-11-01",
                  "end_date": "2027-01-31", "line_items": [{"name": "Activate", "amount": 250000}]},
}
