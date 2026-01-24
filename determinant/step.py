"""Step interface and result structures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .state import State


@dataclass
class StepEvent:
    """Deterministic event emitted during a step."""

    event_type: str
    code: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Artifact:
    """Artifact output written during a step."""

    artifact_id: str
    logical_name: str
    media_type: str
    path: str
    bytes: bytes


@dataclass
class StepResult:
    """Container for step output."""

    state: State
    events: list[StepEvent] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)


class Step(ABC):
    """Base class for deterministic steps."""

    step_id: str | None = None

    def __init__(self) -> None:
        if self.step_id is None:
            self.step_id = self.__class__.__name__

    @abstractmethod
    def execute(self, state: State, config: dict[str, Any], seed: int) -> StepResult:
        """Execute the step over the provided state."""
        raise NotImplementedError
