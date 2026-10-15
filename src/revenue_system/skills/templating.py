from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from revenue_system.segments.paths import packs_path


class TemplateRenderer:
    def __init__(self, packs_root: Path | None = None) -> None:
        packs_root = packs_path(packs_root)
        self.environment = Environment(loader=FileSystemLoader(str(packs_root)), undefined=StrictUndefined, autoescape=False)

    def render(self, template_path: str, values: dict[str, Any]) -> str:
        return self.environment.get_template(template_path).render(**values)

