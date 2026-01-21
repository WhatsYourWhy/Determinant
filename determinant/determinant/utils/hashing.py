"""Hashing utilities for canonical JSON."""

from __future__ import annotations

import hashlib
from typing import Any

from .json_canonical import canonical_json_bytes


def sha256_digest(data: bytes) -> bytes:
    """Return the SHA-256 digest for raw bytes."""

    return hashlib.sha256(data).digest()


def sha256_hexdigest(data: bytes) -> str:
    """Return the SHA-256 hex digest for raw bytes."""

    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes_for_value(value: Any) -> bytes:
    """Return canonical JSON bytes for a Python value."""

    return canonical_json_bytes(value)


def sha256_canonical_json_bytes(value: Any) -> bytes:
    """Return the SHA-256 digest of canonical JSON bytes for a value."""

    data = canonical_json_bytes_for_value(value)
    return sha256_digest(data)


def sha256_canonical_json_hexdigest(value: Any) -> str:
    """Return the SHA-256 hex digest of canonical JSON bytes for a value."""

    data = canonical_json_bytes_for_value(value)
    return sha256_hexdigest(data)
