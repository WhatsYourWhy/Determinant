from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "determinant"))

from determinant.run import RunConfig, run
from determinant.state import State
from determinant.step import Artifact, Step, StepEvent, StepResult
from determinant.json_canonical import canonical_json_bytes


@dataclass
class ExampleGraph:
    graph_id: str
    version: str
    steps: list[Step]


class ScaleNumbers(Step):
    def __init__(self, multiplier: int) -> None:
        super().__init__()
        self.multiplier = multiplier

    def execute(self, state: State) -> StepResult:
        numbers = [int(value) * self.multiplier for value in state.data["numbers"]]
        new_state = State({"numbers": state.data["numbers"], "scaled": numbers})
        event = StepEvent(
            event_type="INFO",
            code="NUMBERS_SCALED",
            message=f"Scaled {len(numbers)} numbers",
            data={"count": len(numbers), "multiplier": self.multiplier},
        )
        return StepResult(state=new_state, events=[event], artifacts=[])


class SummarizeNumbers(Step):
    def execute(self, state: State) -> StepResult:
        scaled = state.data["scaled"]
        total = sum(int(value) for value in scaled)
        average = total / max(len(scaled), 1)
        summary = {"total": total, "average": average, "count": len(scaled)}
        new_state = State({"numbers": state.data["numbers"], "scaled": scaled, "summary": summary})
        artifact = Artifact(
            artifact_id="summary",
            logical_name="summary",
            media_type="application/json",
            path="summary.json",
            bytes=canonical_json_bytes(summary),
        )
        event = StepEvent(
            event_type="INFO",
            code="SUMMARY_COMPUTED",
            message="Computed summary statistics",
            data=summary,
        )
        return StepResult(state=new_state, events=[event], artifacts=[artifact])


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _build_graph(graph_config: dict, config: dict) -> ExampleGraph:
    step_factories = {
        "scale_numbers": lambda: ScaleNumbers(config["multiplier"]),
        "summarize_numbers": lambda: SummarizeNumbers(),
    }
    steps: list[Step] = []
    for step_config in graph_config["steps"]:
        step_type = step_config["type"]
        step = step_factories[step_type]()
        step.step_id = step_config["step_id"]
        steps.append(step)
    return ExampleGraph(
        graph_id=graph_config["graph_id"],
        version=graph_config["version"],
        steps=steps,
    )


def _run_replay(graph: ExampleGraph, state: State, config: dict, label: str) -> Path:
    output_dir = Path(__file__).resolve().parent / "runs" / label
    run_config = RunConfig(
        run_id="math-replay",
        seed=config["seed"],
        output_dir=str(output_dir),
        config_data=config,
    )
    result = run(graph=graph, initial_state=state, config=run_config)
    return Path(result.ledger_path).parent


def main() -> None:
    example_dir = Path(__file__).resolve().parent
    graph_config = _load_json(example_dir / "graph.json")
    config = _load_json(example_dir / "config.json")
    initial_state = State.from_file(example_dir / "input_state.json")

    graph = _build_graph(graph_config, config)

    run_one = _run_replay(graph, initial_state, config, "first")
    run_two = _run_replay(graph, initial_state, config, "second")

    ledger_one = (run_one / "ledger.ndjson").read_bytes()
    ledger_two = (run_two / "ledger.ndjson").read_bytes()
    manifest_one = _load_json(run_one / "manifest.json")
    manifest_two = _load_json(run_two / "manifest.json")

    if ledger_one == ledger_two and manifest_one["final_state"]["sha256"] == manifest_two["final_state"]["sha256"]:
        print("Deterministic replay verified for math-only pipeline.")
    else:
        raise SystemExit("Replay mismatch detected.")


if __name__ == "__main__":
    main()
