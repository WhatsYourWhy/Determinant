from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from determinant.run import RunConfig, run
from determinant.state import State
from determinant.step import Artifact, Step, StepEvent, StepResult
from determinant.utils.json_canonical import canonical_json_bytes


@dataclass
class SimpleGraph:
    graph_id: str
    version: str
    steps: list[Step]


def _run_graph(tmp_path: Path, graph: SimpleGraph, run_id: str, config_data: dict) -> Path:
    output_dir = tmp_path / config_data["output_dir"]
    config = RunConfig(
        run_id=run_id,
        seed=config_data["seed"],
        output_dir=str(output_dir),
        config_data=config_data,
    )
    initial_state = State({"value": config_data["initial_value"]})
    result = run(graph=graph, initial_state=initial_state, config=config)
    return Path(result.ledger_path).parent


class AddValueStep(Step):
    def __init__(self, increment: int) -> None:
        super().__init__()
        self.increment = increment

    def execute(self, state: State) -> StepResult:
        value = int(state.data["value"]) + self.increment
        new_state = State({"value": value})
        event = StepEvent(
            event_type="INFO",
            code="VALUE_UPDATED",
            message=f"Value updated to {value}",
            data={"value": value},
        )
        artifact = Artifact(
            artifact_id=f"value-{value}",
            logical_name="value_snapshot",
            media_type="application/json",
            path="value.json",
            bytes=canonical_json_bytes({"value": value}),
        )
        return StepResult(state=new_state, events=[event], artifacts=[artifact])


class ThresholdStep(Step):
    def __init__(self, threshold: int) -> None:
        super().__init__()
        self.threshold = threshold

    def execute(self, state: State) -> StepResult:
        value = int(state.data["value"])
        new_state = State(
            {
                "value": value,
                "above_threshold": value >= self.threshold,
                "threshold": self.threshold,
            }
        )
        return StepResult(state=new_state, events=[], artifacts=[])


def test_run_determinism(tmp_path: Path) -> None:
    graph = SimpleGraph(
        graph_id="determinism-demo",
        version="v1",
        steps=[AddValueStep(5)],
    )
    config = {
        "seed": 7,
        "output_dir": "run_one",
        "initial_value": 10,
    }
    run_id = "determinism-run"
    run_one_dir = _run_graph(tmp_path, graph, run_id, config)

    config_two = dict(config)
    config_two["output_dir"] = "run_two"
    run_two_dir = _run_graph(tmp_path, graph, run_id, config_two)

    ledger_one = (run_one_dir / "ledger.ndjson").read_bytes()
    ledger_two = (run_two_dir / "ledger.ndjson").read_bytes()
    assert ledger_one == ledger_two

    manifest_one = json.loads((run_one_dir / "manifest.json").read_text("utf-8"))
    manifest_two = json.loads((run_two_dir / "manifest.json").read_text("utf-8"))
    assert manifest_one["final_state"]["sha256"] == manifest_two["final_state"]["sha256"]


def test_config_change_diverges_at_expected_step(tmp_path: Path) -> None:
    graph_threshold_two = SimpleGraph(
        graph_id="threshold-demo",
        version="v1",
        steps=[AddValueStep(1), ThresholdStep(2)],
    )
    graph_threshold_three = SimpleGraph(
        graph_id="threshold-demo",
        version="v1",
        steps=[AddValueStep(1), ThresholdStep(3)],
    )
    run_id = "threshold-run"
    run_one_dir = _run_graph(
        tmp_path,
        graph_threshold_two,
        run_id,
        {
            "seed": 0,
            "output_dir": "threshold_two",
            "initial_value": 1,
            "threshold": 2,
        },
    )
    run_two_dir = _run_graph(
        tmp_path,
        graph_threshold_three,
        run_id,
        {
            "seed": 0,
            "output_dir": "threshold_three",
            "initial_value": 1,
            "threshold": 3,
        },
    )

    manifest_one = json.loads((run_one_dir / "manifest.json").read_text("utf-8"))
    manifest_two = json.loads((run_two_dir / "manifest.json").read_text("utf-8"))
    step_one_state = manifest_one["steps"][0]["state_out"]["path"]
    step_two_state = manifest_one["steps"][1]["state_out"]["path"]

    step_one_bytes_a = (run_one_dir / step_one_state).read_bytes()
    step_one_bytes_b = (run_two_dir / step_one_state).read_bytes()
    assert step_one_bytes_a == step_one_bytes_b

    step_two_bytes_a = (run_one_dir / step_two_state).read_bytes()
    step_two_bytes_b = (run_two_dir / step_two_state).read_bytes()
    assert step_two_bytes_a != step_two_bytes_b
