from __future__ import annotations

from determinant.hashing import sha256_canonical_json
from determinant.json_canonical import canonical_json_bytes
from determinant.state import State


def test_canonical_json_hash_stable_for_key_order() -> None:
    data_one = {"b": 2, "a": 1}
    data_two = {"a": 1, "b": 2}

    assert canonical_json_bytes(data_one) == canonical_json_bytes(data_two)
    assert sha256_canonical_json(data_one) == sha256_canonical_json(data_two)


def test_state_sha256_uses_canonical_json() -> None:
    state_one = State({"b": 2, "a": 1})
    state_two = State({"a": 1, "b": 2})

    assert state_one.sha256() == state_two.sha256()
