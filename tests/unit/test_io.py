from datetime import date

from revenue_system.skills.io_validation import IOData, validate_io


def test_valid_io_passes():
    data = IOData("Example Foods", 1000, date(2026, 11, 1), date(2026, 12, 1), [{"name": "Activate", "amount": 1000}])
    assert validate_io(data) == []


def test_invalid_io_reports_arithmetic_error():
    data = IOData("Example Foods", 1000, date(2026, 11, 1), date(2026, 12, 1), [{"name": "Activate", "amount": 900}])
    assert "line items must sum to budget" in validate_io(data)

