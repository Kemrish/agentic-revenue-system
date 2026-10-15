import pytest

from revenue_system.adapters.esign import DropboxSignAdapter


@pytest.mark.asyncio
async def test_dropbox_sign_requires_configuration():
    adapter = DropboxSignAdapter("key", "https://api.hellosign.com", "", "", "", True)
    with pytest.raises(ValueError, match="reviewed contract"):
        await adapter.send_for_signature("demo", "id-1")
