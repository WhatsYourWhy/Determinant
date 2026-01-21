"""Run orchestration for Determinant."""

from __future__ import annotations

from dataclasses import dataclass

from .graph import Graph
from .state import State


@dataclass
class RunConfig:
    """Runtime configuration for a Determinant run."""

    run_id: str | None
    seed: int
    output_dir: str


@dataclass
class RunResult:
    """Result metadata for a Determinant run."""

    run_id: str
    final_state: State | None
    status: str
    ledger_path: str


def run(graph: Graph, initial_state: State, config: RunConfig) -> RunResult:
    """Execute a graph with the provided state (placeholder)."""
    raise NotImplementedError("run() is not implemented yet.")
