"""State container for deterministic runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class State:
    """Immutable, serializable state for a Determinant run."""

    data: Mapping[str, Any]

    @classmethod
    def from_file(cls, path: str) -> "State":
        """Load state from a JSON file (placeholder)."""
        raise NotImplementedError("State.from_file is not implemented yet.")

    def to_file(self, path: str) -> None:
        """Persist state to a JSON file (placeholder)."""
        raise NotImplementedError("State.to_file is not implemented yet.")

    def to_canonical_json_bytes(self) -> bytes:
        """Return canonical JSON bytes for hashing (placeholder)."""
        raise NotImplementedError("State.to_canonical_json_bytes is not implemented yet.")

    def sha256(self) -> str:
        """Return SHA-256 of the canonical JSON bytes (placeholder)."""
        raise NotImplementedError("State.sha256 is not implemented yet.")
