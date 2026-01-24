"""Ledger validation utilities."""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from .ledger import ledger_record_hash


@dataclass
class ValidationIssue:
    """A validation issue emitted by the validator."""

    level: str
    code: str
    message: str


@dataclass
class ValidationResult:
    """Summary of validation checks."""

    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)


def validate_run(run_dir: str) -> ValidationResult:
    """Validate a run directory."""
    issues: list[ValidationIssue] = []
    run_path = Path(run_dir)
    ledger_path = run_path / "ledger.ndjson"

    if ledger_path.exists():
        lines = [
            line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line
        ]
        previous_hash: str | None = None
        for index, line in enumerate(lines, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(
                    ValidationIssue(
                        level="ERROR",
                        code="LEDGER_INVALID_JSON",
                        message=f"Record {index} is not valid JSON: {exc}",
                    )
                )
                continue
            computed_hash = ledger_record_hash(record)
            if record.get("hash") != computed_hash:
                issues.append(
                    ValidationIssue(
                        level="ERROR",
                        code="HASH_CHAIN_BROKEN",
                        message=f"Record {index} hash does not match contents.",
                    )
                )
            if record.get("prev_hash") != previous_hash:
                issues.append(
                    ValidationIssue(
                        level="ERROR",
                        code="HASH_CHAIN_BROKEN",
                        message=f"Record {index} prev_hash does not match chain.",
                    )
                )
            previous_hash = record.get("hash")
    else:
        issues.append(
            ValidationIssue(
                level="ERROR",
                code="LEDGER_MISSING",
                message="ledger.ndjson is missing.",
            )
        )

    manifest_path = run_path / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        state_paths = _collect_state_paths(manifest)
        for state_path in state_paths:
            if not (run_path / state_path).exists():
                issues.append(
                    ValidationIssue(
                        level="ERROR",
                        code="MISSING_STATE_FILE",
                        message=f"State file missing: {state_path}",
                    )
                )
    else:
        issues.append(
            ValidationIssue(
                level="ERROR",
                code="MANIFEST_MISSING",
                message="manifest.json is missing.",
            )
        )

    return ValidationResult(ok=not issues, issues=issues)


def compare_runs(run_dir_a: str, run_dir_b: str) -> ValidationResult:
    """Compare two runs, ignoring timestamps and run identifiers."""
    issues: list[ValidationIssue] = []
    records_a = _load_projected_records(Path(run_dir_a) / "ledger.ndjson")
    records_b = _load_projected_records(Path(run_dir_b) / "ledger.ndjson")
    if records_a != records_b:
        issues.append(
            ValidationIssue(
                level="ERROR",
                code="RUNS_DIVERGED",
                message="Run ledgers differ after normalization.",
            )
        )
    return ValidationResult(ok=not issues, issues=issues)


def _collect_state_paths(manifest: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    inputs = manifest.get("inputs", {})
    initial_state = inputs.get("initial_state")
    if isinstance(initial_state, dict) and "path" in initial_state:
        paths.append(initial_state["path"])
    for step in manifest.get("steps", []):
        for key in ("state_in", "state_out"):
            state_entry = step.get(key)
            if isinstance(state_entry, dict) and "path" in state_entry:
                paths.append(state_entry["path"])
    final_state = manifest.get("final_state")
    if isinstance(final_state, dict) and "path" in final_state:
        paths.append(final_state["path"])
    return paths


def _load_projected_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    ignored_keys = {"run_id", "ts_utc", "hash", "prev_hash"}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        records.append(_strip_keys(record, ignored_keys))
    return records


def _strip_keys(value: Any, ignored_keys: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_keys(item, ignored_keys)
            for key, item in value.items()
            if key not in ignored_keys
        }
    if isinstance(value, list):
        return [_strip_keys(item, ignored_keys) for item in value]
    return value
