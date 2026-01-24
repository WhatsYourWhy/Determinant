"""Tests for Graph execution ordering and manifest metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from determinant.graph import Graph
from determinant.run import RunConfig, run
from determinant.state import State
from determinant.step import Step, StepResult


@dataclass
class NamedStep(Step):
    name: str

    def __post_init__(self) -> None:
        self.step_id = self.name

    def execute(self, state: State, config: dict[str, Any], seed: int) -> StepResult:
        _ = config, seed
        history = list(state.data.get("history", []))
        history.append(self.step_id or self.name)
        return StepResult(state=State({"history": history}))


def _run_graph(tmp_path: Path, graph: Graph) -> Path:
    config = RunConfig(
        run_id="graph-run",
        seed=0,
        output_dir=str(tmp_path / "run"),
    )
    result = run(graph=graph, initial_state=State({"history": []}), config=config)
    return Path(result.ledger_path).parent


def test_graph_execution_order_is_fixed(tmp_path: Path) -> None:
    graph = Graph(
        graph_id="order-demo",
        version="v1",
        steps=[NamedStep("first"), NamedStep("second"), NamedStep("third")],
    )

    run_dir = _run_graph(tmp_path, graph)
    manifest = json.loads((run_dir / "manifest.json").read_text("utf-8"))

    assert [step["step"]["step_id"] for step in manifest["steps"]] == [
        "first",
        "second",
        "third",
    ]

    final_state = json.loads((run_dir / manifest["final_state"]["path"]).read_text("utf-8"))
    assert final_state["history"] == ["first", "second", "third"]


def test_graph_identity_version_captured_in_manifest(tmp_path: Path) -> None:
    graph = Graph(
        graph_id="identity-demo",
        version="2024.09",
        steps=[NamedStep("alpha")],
    )

    run_dir = _run_graph(tmp_path, graph)
    manifest = json.loads((run_dir / "manifest.json").read_text("utf-8"))
    graph_meta = json.loads((run_dir / manifest["inputs"]["graph"]["path"]).read_text("utf-8"))

    assert manifest["graph"] == {"graph_id": "identity-demo", "version": "2024.09"}
    assert graph_meta["graph_id"] == "identity-demo"
    assert graph_meta["version"] == "2024.09"
