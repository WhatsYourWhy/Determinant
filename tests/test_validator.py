from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from determinant.run import RunConfig, run
from determinant.state import State
from determinant.step import Step, StepResult
from determinant.validator import compare_runs, validate_run


@dataclass
class SimpleGraph:
    graph_id: str
    version: str
    steps: list[Step]


class PassThroughStep(Step):
    def execute(self, state: State) -> StepResult:
        return StepResult(state=state, events=[], artifacts=[])


def _create_run(
    tmp_path: Path,
    *,
    run_id: str = "validator-run",
    output_dir_name: str = "validator",
) -> Path:
    graph = SimpleGraph(
        graph_id="validator-demo",
        version="v1",
        steps=[PassThroughStep()],
    )
    config = RunConfig(
        run_id=run_id,
        seed=0,
        output_dir=str(tmp_path / output_dir_name),
        config_data={"example": "validator"},
    )
    initial_state = State({"status": "ok"})
    result = run(graph=graph, initial_state=initial_state, config=config)
    return Path(result.ledger_path).parent


def test_validator_happy_path(tmp_path: Path) -> None:
    run_dir = _create_run(tmp_path)
    result = validate_run(run_dir)
    assert result.ok is True
    assert result.issues == []


def test_validator_detects_broken_hash_chain(tmp_path: Path) -> None:
    run_dir = _create_run(tmp_path)
    ledger_path = run_dir / "ledger.ndjson"
    lines = ledger_path.read_text("utf-8").splitlines()
    record = json.loads(lines[1])
    record["prev_hash"] = "broken"
    lines[1] = json.dumps(record)
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = validate_run(run_dir)
    codes = {issue.code for issue in result.issues}
    assert "HASH_CHAIN_BROKEN" in codes


def test_validator_detects_tampered_record_contents(tmp_path: Path) -> None:
    run_dir = _create_run(tmp_path)
    ledger_path = run_dir / "ledger.ndjson"
    lines = ledger_path.read_text("utf-8").splitlines()
    record = json.loads(lines[0])
    record["schema"] = "tampered"
    lines[0] = json.dumps(record)
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = validate_run(run_dir)
    codes = {issue.code for issue in result.issues}
    assert "HASH_CHAIN_BROKEN" in codes


def test_validator_detects_missing_state_file(tmp_path: Path) -> None:
    run_dir = _create_run(tmp_path)
    state_dir = run_dir / "state"
    state_files = sorted(state_dir.glob("*.json"))
    state_files[0].unlink()

    result = validate_run(run_dir)
    codes = {issue.code for issue in result.issues}
    assert "MISSING_STATE_FILE" in codes


def test_compare_runs_ignores_timestamps_and_run_id(tmp_path: Path) -> None:
    run_dir_a = _create_run(
        tmp_path, run_id="validator-run-a", output_dir_name="validator-a"
    )
    run_dir_b = _create_run(
        tmp_path, run_id="validator-run-b", output_dir_name="validator-b"
    )

    result = compare_runs(run_dir_a, run_dir_b)
    assert result.ok is True
    assert result.issues == []
