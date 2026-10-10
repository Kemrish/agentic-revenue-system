from pathlib import Path

from revenue_system.segments.registry import PackRegistry


def test_both_segment_packs_load():
    registry = PackRegistry(Path("packs"))
    assert {pack.segment for pack in registry.all()} == {"brand", "publisher"}

