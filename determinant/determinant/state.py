"""State representation with canonical JSON serialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .utils.hashing import (
    canonical_json_bytes_for_value,
    sha256_canonical_json_hexdigest,
)


@dataclass(frozen=True)
class State:
    """A deterministic state container."""

    data: Mapping[str, Any]

    def to_dict(self) -> Mapping[str, Any]:
        return self.data

    def to_canonical_json_bytes(self) -> bytes:
        return canonical_json_bytes_for_value(self.to_dict())

    def sha256(self) -> str:
        return sha256_canonical_json_hexdigest(self.to_dict())
