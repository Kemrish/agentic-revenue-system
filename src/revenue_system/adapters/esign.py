import json
from urllib.request import Request, urlopen


class ESignAdapter:
    def __init__(self, api_key: str, base_url: str, live_side_effects_enabled: bool = False) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.live_side_effects_enabled = live_side_effects_enabled

    async def send_for_signature(self, document: str, idempotency_key: str) -> str:
        if not self.live_side_effects_enabled:
            raise PermissionError("Live e-sign is disabled; set LIVE_SIDE_EFFECTS_ENABLED=true explicitly")
        request = Request(
            f"{self.base_url}/envelopes",
            data=json.dumps({"document": document}).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "Idempotency-Key": idempotency_key},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read())
        return str(payload.get("envelope_id", idempotency_key))

