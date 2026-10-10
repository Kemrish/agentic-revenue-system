from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class IOData:
    legal_entity: str
    budget: float
    start_date: date
    end_date: date
    line_items: list[dict[str, float | str]]
    date_error: str | None = None


def validate_io(data: IOData) -> list[str]:
    errors: list[str] = []
    if data.date_error:
        errors.append(data.date_error)
    if not data.legal_entity.strip():
        errors.append("legal_entity is required")
    if data.budget <= 0:
        errors.append("budget must be positive")
    if data.start_date >= data.end_date:
        errors.append("start_date must be before end_date")
    if not data.line_items:
        errors.append("at least one line item is required")
    total = sum(float(item.get("amount", 0)) for item in data.line_items)
    if round(total, 2) != round(data.budget, 2):
        errors.append("line items must sum to budget")
    return errors

