"""Composition root shared by the dashboard, CLI, and event worker."""

from dataclasses import dataclass

from .adapters.claude_runner import ClaudeRunner
from .adapters.db import SQLiteStore
from .adapters.esign import DropboxSignAdapter
from .adapters.fireflies import FirefliesAdapter
from .adapters.disabled import DisabledIntegration
from .adapters.hubspot import HubSpotAdapter
from .adapters.mail import MailAdapter
from .adapters.openrouter_runner import OpenRouterRunner
from .agents.execution import DisabledRunner, ValidatingRunner
from .settings import Settings


@dataclass(frozen=True)
class Container:
    settings: Settings
    store: SQLiteStore
    runner: object
    mail: object
    transcripts: object
    esign: object
    crm: object


def agent_runner(settings: Settings):
    """Use the same model selection in every entry point; never label fake output live."""
    if settings.runtime_mode == "live" and settings.claude_mode == "live":
        if settings.llm_provider == "openrouter":
            if not settings.openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY is required for the live OpenRouter runner")
            return ValidatingRunner(OpenRouterRunner(settings.openrouter_api_key, settings.openrouter_model)), "live · openrouter"
        if settings.llm_provider in {"claude", "anthropic"}:
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is required for the live Claude runner")
            return ValidatingRunner(ClaudeRunner(api_key=settings.anthropic_api_key)), "live · claude"
        raise ValueError("Set LLM_PROVIDER to openrouter, claude, or anthropic for a live model")
    return DisabledRunner(), "disabled"


def build_container(settings: Settings | None = None) -> Container:
    selected = settings or Settings()
    live = selected.runtime_mode == "live"
    runner, _ = agent_runner(selected)
    return Container(
        settings=selected,
        store=SQLiteStore(selected.database_url),
        runner=runner,
        mail=MailAdapter(
            selected.mail_api_key, selected.mail_from_address,
            allowed_recipients={v.strip() for v in selected.mail_allowed_recipients.split(",") if v.strip()},
            live_side_effects_enabled=selected.live_side_effects_enabled,
        ) if live and selected.mail_mode == "live" else DisabledIntegration("Mail"),
        transcripts=FirefliesAdapter(selected.fireflies_api_key) if live and selected.fireflies_mode == "live" else DisabledIntegration("Transcripts"),
        esign=DropboxSignAdapter(
            selected.esign_api_key, selected.esign_base_url, selected.esign_document_url,
            selected.esign_signer_email, selected.esign_signer_name,
            selected.live_side_effects_enabled, selected.esign_test_mode,
            allowed_recipients={v.strip() for v in selected.esign_allowed_recipients.split(",") if v.strip()},
        ) if live and selected.esign_mode == "live" else DisabledIntegration("E-signature"),
        crm=HubSpotAdapter(selected.hubspot_access_token) if live and selected.hubspot_mode == "live" else None,
    )
