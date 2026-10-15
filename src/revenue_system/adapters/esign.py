import asyncio

import httpx

from revenue_system.skills.contracts import DOCX_TYPE, validate_contract

from .errors import AmbiguousDeliveryError


class DropboxSignAdapter:
    def __init__(self, api_key: str, base_url: str, document_url: str = "", signer_email: str = "", signer_name: str = "", live_side_effects_enabled: bool = False, test_mode: bool = True, allowed_recipients: set[str] | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        # Legacy arguments are accepted but never substitute reviewed content.
        self.allowed_recipients = allowed_recipients or set()
        self.live_side_effects_enabled = live_side_effects_enabled
        self.test_mode = test_mode

    async def send_for_signature(self, document: dict, idempotency_key: str) -> str:
        return await asyncio.to_thread(self._send_for_signature, document, idempotency_key)

    def _send_for_signature(self, document: dict, idempotency_key: str) -> str:
        if not self.live_side_effects_enabled:
            raise PermissionError("Live e-sign is disabled; set LIVE_SIDE_EFFECTS_ENABLED=true explicitly")
        artifact = validate_contract(document)
        if document["signer_email"] not in self.allowed_recipients:
            raise PermissionError("Signer is not on ESIGN_ALLOWED_RECIPIENTS")
        fields = {
            "title": "Revenue agreement",
            "subject": "Please review and sign your agreement",
            "message": "Review the agreement and complete the requested signature fields.",
            "signers[0][email_address]": document["signer_email"],
            "signers[0][name]": document["signer_name"],
            "signers[0][order]": "0",
            "metadata[action_id]": idempotency_key,
            "metadata[artifact_sha256]": document["artifact_sha256"],
            "test_mode": "1" if self.test_mode else "0",
        }
        try:
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                response = client.post(f"{self.base_url}/v3/signature_request/send", auth=(self.api_key, ""), data=fields,
                                       files={"files[0]": ("agreement.docx", artifact, DOCX_TYPE)})
        except httpx.TransportError as exc:
            raise AmbiguousDeliveryError("E-sign transport failure; inspect provider history before retry") from exc
        if response.status_code >= 500:
            raise AmbiguousDeliveryError("E-sign provider failed; inspect provider history before retry")
        if response.is_error:
            raise RuntimeError(f"Dropbox Sign rejected request ({response.status_code})")
        try:
            provider_id = response.json()["signature_request"]["signature_request_id"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AmbiguousDeliveryError("E-sign response omitted its reference; reconcile before retry") from exc
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise AmbiguousDeliveryError("E-sign response omitted its reference; reconcile before retry")
        return provider_id

    async def verify_completed(self, provider_id: str) -> bool:
        # Callback hashes cover time/type, not the entire envelope body.
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(f"{self.base_url}/v3/signature_request/{provider_id}", auth=(self.api_key, ""))
            response.raise_for_status()
            result = response.json().get("signature_request", {})
        return result.get("signature_request_id") == provider_id and result.get("is_complete") is True


# Backward-compatible name for callers that only exercise the safety gate.
class ESignAdapter(DropboxSignAdapter):
    def __init__(self, api_key: str, base_url: str, live_side_effects_enabled: bool = False) -> None:
        super().__init__(api_key, base_url, "", "", "", live_side_effects_enabled)

