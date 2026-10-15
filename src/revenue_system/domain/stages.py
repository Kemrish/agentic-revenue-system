from dataclasses import dataclass

STAGES = (
    "new",
    "enriched",
    "scored",
    "outreach",
    "engaged",
    "meeting",
    "qualified",
    "proposal",
    "contracting",
    "closed_won",
    "closed_lost",
)


@dataclass(frozen=True)
class Transition:
    source: str
    target: str


ALLOWED_TRANSITIONS = {
    ("new", "enriched"),
    ("enriched", "scored"),
    ("scored", "outreach"),
    ("outreach", "engaged"),
    ("engaged", "meeting"),
    ("meeting", "qualified"),
    ("qualified", "proposal"),
    ("proposal", "contracting"),
    ("contracting", "closed_won"),
    ("new", "closed_lost"),
    ("outreach", "closed_lost"),
    ("engaged", "closed_lost"),
    ("qualified", "closed_lost"),
}


def can_transition(source: str, target: str) -> bool:
    return (source, target) in ALLOWED_TRANSITIONS


def transition(stage: str, target: str) -> str:
    if not can_transition(stage, target):
        raise ValueError(f"Invalid stage transition: {stage} -> {target}")
    return target

