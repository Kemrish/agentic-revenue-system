import json
from urllib.request import Request, urlopen


class MailAdapter:
    def __init__(self, api_key: str, from_address: str, base_url: str = "https://api.resend.com") -> None:
        self.api_key = api_key
        self.from_address = from_address
        self.base_url = base_url.rstrip("/")

    async def send(self, recipient: str, subject: str, body: str, idempotency_key: str) -> str:
        request = Request(
            f"{self.base_url}/emails",
            data=json.dumps({"from": self.from_address, "to": [recipient], "subject": subject, "text": body}).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "Idempotency-Key": idempotency_key},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read())
        return str(payload.get("id", idempotency_key))

