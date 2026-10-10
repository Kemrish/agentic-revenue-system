import pytest

from revenue_system.domain.stages import transition


def test_valid_transition():
    assert transition("new", "enriched") == "enriched"


def test_invalid_transition_is_rejected():
    with pytest.raises(ValueError):
        transition("new", "qualified")

