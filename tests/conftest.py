"""Tests never inherit the operator's live database or enabled provider modes."""

import pytest


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    defaults = {
        "APP_ENV": "test", "DATABASE_URL": f"sqlite:///{tmp_path / 'isolated.db'}",
        "RUNTIME_MODE": "test", "CLAUDE_MODE": "test", "LLM_PROVIDER": "replay",
        "MAIL_MODE": "test", "ESIGN_MODE": "test", "HUBSPOT_MODE": "test", "FIREFLIES_MODE": "test",
        "LIVE_SIDE_EFFECTS_ENABLED": "false", "DASHBOARD_PASSWORD": "", "WEBHOOK_SECRET": "",
        "HUBSPOT_CLIENT_SECRET": "", "RESEND_WEBHOOK_SECRET": "", "FIREFLIES_WEBHOOK_SECRET": "",
        "CRM_SYNC_ENABLED": "false", "PACKS_ROOT": "", "MAIL_THREAD_SECRET": "", "MAIL_REPLY_DOMAIN": "",
    }
    for name, value in defaults.items():
        monkeypatch.setenv(name, value)

