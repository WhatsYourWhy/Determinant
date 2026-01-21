"""State representation with canonical JSON serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from .utils.hashing import (
    canonical_json_bytes_for_value,
    sha256_canonical_json_hexdigest,
)


@dataclass(frozen=True)
class State:
    """A deterministic state container."""

    data: Mapping[str, Any]

    def __post_init__(self) -> None:
        sanitized = _sanitize_mapping(self.data)
        object.__setattr__(self, "data", sanitized)

    @classmethod
    def from_file(cls, path: str | Path) -> "State":
        raw = Path(path).read_bytes()
        data = json.loads(raw.decode("utf-8"), parse_float=Decimal)
        if not isinstance(data, Mapping):
            raise TypeError("State JSON must be an object with string keys")
        return cls(data)

    def to_dict(self) -> Mapping[str, Any]:
        return self.data

    def to_file(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_canonical_json_bytes())

    def to_canonical_json_bytes(self) -> bytes:
        return canonical_json_bytes_for_value(self.to_dict())

    def sha256(self) -> str:
        return sha256_canonical_json_hexdigest(self.to_dict())


def _sanitize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("State keys must be strings for canonical JSON")
        sanitized[key] = _sanitize_value(item)
    return sanitized


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, Decimal, str)):
        return value
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value]
    raise TypeError(f"Unsupported type in state: {type(value)!r}")
