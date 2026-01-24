"""Tests for State serialization and hashing."""

from __future__ import annotations

import json
from pathlib import Path

from determinant.state import State


def test_state_serialization_roundtrip(tmp_path: Path) -> None:
    state = State({"b": 2, "a": {"nested": True, "value": 1}})
    target = tmp_path / "state.json"

    state.to_file(str(target))
    reloaded = State.from_file(str(target))

    assert reloaded.data == state.data


def test_state_hashing_is_stable() -> None:
    data_one = {"b": 2, "a": {"nested": True, "value": 1}}
    data_two = json.loads('{"a": {"value": 1, "nested": true}, "b": 2}')

    state_one = State(data_one)
    state_two = State(data_two)

    assert state_one.to_canonical_json_bytes() == state_two.to_canonical_json_bytes()
    assert state_one.sha256() == state_two.sha256()
