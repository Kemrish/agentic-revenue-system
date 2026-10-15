import json
import asyncio
from urllib.request import Request, urlopen


class FirefliesAdapter:
    def __init__(self, api_key: str, base_url: str = "https://api.fireflies.ai") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def get_transcript(self, transcript_id: str) -> str:
        return await asyncio.to_thread(self._get_transcript, transcript_id)

    def _get_transcript(self, transcript_id: str) -> str:
        request = Request(f"{self.base_url}/transcript/{transcript_id}", headers={"Authorization": f"Bearer {self.api_key}"})
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read())
        return str(payload.get("transcript", payload.get("text", "")))

