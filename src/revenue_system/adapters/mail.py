import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class MailAdapter:
    def __init__(self, api_key: str, from_address: str, base_url: str = "https://api.resend.com", allowed_recipients: set[str] | None = None, live_side_effects_enabled: bool = False) -> None:
        self.api_key = api_key
        self.from_address = from_address
        self.base_url = base_url.rstrip("/")
        self.allowed_recipients = allowed_recipients or set()
        self.live_side_effects_enabled = live_side_effects_enabled

    async def send(self, recipient: str, subject: str, body: str, idempotency_key: str) -> str:
        if not self.live_side_effects_enabled:
            raise PermissionError("Live mail is disabled; set LIVE_SIDE_EFFECTS_ENABLED=true explicitly")
        if recipient not in self.allowed_recipients:
            raise PermissionError(f"Recipient is not on the mail allowlist: {recipient}")
        request = Request(
            f"{self.base_url}/emails",
            data=json.dumps({"from": self.from_address, "to": [recipient], "subject": subject, "text": body}).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "Idempotency-Key": idempotency_key, "User-Agent": "agentic-revenue-system/0.1"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Mail provider rejected request ({exc.code}): {detail}") from exc
        return str(payload.get("id", idempotency_key))

