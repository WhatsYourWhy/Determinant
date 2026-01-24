"""Canonical JSON serialization utilities."""

from __future__ import annotations

import json
from typing import Any


def canonical_json_bytes(data: Any) -> bytes:
    """Serialize data to canonical JSON bytes."""
    serialized = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return serialized.encode("utf-8")
