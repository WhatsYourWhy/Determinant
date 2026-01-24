"""Tests for step purity constraints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from determinant.state import State
from determinant.step import Step, StepResult


@dataclass
class DeterministicStep(Step):
    value: int

    def execute(self, state: State, config: dict[str, Any], seed: int) -> StepResult:
        _ = config
        current = int(state.data["value"])
        result = current + self.value + seed
        return StepResult(state=State({"value": result}))


def _run_step(step: Step, *, value: int, seed: int) -> StepResult:
    state = State({"value": value})
    return step.execute(state, {}, seed)


def test_step_is_deterministic_given_same_inputs() -> None:
    step = DeterministicStep(3)

    result_one = _run_step(step, value=5, seed=11)
    result_two = _run_step(step, value=5, seed=11)

    assert result_one.state.data == result_two.state.data


def test_step_changes_with_input_seed() -> None:
    step = DeterministicStep(3)

    result_one = _run_step(step, value=5, seed=11)
    result_two = _run_step(step, value=5, seed=12)

    assert result_one.state.data != result_two.state.data
