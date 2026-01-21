"""Ledger writer for NDJSON records with hash chaining."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Mapping

from .utils.hashing import sha256_canonical_json_hexdigest
from .utils.json_canonical import canonical_json_text


@dataclass
class LedgerWriter:
    """Append-only NDJSON writer with hash chaining.

    Records are hashed and chained. Timing and performance metadata are included
    inline in records.
    """

    path: Path
    run_id: str
    schema: str = "determinant.ledger.v0"
    append: bool = False
    _seq: int = field(init=False, default=0)
    _prev_hash: str | None = field(init=False, default=None)
    _handle: IO[str] | None = field(init=False, default=None)

    def __enter__(self) -> "LedgerWriter":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open(self) -> None:
        if self._handle is not None:
            return
        mode = "a" if self.append else "w"
        self._handle = self.path.open(mode, encoding="utf-8")

    def close(self) -> None:
        if self._handle is None:
            return
        self._handle.close()
        self._handle = None

    def write_record(
        self,
        record_type: str,
        payload: Mapping[str, Any],
        *,
        ts_utc: str | None = None,
        metrics_duration_ms: int | None = None,
    ) -> dict[str, Any]:
        """Write a record to the ledger."""

        record_ts = ts_utc or self._utc_now()
        if metrics_duration_ms is not None and record_type != "STEP_END":
            raise ValueError("metrics_duration_ms is only supported for STEP_END records")
        updated_payload = dict(payload)
        if metrics_duration_ms is not None:
            metrics_payload = dict(updated_payload.get("metrics", {}))
            metrics_payload["duration_ms"] = metrics_duration_ms
            updated_payload["metrics"] = metrics_payload
        return self._write_semantic_record(record_type, updated_payload, record_ts)

    def _write_semantic_record(
        self, record_type: str, payload: Mapping[str, Any], ts_utc: str
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "schema": self.schema,
            "type": record_type,
            "run_id": self.run_id,
            "seq": self._next_seq(),
            "prev_hash": self._prev_hash,
            "ts_utc": ts_utc,
        }
        record.update(payload)
        record["hash"] = self._hash_record(record)
        self._write_line(record)
        self._prev_hash = record["hash"]
        return record

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _hash_record(self, record: Mapping[str, Any]) -> str:
        without_hash = {key: value for key, value in record.items() if key != "hash"}
        return sha256_canonical_json_hexdigest(without_hash)

    def _write_line(self, record: Mapping[str, Any]) -> None:
        if self._handle is None:
            raise RuntimeError("LedgerWriter is not open")
        line = canonical_json_text(record)
        self._handle.write(f"{line}\n")

    @staticmethod
    def _utc_now() -> str:
        timestamp = datetime.now(timezone.utc)
        return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")
