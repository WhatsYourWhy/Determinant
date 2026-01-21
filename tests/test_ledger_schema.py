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


class EventArtifactStep(Step):
    def execute(self, state: State) -> StepResult:
        count = int(state.data["count"]) + 1
        new_state = State({"count": count})
        event = StepEvent(
            event_type="INFO",
            code="COUNT_UPDATED",
            message="Count incremented",
            data={"count": count},
        )
        artifact = Artifact(
            artifact_id="count-snapshot",
            logical_name="count_snapshot",
            media_type="application/json",
            path="count.json",
            bytes=canonical_json_bytes({"count": count}),
        )
        return StepResult(state=new_state, events=[event], artifacts=[artifact])


def _load_ledger(run_dir: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (run_dir / "ledger.ndjson").read_text("utf-8").splitlines()
        if line.strip()
    ]


def test_ledger_schema_and_sequence(tmp_path: Path) -> None:
    graph = SimpleGraph(
        graph_id="ledger-schema",
        version="v1",
        steps=[EventArtifactStep()],
    )
    config = RunConfig(
        run_id="ledger-schema-run",
        seed=1,
        output_dir=str(tmp_path / "ledger_schema"),
        config_data={"example": "schema"},
    )
    initial_state = State({"count": 0})
    result = run(graph=graph, initial_state=initial_state, config=config)
    run_dir = Path(result.ledger_path).parent

    records = _load_ledger(run_dir)
    allowed_types = {
        "RUN_START",
        "STEP_START",
        "STEP_EVENT",
        "ARTIFACT_WRITTEN",
        "STEP_END",
        "RUN_END",
        "RUN_FAIL",
        "RECORD_TIME",
        "PERF_METRIC",
    }
    required_by_type = {
        "RUN_START": {"runtime", "run", "inputs"},
        "STEP_START": {"step", "state_in"},
        "STEP_EVENT": {"step", "event"},
        "ARTIFACT_WRITTEN": {"step", "artifact"},
        "STEP_END": {"step", "status", "state_out"},
        "RUN_END": {"status", "final_state", "rollup"},
        "RUN_FAIL": {"status", "step", "error"},
        "RECORD_TIME": {"for_seq", "for_hash", "ts_utc"},
        "PERF_METRIC": {"for_seq", "for_hash", "step", "metrics"},
    }

    for index, record in enumerate(records, start=1):
        assert record["schema"] == "determinant.ledger.v0"
        assert record["type"] in allowed_types
        assert record["seq"] == index
        for field in {"schema", "type", "run_id", "seq", "prev_hash", "hash"}:
            assert field in record
        expected_fields = required_by_type.get(record["type"], set())
        assert expected_fields.issubset(record.keys())
