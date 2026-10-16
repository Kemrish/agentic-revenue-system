from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from math import isfinite


@dataclass(frozen=True)
class IOData:
    legal_entity: str
    budget: float
    start_date: date
    end_date: date
    line_items: list[dict[str, float | int | str]]
    date_error: str | None = None


def validate_io(data: IOData) -> list[str]:
    errors: list[str] = []
    if data.date_error:
        errors.append(data.date_error)
    if not data.legal_entity.strip():
        errors.append("legal_entity is required")
    if not isfinite(data.budget) or data.budget <= 0:
        errors.append("budget must be positive")
    if data.start_date >= data.end_date:
        errors.append("start_date must be before end_date")
    if not data.line_items:
        errors.append("at least one line item is required")
    if any(not isinstance(item.get("name"), str) or not item["name"].strip() for item in data.line_items):
        errors.append("each line item requires a name")
    try:
        amounts = [float(item.get("amount", 0)) for item in data.line_items]
    except (TypeError, ValueError):
        return errors + ["line item amounts must be numeric"]
    if any(not isfinite(amount) or amount <= 0 for amount in amounts):
        errors.append("line item amounts must be finite and positive")
    if isfinite(data.budget) and all(isfinite(amount) for amount in amounts):
        try:
            values = [Decimal(str(value)) for value in [data.budget, *amounts]]
            if any(value != value.quantize(Decimal("0.01")) for value in values):
                errors.append("USD amounts must use at most two decimal places")
            if sum(values[1:]) != values[0]:
                errors.append("line items must sum to budget")
        except InvalidOperation:
            errors.append("monetary values are outside the supported precision")
    return errors

