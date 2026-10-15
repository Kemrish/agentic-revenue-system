import json
import asyncio
import base64
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class DropboxSignAdapter:
    def __init__(self, api_key: str, base_url: str, document_url: str, signer_email: str, signer_name: str, live_side_effects_enabled: bool = False, test_mode: bool = True) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.document_url = document_url
        self.signer_email = signer_email
        self.signer_name = signer_name
        self.live_side_effects_enabled = live_side_effects_enabled
        self.test_mode = test_mode

    async def send_for_signature(self, document: str, idempotency_key: str) -> str:
        return await asyncio.to_thread(self._send_for_signature, document, idempotency_key)

    def _send_for_signature(self, document: str, idempotency_key: str) -> str:
        if not self.live_side_effects_enabled:
            raise PermissionError("Live e-sign is disabled; set LIVE_SIDE_EFFECTS_ENABLED=true explicitly")
        if not all((self.document_url, self.signer_email, self.signer_name)):
            raise ValueError("Dropbox Sign requires document URL, signer email, and signer name")
        auth = base64.b64encode(f"{self.api_key}:".encode()).decode()
        fields = urlencode({
            "file_urls[]": self.document_url,
            "title": "Agentic Revenue System demo agreement",
            "subject": "Please review and sign the demo agreement",
            "message": "This is a fictional demo agreement for testing.",
            "signers[0][email_address]": self.signer_email,
            "signers[0][name]": self.signer_name,
            "signers[0][order]": "0",
            "metadata[demo_id]": idempotency_key,
            "test_mode": "1" if self.test_mode else "0",
        }).encode()
        request = Request(
            f"{self.base_url}/v3/signature_request/send",
            data=fields,
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded", "Idempotency-Key": idempotency_key, "User-Agent": "agentic-revenue-system/0.1"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Dropbox Sign rejected request ({exc.code}): {detail}") from exc
        return str(payload.get("signature_request", {}).get("signature_request_id", idempotency_key))


# Backward-compatible name for callers that only exercise the safety gate.
class ESignAdapter(DropboxSignAdapter):
    def __init__(self, api_key: str, base_url: str, live_side_effects_enabled: bool = False) -> None:
        super().__init__(api_key, base_url, "", "", "", live_side_effects_enabled)

