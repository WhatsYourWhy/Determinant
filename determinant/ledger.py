"""Ledger writer for Determinant runs."""

from __future__ import annotations


class LedgerWriter:
    """Write NDJSON ledger records with hash chaining (placeholder)."""

    def __init__(self, path: str, run_id: str) -> None:
        self.path = path
        self.run_id = run_id

    def write_run_start(self, payload: dict) -> None:
        raise NotImplementedError("write_run_start is not implemented yet.")

    def write_step_start(self, payload: dict) -> None:
        raise NotImplementedError("write_step_start is not implemented yet.")

    def write_step_event(self, payload: dict) -> None:
        raise NotImplementedError("write_step_event is not implemented yet.")

    def write_artifact_written(self, payload: dict) -> None:
        raise NotImplementedError("write_artifact_written is not implemented yet.")

    def write_step_end(self, payload: dict) -> None:
        raise NotImplementedError("write_step_end is not implemented yet.")

    def write_run_end(self, payload: dict) -> None:
        raise NotImplementedError("write_run_end is not implemented yet.")

    def write_run_fail(self, payload: dict) -> None:
        raise NotImplementedError("write_run_fail is not implemented yet.")
