"""Composition root: selects concrete adapters for each runtime mode."""

from dataclasses import dataclass

from .settings import Settings


@dataclass(frozen=True)
class Container:
    settings: Settings


def build_container(settings: Settings | None = None) -> Container:
    return Container(settings=settings or Settings())

