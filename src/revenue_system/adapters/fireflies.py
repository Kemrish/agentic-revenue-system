import asyncio
import json
from urllib.request import Request, urlopen


class FirefliesAdapter:
    def __init__(self, api_key: str, base_url: str = "https://api.fireflies.ai") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def get_transcript(self, transcript_id: str) -> str:
        return await asyncio.to_thread(self._get_transcript, transcript_id)

    def _get_transcript(self, transcript_id: str) -> str:
        query = "query Transcript($id: String!) { transcript(id: $id) { id sentences { speaker_name text } } }"
        request = Request(f"{self.base_url}/graphql", data=json.dumps({"query": query, "variables": {"id": transcript_id}}).encode(),
                          headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read())
        if payload.get("errors"):
            raise RuntimeError("Fireflies GraphQL returned errors; verify access and transcript ID")
        transcript = (payload.get("data") or {}).get("transcript")
        if not isinstance(transcript, dict) or transcript.get("id") != transcript_id:
            raise ValueError("Fireflies did not return the requested transcript")
        sentences = transcript.get("sentences") or []
        text = "\n".join(f"{s.get('speaker_name') or 'Speaker'}: {s['text']}" for s in sentences if s.get("text"))
        if not text.strip():
            raise ValueError("Fireflies transcript is empty or not ready")
        return text

