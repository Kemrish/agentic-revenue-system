import json
from urllib.request import Request, urlopen


class ESignAdapter:
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def send_for_signature(self, document: str, idempotency_key: str) -> str:
        request = Request(
            f"{self.base_url}/envelopes",
            data=json.dumps({"document": document}).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "Idempotency-Key": idempotency_key},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read())
        return str(payload.get("envelope_id", idempotency_key))

