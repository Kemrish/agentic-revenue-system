import pytest

from revenue_system.adapters.esign import ESignAdapter


@pytest.mark.asyncio
async def test_esign_requires_explicit_side_effect_opt_in():
    adapter = ESignAdapter("key", "https://example.invalid")
    with pytest.raises(PermissionError):
        await adapter.send_for_signature("document", "idempotency-1")
