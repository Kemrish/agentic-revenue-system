"""Application settings and per-integration runtime modes."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

RuntimeMode = Literal["live", "record", "replay", "test"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    runtime_mode: RuntimeMode = "replay"
    database_url: str = "sqlite:///./revenue_system.db"
    claude_mode: RuntimeMode = "replay"
    hubspot_mode: RuntimeMode = "replay"
    mail_mode: RuntimeMode = "replay"
    fireflies_mode: RuntimeMode = "replay"
    esign_mode: RuntimeMode = "replay"
    hubspot_access_token: str = ""
    mail_api_key: str = ""
    mail_from_address: str = "demo@example.invalid"
    fireflies_api_key: str = ""
    esign_api_key: str = ""
    esign_base_url: str = "https://api.example.invalid"

