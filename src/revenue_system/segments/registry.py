from pathlib import Path

from .schema import SegmentPack, load_pack


class PackRegistry:
    def __init__(self, root: Path) -> None:
        self._packs = {pack.segment: pack for pack in (load_pack(path / "pack.yaml") for path in root.iterdir() if (path / "pack.yaml").exists())}

    def get(self, segment: str) -> SegmentPack:
        try:
            return self._packs[segment]
        except KeyError as exc:
            raise KeyError(f"Unknown segment pack: {segment}") from exc

    def all(self) -> list[SegmentPack]:
        return list(self._packs.values())

