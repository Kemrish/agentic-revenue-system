import asyncio
import json
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class HubSpotAdapter:
    """Minimal property-level HubSpot adapter; no whole-object overwrites."""

    def __init__(self, access_token: str, base_url: str = "https://api.hubapi.com") -> None:
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")

    def update_properties(self, object_type: str, object_id: str, properties: dict[str, str], source: str) -> str:
        payload = {"properties": properties}
        request = Request(
            f"{self.base_url}/crm/v3/objects/{object_type}/{object_id}",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
            method="PATCH",
        )
        try:
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read())
            if str(result.get("id", "")) != str(object_id):
                raise RuntimeError("HubSpot update omitted the expected object reference")
            return str(result["id"])
        except HTTPError as exc:
            raise RuntimeError(f"HubSpot update failed with status {exc.code}") from exc

    async def get_contact(self, contact_id: str, property_names: list[str]) -> dict:
        return await asyncio.to_thread(self._get_contact, contact_id, property_names)

    def _get_contact(self, contact_id: str, property_names: list[str]) -> dict:
        query = urlencode({"properties": ",".join(property_names)})
        request = Request(f"{self.base_url}/crm/v3/objects/contacts/{quote(str(contact_id), safe='')}?{query}",
                          headers={"Authorization": f"Bearer {self.access_token}"})
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read())
        if str(result.get("id", "")) != str(contact_id) or not isinstance(result.get("properties"), dict):
            raise ValueError("HubSpot did not return the requested contact")
        return result["properties"]

