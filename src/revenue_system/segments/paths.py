"""Locate bundled packs independently of the process working directory."""

from importlib.resources import files
from pathlib import Path


def packs_path(override: Path | str | None = None) -> Path:
    if override is not None:
        root = Path(override).resolve()
    else:
        bundled = Path(str(files("revenue_system").joinpath("data", "packs")))
        root = bundled if bundled.is_dir() else Path(__file__).resolve().parents[3] / "packs"
    if not root.is_dir():
        raise ValueError("Segment packs are missing; reinstall the complete wheel or set PACKS_ROOT")
    return root
