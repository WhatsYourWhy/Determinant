"""Deterministic step definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .state import State


@dataclass
class StepEvent:
    """Structured event emitted during step execution."""

    event_type: str
    code: str
    message: str
    data: dict[str, Any]


@dataclass
class Artifact:
    """Artifact emitted during step execution."""

    artifact_id: str
    logical_name: str
    media_type: str
    path: str
    bytes: bytes


@dataclass
class StepResult:
    """Result of running a step."""

    state: State
    events: list[StepEvent]
    artifacts: list[Artifact]


class Step(ABC):
    """Base class for deterministic steps."""

    step_id: str

    def __init__(self) -> None:
        if not getattr(self, "step_id", None):
            self.step_id = self.__class__.__name__

    @abstractmethod
    def execute(self, state: State) -> StepResult:
        """Execute the step against the provided state."""

        raise NotImplementedError
