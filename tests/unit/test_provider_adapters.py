import json
from contextlib import contextmanager

import httpx
import pytest

from revenue_system.adapters.esign import DropboxSignAdapter
from revenue_system.adapters.fireflies import FirefliesAdapter
from revenue_system.adapters.mail import MailAdapter
from revenue_system.skills.contracts import validate_contract
from tests.unit.test_contract_integrity import contract


@pytest.mark.asyncio
async def test_signature_upload_contains_exact_reviewed_bytes_and_signer(monkeypatch):
    payload = contract()
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            assert url.endswith("/v3/signature_request/send")
            assert kwargs["files"]["files[0]"][1] == validate_contract(payload)
            assert kwargs["data"]["signers[0][email_address]"] == payload["signer_email"]
            assert "file_urls[]" not in kwargs["data"]
            assert kwargs["data"]["metadata[artifact_sha256]"] == payload["artifact_sha256"]
            return httpx.Response(200, json={"signature_request": {"signature_request_id": "request-1"}})
    monkeypatch.setattr("revenue_system.adapters.esign.httpx.Client", Client)
    adapter = DropboxSignAdapter("key", "https://api.hellosign.com", document_url="https://wrong.example.com",
                                  signer_email="wrong@example.com", live_side_effects_enabled=True,
                                  allowed_recipients={payload["signer_email"]})
    assert await adapter.send_for_signature(payload, "action-1") == "request-1"
    adapter.allowed_recipients = set()
    with pytest.raises(PermissionError, match="ESIGN_ALLOWED"):
        await adapter.send_for_signature(payload, "action-2")


def test_fireflies_uses_graphql_variables_and_rejects_graphql_errors(monkeypatch):
    response = {"data": {"transcript": {"id": "t1", "sentences": [{"speaker_name": "Amina", "text": "Evidence"}]}}}
    @contextmanager
    def urlopen(request, **kwargs):
        assert request.full_url == "https://api.fireflies.ai/graphql" and request.method == "POST"
        assert json.loads(request.data)["variables"] == {"id": "t1"}
        class Result:
            def read(self):
                return json.dumps(response).encode()
        yield Result()
    monkeypatch.setattr("revenue_system.adapters.fireflies.urlopen", urlopen)
    adapter = FirefliesAdapter("key")
    assert adapter._get_transcript("t1") == "Amina: Evidence"
    response = {"errors": [{"message": "Denied"}]}
    with pytest.raises(RuntimeError, match="GraphQL"):
        adapter._get_transcript("t1")


def test_mail_missing_provider_reference_is_not_success(monkeypatch):
    @contextmanager
    def urlopen(*args, **kwargs):
        class Result:
            def read(self):
                return b"{}"
        yield Result()
    monkeypatch.setattr("revenue_system.adapters.mail.urlopen", urlopen)
    adapter = MailAdapter("key", "sender@example.com", allowed_recipients={"a@example.com"}, live_side_effects_enabled=True)
    with pytest.raises(RuntimeError, match="reference"):
        adapter._send("a@example.com", "Subject", "Body", "action-1")
