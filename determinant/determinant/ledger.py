"""Ledger writer for NDJSON records with hash chaining."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Mapping

from .utils.hashing import sha256_canonical_json_hexdigest
from .utils.json_canonical import canonical_json_text


@dataclass
class LedgerWriter:
    """Append-only NDJSON writer with hash chaining.

    Semantic records are hashed and chained. Timing and performance metadata are
    recorded as separate non-semantic records (`RECORD_TIME`, `PERF_METRIC`).
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
        metrics_step: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write a semantic record and optional non-semantic companions."""

        semantic_record = self._write_semantic_record(record_type, payload)
        if ts_utc is not None:
            self._write_record_time(semantic_record, ts_utc)
        if metrics_duration_ms is not None:
            if metrics_step is None:
                raise ValueError("metrics_step is required when metrics_duration_ms is set")
            self._write_perf_metric(semantic_record, metrics_step, metrics_duration_ms)
        return semantic_record

    def _write_semantic_record(
        self, record_type: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "schema": self.schema,
            "type": record_type,
            "run_id": self.run_id,
            "seq": self._next_seq(),
            "prev_hash": self._prev_hash,
        }
        record.update(payload)
        record["hash"] = self._hash_record(record)
        self._write_line(record)
        self._prev_hash = record["hash"]
        return record

    def _write_record_time(self, semantic_record: Mapping[str, Any], ts_utc: str) -> None:
        payload = {
            "for_seq": semantic_record["seq"],
            "for_hash": semantic_record["hash"],
            "ts_utc": ts_utc,
        }
        self._write_semantic_record("RECORD_TIME", payload)

    def _write_perf_metric(
        self,
        semantic_record: Mapping[str, Any],
        metrics_step: Mapping[str, Any],
        duration_ms: int,
    ) -> None:
        payload = {
            "for_seq": semantic_record["seq"],
            "for_hash": semantic_record["hash"],
            "step": dict(metrics_step),
            "metrics": {"duration_ms": duration_ms},
        }
        self._write_semantic_record("PERF_METRIC", payload)

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
