"""Hashing utilities."""

from __future__ import annotations

import hashlib
from typing import Any

from .json_canonical import canonical_json_bytes


def sha256_bytes(data: bytes) -> str:
    """Return SHA-256 hex digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_canonical_json(data: Any) -> str:
    """Return SHA-256 hex digest for canonical JSON serialization of data."""
    return sha256_bytes(canonical_json_bytes(data))
