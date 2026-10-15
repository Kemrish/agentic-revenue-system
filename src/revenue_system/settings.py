"""Application settings and per-integration runtime modes."""

import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RuntimeMode = Literal["live", "record", "replay", "test"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=os.environ.get("ARS_ENV_FILE", ".env"), extra="ignore")

    app_env: str = "development"
    runtime_mode: RuntimeMode = "replay"
    database_url: str = "sqlite:///./revenue_system.db"
    packs_root: Path | None = None
    claude_mode: RuntimeMode = "replay"
    anthropic_api_key: str = ""
    llm_provider: str = "replay"
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-haiku-5.5"
    hubspot_mode: RuntimeMode = "replay"
    mail_mode: RuntimeMode = "replay"
    fireflies_mode: RuntimeMode = "replay"
    esign_mode: RuntimeMode = "replay"
    hubspot_access_token: str = ""
    hubspot_client_secret: str = ""
    hubspot_segment_property: str = "ars_segment"
    hubspot_fit_property: str = "ars_fit"
    hubspot_intent_property: str = "ars_intent"
    hubspot_score_property: str = "ars_score"
    hubspot_stage_property: str = "ars_stage"
    crm_sync_enabled: bool = False
    public_webhook_url: str = ""
    resend_webhook_secret: str = ""
    fireflies_webhook_secret: str = ""
    mail_reply_domain: str = ""
    mail_thread_secret: str = ""
    mail_api_key: str = ""
    mail_from_address: str = ""
    fireflies_api_key: str = ""
    esign_api_key: str = ""
    esign_base_url: str = "https://api.hellosign.com"
    esign_document_url: str = ""
    esign_signer_email: str = ""
    esign_signer_name: str = ""
    esign_test_mode: bool = True
    esign_allowed_recipients: str = ""
    webhook_secret: str = ""
    dashboard_username: str = "operator"
    dashboard_password: str = ""
    worker_poll_seconds: float = Field(default=5.0, gt=0, le=3600)
    max_event_attempts: int = Field(default=5, ge=1, le=100)
    max_delivery_attempts: int = Field(default=5, ge=1, le=100)
    retry_base_seconds: float = Field(default=5, ge=0, le=3600)
    queue_lease_seconds: int = Field(default=300, ge=60, le=3600)
    webhook_max_bytes: int = Field(default=1048576, ge=1024, le=10485760)
    live_side_effects_enabled: bool = False
    mail_allowed_recipients: str = ""

    @field_validator("packs_root", mode="before")
    @classmethod
    def empty_pack_override(cls, value):
        return None if value == "" else value

