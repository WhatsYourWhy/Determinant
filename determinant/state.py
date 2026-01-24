"""State container for deterministic runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .hashing import sha256_canonical_json
from .json_canonical import canonical_json_bytes


@dataclass(frozen=True)
class State:
    """Immutable, serializable state for a Determinant run."""

    data: Mapping[str, Any]

    @classmethod
    def from_file(cls, path: str) -> "State":
        """Load state from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data)

    def to_file(self, path: str) -> None:
        """Persist state to a JSON file."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.to_canonical_json_bytes())

    def to_canonical_json_bytes(self) -> bytes:
        """Return canonical JSON bytes for hashing."""
        return canonical_json_bytes(self.data)

    def sha256(self) -> str:
        """Return SHA-256 of the canonical JSON bytes."""
        return sha256_canonical_json(self.data)
