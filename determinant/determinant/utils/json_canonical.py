"""Deterministic JSON canonicalization utilities."""

from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical JSON bytes for a Python value.

    Rules:
    - Sorted object keys (Unicode code point order).
    - UTF-8 encoding.
    - No insignificant whitespace.
    - Deterministic number formatting.
    """

    return _canonicalize(value).encode("utf-8")


def canonical_json_text(value: Any) -> str:
    """Return canonical JSON text for a Python value."""

    return _canonicalize(value)


def _canonicalize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, (float, Decimal)):
        return _format_number(value)
    if isinstance(value, (list, tuple)):
        items = ",".join(_canonicalize(item) for item in value)
        return f"[{items}]"
    if isinstance(value, dict):
        return _canonicalize_object(value)

    raise TypeError(f"Unsupported type for canonical JSON: {type(value)!r}")


def _canonicalize_object(value: dict[str, Any]) -> str:
    items: list[str] = []
    for key in sorted(value.keys()):
        if not isinstance(key, str):
            raise TypeError("JSON object keys must be strings for canonicalization")
        encoded_key = json.dumps(key, ensure_ascii=False)
        items.append(f"{encoded_key}:{_canonicalize(value[key])}")
    return "{" + ",".join(items) + "}"


def _format_number(value: float | Decimal) -> str:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Canonical JSON does not support NaN or Infinity")
        if value == 0.0:
            return "0"
        decimal_value = Decimal.from_float(value)
    else:
        decimal_value = value
        if decimal_value.is_nan() or decimal_value.is_infinite():
            raise ValueError("Canonical JSON does not support NaN or Infinity")
        if decimal_value.is_zero():
            return "0"

    normalized = decimal_value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    return text
