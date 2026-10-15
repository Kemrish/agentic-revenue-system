import asyncio
import json
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from revenue_system.governance.provider_security import reply_token

from .errors import AmbiguousDeliveryError


class MailAdapter:
    def __init__(self, api_key: str, from_address: str, base_url: str = "https://api.resend.com", allowed_recipients: set[str] | None = None, live_side_effects_enabled: bool = False, reply_domain: str = "", thread_secret: str = "") -> None:
        self.api_key = api_key
        self.from_address = from_address
        self.base_url = base_url.rstrip("/")
        self.allowed_recipients = allowed_recipients or set()
        self.live_side_effects_enabled = live_side_effects_enabled
        self.reply_domain = reply_domain
        self.thread_secret = thread_secret

    async def send(self, recipient: str, subject: str, body: str, idempotency_key: str) -> str:
        return await asyncio.to_thread(self._send, recipient, subject, body, idempotency_key)

    def _send(self, recipient: str, subject: str, body: str, idempotency_key: str) -> str:
        if not self.live_side_effects_enabled:
            raise PermissionError("Live mail is disabled; set LIVE_SIDE_EFFECTS_ENABLED=true explicitly")
        if recipient not in self.allowed_recipients:
            raise PermissionError(f"Recipient is not on the mail allowlist: {recipient}")
        message = {"from": self.from_address, "to": [recipient], "subject": subject, "text": body}
        if self.reply_domain:
            message["reply_to"] = f"reply+{reply_token(idempotency_key, self.thread_secret)}@{self.reply_domain}"
        request = Request(
            f"{self.base_url}/emails",
            data=json.dumps(message).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "Idempotency-Key": idempotency_key, "User-Agent": "agentic-revenue-system/0.1"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Mail provider rejected request ({exc.code}): {detail}") from exc
        provider_id = payload.get("id")
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise AmbiguousDeliveryError("Mail provider response omitted its delivery reference; reconcile before retry")
        return provider_id

    async def get_received(self, email_id: str) -> dict:
        return await asyncio.to_thread(self._get_received, email_id)

    def _get_received(self, email_id: str) -> dict:
        request = Request(f"{self.base_url}/emails/receiving/{quote(str(email_id), safe='')}",
                          headers={"Authorization": f"Bearer {self.api_key}"})
        with urlopen(request, timeout=15) as response:
            body = json.loads(response.read())
        if not body.get("text"):
            raise ValueError("Received email has no plain-text body; manual review required")
        return body

