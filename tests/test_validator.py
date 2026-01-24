from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from determinant.run import RunConfig, run
from determinant.state import State
from determinant.step import Step, StepResult
from determinant.validator import compare_runs


@dataclass
class SimpleGraph:
    graph_id: str
    version: str
    steps: list[Step]


class AddValueStep(Step):
    def __init__(self, increment: int) -> None:
        super().__init__()
        self.increment = increment

    def execute(self, state: State, config: dict[str, object], seed: int) -> StepResult:
        _ = config, seed
        value = int(state.data["value"]) + self.increment
        return StepResult(state=State({"value": value}))


class MultiplyValueStep(Step):
    def __init__(self, multiplier: int) -> None:
        super().__init__()
        self.multiplier = multiplier

    def execute(self, state: State, config: dict[str, object], seed: int) -> StepResult:
        _ = config, seed
        value = int(state.data["value"]) * self.multiplier
        return StepResult(state=State({"value": value}))


def _run_graph(
    tmp_path: Path,
    graph: SimpleGraph,
    run_id: str,
    output_dir: str,
    seed: int,
    initial_value: int,
) -> Path:
    config = RunConfig(
        run_id=run_id,
        seed=seed,
        output_dir=str(tmp_path / output_dir),
        config_data={
            "seed": seed,
            "output_dir": output_dir,
            "initial_value": initial_value,
        },
    )
    result = run(graph=graph, initial_state=State({"value": initial_value}), config=config)
    return Path(result.ledger_path).parent


def test_compare_runs_ignores_run_id_and_timestamp(tmp_path: Path) -> None:
    graph = SimpleGraph(
        graph_id="validator-demo",
        version="v1",
        steps=[AddValueStep(1)],
    )
    run_one_dir = _run_graph(
        tmp_path,
        graph,
        run_id="run-one",
        output_dir="run_one",
        seed=7,
        initial_value=5,
    )
    run_two_dir = _run_graph(
        tmp_path,
        graph,
        run_id="run-two",
        output_dir="run_two",
        seed=7,
        initial_value=5,
    )

    result = compare_runs(str(run_one_dir), str(run_two_dir))
    assert result.ok
    assert result.issues == []


def test_compare_runs_reports_divergence_at_step(tmp_path: Path) -> None:
    graph_one = SimpleGraph(
        graph_id="validator-diverge",
        version="v1",
        steps=[AddValueStep(1), MultiplyValueStep(2)],
    )
    graph_two = SimpleGraph(
        graph_id="validator-diverge",
        version="v1",
        steps=[AddValueStep(1), MultiplyValueStep(3)],
    )
    run_one_dir = _run_graph(
        tmp_path,
        graph_one,
        run_id="run-one",
        output_dir="run_one",
        seed=11,
        initial_value=2,
    )
    run_two_dir = _run_graph(
        tmp_path,
        graph_two,
        run_id="run-two",
        output_dir="run_two",
        seed=11,
        initial_value=2,
    )

    result = compare_runs(str(run_one_dir), str(run_two_dir))
    assert not result.ok
    assert any(issue.code == "RUN_RECORD_MISMATCH" for issue in result.issues)
