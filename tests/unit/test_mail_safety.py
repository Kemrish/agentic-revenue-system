import pytest

from revenue_system.adapters.mail import MailAdapter


@pytest.mark.asyncio
async def test_live_mail_requires_explicit_opt_in_and_allowlist():
    adapter = MailAdapter("key", "from@example.com", allowed_recipients={"approved@example.com"})
    with pytest.raises(PermissionError):
        await adapter.send("approved@example.com", "subject", "body", "k1")

    adapter = MailAdapter("key", "from@example.com", allowed_recipients={"approved@example.com"}, live_side_effects_enabled=True)
    with pytest.raises(PermissionError):
        await adapter.send("other@example.com", "subject", "body", "k2")

