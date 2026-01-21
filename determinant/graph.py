"""Graph representation for deterministic execution."""

from __future__ import annotations

from dataclasses import dataclass, field

from .step import Step


@dataclass
class Graph:
    """Static, ordered list of steps (v0)."""

    graph_id: str
    version: str
    steps: list[Step] = field(default_factory=list)
