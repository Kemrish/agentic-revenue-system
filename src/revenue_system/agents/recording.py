import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .base import AgentRequest


@dataclass(frozen=True)
class Recording:
    agent_name: str
    prompt_version: str
    input_hash: str
    output: dict[str, Any]


def request_hash(request: AgentRequest) -> str:
    value = json.dumps({"task": request.task, "context": request.context}, sort_keys=True)
    return hashlib.sha256(value.encode()).hexdigest()


class RecordingStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, recording: Recording) -> Path:
        path = self.root / f"{recording.agent_name}-{recording.input_hash}.json"
        path.write_text(json.dumps(asdict(recording), indent=2), encoding="utf-8")
        return path

    def load(self, request: AgentRequest) -> Recording:
        path = self.root / f"{request.agent_name}-{request_hash(request)}.json"
        if not path.exists():
            raise KeyError(f"No replay recording for {request.agent_name} and current input")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["prompt_version"] != request.prompt_version:
            raise ValueError("Replay recording prompt version does not match current prompt")
        return Recording(**data)

