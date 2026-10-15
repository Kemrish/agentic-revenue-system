import base64
import hashlib
from io import BytesIO
from zipfile import ZipFile

import pytest

from revenue_system.agents.deal_desk import IODraft, repair_from_supplied_data
from revenue_system.skills.contracts import bind_contract, validate_contract

TERMS = {"legal_entity": "Approved Entity", "budget": 1000, "start_date": "2026-11-01",
         "end_date": "2027-01-31", "line_items": [{"name": "Service", "amount": 1000}]}


def contract():
    return bind_contract(TERMS | {"document": "Approved Entity\nAgreement: 1,000.00\nሰላም & <terms>"}, "signer@example.com", "Amina")


def test_upstream_terms_override_nonempty_model_inventions():
    invented = TERMS | {"legal_entity": "Wrong Entity", "start_date": "2030-01-01", "end_date": "2031-01-01", "budget": 2}
    assert repair_from_supplied_data(IODraft(**invented), TERMS).model_dump() == TERMS


def test_absent_upstream_terms_never_accept_invented_values():
    result = repair_from_supplied_data(IODraft(**TERMS), {})
    assert result.legal_entity == "" and result.budget == 0 and result.start_date == "" and result.line_items == []


def test_docx_is_reproducible_and_preserves_reviewed_text():
    payload = contract()
    assert payload == contract()
    with ZipFile(BytesIO(validate_contract(payload))) as archive:
        xml = archive.read("word/document.xml").decode()
        assert "ሰላም &amp; &lt;terms&gt;" in xml


@pytest.mark.parametrize("updates", [{"document": "Replacement"}, {"artifact_sha256": "wrong"}, {"signer_email": ""}])
def test_tampered_or_incomplete_contract_is_blocked(updates):
    with pytest.raises(ValueError):
        validate_contract(contract() | updates)


def test_rehashed_replacement_file_still_fails_text_comparison():
    replacement = b"another document"
    with pytest.raises(ValueError, match="differs"):
        validate_contract(contract() | {"artifact_base64": base64.b64encode(replacement).decode(),
                                       "artifact_sha256": hashlib.sha256(replacement).hexdigest()})
