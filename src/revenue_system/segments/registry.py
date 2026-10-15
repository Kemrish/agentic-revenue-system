from pathlib import Path

from .paths import packs_path
from .schema import SegmentPack, load_pack


class PackRegistry:
    def __init__(self, root: Path | None = None) -> None:
        root = packs_path(root)
        self._packs = {pack.segment: pack for pack in (load_pack(path / "pack.yaml") for path in root.iterdir() if (path / "pack.yaml").exists())}
        if not self._packs:
            raise ValueError("At least one valid segment pack is required")

    def get(self, segment: str) -> SegmentPack:
        try:
            return self._packs[segment]
        except KeyError as exc:
            raise KeyError(f"Unknown segment pack: {segment}") from exc

    def all(self) -> list[SegmentPack]:
        return list(self._packs.values())

