"""Composition root: selects concrete adapters for each runtime mode."""

from dataclasses import dataclass

from .settings import Settings
from .adapters.db import SQLiteStore


@dataclass(frozen=True)
class Container:
    settings: Settings
    store: SQLiteStore


def build_container(settings: Settings | None = None) -> Container:
    selected = settings or Settings()
    return Container(settings=selected, store=SQLiteStore(selected.database_url))

