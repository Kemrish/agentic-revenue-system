"""Composition root: selects concrete adapters for each runtime mode."""

from dataclasses import dataclass

from .settings import Settings
from .adapters.db import SQLiteStore
from .adapters.claude_runner import ClaudeRunner
from .adapters.esign import ESignAdapter
from .adapters.fireflies import FirefliesAdapter
from .adapters.hubspot import HubSpotAdapter
from .adapters.mail import MailAdapter
from .adapters.fixtures.esign import FixtureESignAdapter
from .adapters.fixtures.mail import FixtureMailAdapter
from .adapters.fixtures.transcripts import FixtureTranscriptAdapter
from .agents.execution import ReplayRunner


@dataclass(frozen=True)
class Container:
    settings: Settings
    store: SQLiteStore
    runner: object
    mail: object
    transcripts: object
    esign: object
    crm: object


def build_container(settings: Settings | None = None) -> Container:
    selected = settings or Settings()
    live = selected.runtime_mode == "live"
    return Container(
        settings=selected,
        store=SQLiteStore(selected.database_url),
        runner=ClaudeRunner() if live and selected.claude_mode == "live" else ReplayRunner({}),
        mail=MailAdapter(
            selected.mail_api_key,
            selected.mail_from_address,
            allowed_recipients={item.strip() for item in selected.mail_allowed_recipients.split(",") if item.strip()},
            live_side_effects_enabled=selected.live_side_effects_enabled,
        ) if live and selected.mail_mode == "live" else FixtureMailAdapter(),
        transcripts=FirefliesAdapter(selected.fireflies_api_key) if live and selected.fireflies_mode == "live" else FixtureTranscriptAdapter(),
        esign=ESignAdapter(selected.esign_api_key, selected.esign_base_url) if live and selected.esign_mode == "live" else FixtureESignAdapter(),
        crm=HubSpotAdapter(selected.hubspot_access_token) if live and selected.hubspot_mode == "live" else None,
    )

