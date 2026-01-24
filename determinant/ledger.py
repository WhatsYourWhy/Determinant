"""Ledger writer for Determinant runs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .hashing import sha256_canonical_json


class LedgerWriter:
    """Write NDJSON ledger records with hash chaining (placeholder)."""

    def __init__(self, path: str, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self._seq = 0
        self._last_hash: str | None = None
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def write_run_start(self, payload: dict) -> None:
        self._write_record("RUN_START", payload)

    def write_step_start(self, payload: dict) -> None:
        self._write_record("STEP_START", payload)

    def write_step_event(self, payload: dict) -> None:
        self._write_record("STEP_EVENT", payload)

    def write_artifact_written(self, payload: dict) -> None:
        self._write_record("ARTIFACT_WRITTEN", payload)

    def write_step_end(self, payload: dict) -> None:
        self._write_record("STEP_END", payload)

    def write_run_end(self, payload: dict) -> None:
        self._write_record("RUN_END", payload)

    def write_run_fail(self, payload: dict) -> None:
        self._write_record("RUN_FAIL", payload)

    def _write_record(self, record_type: str, payload: dict) -> None:
        self._seq += 1
        record = {
            "schema": "determinant.ledger.v0",
            "type": record_type,
            "run_id": self.run_id,
            "seq": self._seq,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "prev_hash": self._last_hash,
        }
        record.update(payload)
        record["hash"] = ledger_record_hash(record)
        serialized = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(serialized + "\n")
        self._last_hash = record["hash"]


def ledger_record_hash(record: dict[str, Any]) -> str:
    """Return the canonical hash of a ledger record without its hash field."""
    record_without_hash = {key: value for key, value in record.items() if key != "hash"}
    return sha256_canonical_json(record_without_hash)
