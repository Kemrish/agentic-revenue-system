from datetime import date

from revenue_system.agents.deal_desk import IODraft, repair_from_supplied_data
from revenue_system.skills.io_validation import IOData, validate_io


def test_valid_io_passes():
    data = IOData("Example Foods", 1000, date(2026, 11, 1), date(2026, 12, 1), [{"name": "Activate", "amount": 1000}])
    assert validate_io(data) == []


def test_invalid_io_reports_arithmetic_error():
    data = IOData("Example Foods", 1000, date(2026, 11, 1), date(2026, 12, 1), [{"name": "Activate", "amount": 900}])
    assert "line items must sum to budget" in validate_io(data)


def test_io_repair_only_uses_supplied_values():
    draft = IODraft(legal_entity="", budget=0, start_date="", end_date="", line_items=[])
    repaired = repair_from_supplied_data(draft, {"legal_entity": "Acme", "budget": 10, "start_date": "2026-01-01", "end_date": "2026-02-01", "line_items": [{"name": "x", "amount": 10}]})
    assert repaired.legal_entity == "Acme"
    assert repaired.budget == 10
    assert repaired.line_items[0]["amount"] == 10

