import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class HubSpotAdapter:
    """Minimal property-level HubSpot adapter; no whole-object overwrites."""

    def __init__(self, access_token: str, base_url: str = "https://api.hubapi.com") -> None:
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")

    def update_properties(self, object_type: str, object_id: str, properties: dict[str, str], source: str) -> None:
        payload = {"properties": {**properties, "ars_last_update_source": source}}
        request = Request(
            f"{self.base_url}/crm/v3/objects/{object_type}/{object_id}",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
            method="PATCH",
        )
        try:
            with urlopen(request, timeout=15):
                return
        except HTTPError as exc:
            raise RuntimeError(f"HubSpot update failed with status {exc.code}") from exc

