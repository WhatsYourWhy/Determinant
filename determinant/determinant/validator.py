"""Validation utilities for Determinant run artifacts."""

from __future__ import annotations

import json
from decimal import Decimal
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .utils.hashing import sha256_canonical_json_hexdigest, sha256_hexdigest


@dataclass(frozen=True)
class ValidationIssue:
    level: str
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue]


def validate_run(run_dir: str | Path) -> ValidationResult:
    run_path = Path(run_dir)
    issues: list[ValidationIssue] = []

    ledger_path = run_path / "ledger.ndjson"
    if not ledger_path.exists():
        _add_issue(
            issues,
            "ERROR",
            "LEDGER_NOT_FOUND",
            f"Missing ledger file at {ledger_path}",
        )
        return ValidationResult(ok=False, issues=issues)

    records = list(_load_ledger_records(ledger_path, issues))
    _validate_hash_chain(records, issues)
    _validate_record_order(records, issues)
    _validate_referenced_files(run_path, records, issues)

    return ValidationResult(ok=not issues, issues=issues)


def _load_ledger_records(
    ledger_path: Path, issues: list[ValidationIssue]
) -> Iterable[dict[str, Any]]:
    for line_number, raw_line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            _add_issue(
                issues,
                "ERROR",
                "INVALID_LEDGER_JSON",
                f"Line {line_number}: {exc.msg}",
            )
            continue
        if not isinstance(record, dict):
            _add_issue(
                issues,
                "ERROR",
                "INVALID_RECORD",
                f"Line {line_number}: ledger record is not an object",
            )
            continue
        record["_line"] = line_number
        yield record


def _validate_hash_chain(records: list[dict[str, Any]], issues: list[ValidationIssue]) -> None:
    prev_hash = None
    for record in records:
        record_hash = record.get("hash")
        without_hash = {
            key: value
            for key, value in record.items()
            if key not in {"hash", "_line"}
        }
        expected_hash = sha256_canonical_json_hexdigest(without_hash)
        if record_hash is None:
            _add_issue(
                issues,
                "ERROR",
                "MISSING_RECORD_HASH",
                f"Line {record.get('_line')}: record missing hash",
            )
        elif record_hash != expected_hash:
            _add_issue(
                issues,
                "ERROR",
                "HASH_MISMATCH",
                f"Line {record.get('_line')}: hash does not match canonical content",
            )
        if record.get("prev_hash") != prev_hash:
            _add_issue(
                issues,
                "ERROR",
                "HASH_CHAIN_BROKEN",
                f"Line {record.get('_line')}: prev_hash does not match previous record",
            )
        prev_hash = record_hash


def _validate_record_order(records: list[dict[str, Any]], issues: list[ValidationIssue]) -> None:
    semantic_types = {
        "RUN_START",
        "STEP_START",
        "STEP_EVENT",
        "ARTIFACT_WRITTEN",
        "STEP_END",
        "RUN_END",
        "RUN_FAIL",
    }
    non_semantic = {"RECORD_TIME", "PERF_METRIC"}
    state = "START"
    step_open = False
    saw_run_start = False
    saw_terminal = False

    for record in records:
        record_type = record.get("type")
        if record_type in non_semantic:
            continue
        if record_type not in semantic_types:
            _add_issue(
                issues,
                "ERROR",
                "UNKNOWN_RECORD_TYPE",
                f"Line {record.get('_line')}: unknown record type {record_type!r}",
            )
            continue
        if state == "START":
            if record_type != "RUN_START":
                _add_issue(
                    issues,
                    "ERROR",
                    "REQUIRED_RECORD_ORDER",
                    "RUN_START must be the first semantic record",
                )
            else:
                saw_run_start = True
                state = "RUNNING"
            continue
        if state == "DONE":
            _add_issue(
                issues,
                "ERROR",
                "REQUIRED_RECORD_ORDER",
                f"Line {record.get('_line')}: record after terminal {record_type}",
            )
            continue

        if record_type == "RUN_START":
            _add_issue(
                issues,
                "ERROR",
                "REQUIRED_RECORD_ORDER",
                f"Line {record.get('_line')}: duplicate RUN_START",
            )
        elif record_type == "STEP_START":
            if step_open:
                _add_issue(
                    issues,
                    "ERROR",
                    "REQUIRED_RECORD_ORDER",
                    f"Line {record.get('_line')}: STEP_START before STEP_END",
                )
            step_open = True
        elif record_type in {"STEP_EVENT", "ARTIFACT_WRITTEN"}:
            if not step_open:
                _add_issue(
                    issues,
                    "ERROR",
                    "REQUIRED_RECORD_ORDER",
                    f"Line {record.get('_line')}: {record_type} outside step",
                )
        elif record_type == "STEP_END":
            if not step_open:
                _add_issue(
                    issues,
                    "ERROR",
                    "REQUIRED_RECORD_ORDER",
                    f"Line {record.get('_line')}: STEP_END without STEP_START",
                )
            step_open = False
        elif record_type in {"RUN_END", "RUN_FAIL"}:
            if step_open:
                _add_issue(
                    issues,
                    "ERROR",
                    "REQUIRED_RECORD_ORDER",
                    f"Line {record.get('_line')}: {record_type} before STEP_END",
                )
            saw_terminal = True
            state = "DONE"

    if not saw_run_start:
        _add_issue(
            issues,
            "ERROR",
            "MISSING_RUN_START",
            "RUN_START record is missing",
        )
    if not saw_terminal:
        _add_issue(
            issues,
            "ERROR",
            "MISSING_RUN_END",
            "RUN_END or RUN_FAIL record is missing",
        )
    if step_open:
        _add_issue(
            issues,
            "ERROR",
            "INCOMPLETE_STEP",
            "STEP_START without matching STEP_END",
        )


def _validate_referenced_files(
    run_path: Path, records: list[dict[str, Any]], issues: list[ValidationIssue]
) -> None:
    for record in records:
        record_type = record.get("type")
        if record_type == "RUN_START":
            inputs = record.get("inputs", {})
            _validate_input_file(run_path, inputs.get("graph"), "graph", issues)
            _validate_input_file(run_path, inputs.get("config"), "config", issues)
            _validate_input_file(run_path, inputs.get("env"), "env", issues)
            _validate_state_file(run_path, inputs.get("initial_state"), issues)
        elif record_type == "STEP_START":
            _validate_state_file(run_path, record.get("state_in"), issues)
        elif record_type == "STEP_END":
            _validate_state_file(run_path, record.get("state_out"), issues)
        elif record_type == "RUN_END":
            _validate_state_file(run_path, record.get("final_state"), issues)
        elif record_type == "ARTIFACT_WRITTEN":
            _validate_artifact_file(run_path, record.get("artifact"), issues)


def _validate_input_file(
    run_path: Path,
    payload: dict[str, Any] | None,
    label: str,
    issues: list[ValidationIssue],
) -> None:
    if not payload:
        _add_issue(
            issues,
            "ERROR",
            "MISSING_INPUT",
            f"RUN_START missing {label} input payload",
        )
        return
    path = payload.get("path")
    sha = payload.get("sha256")
    if not path:
        _add_issue(
            issues,
            "ERROR",
            "MISSING_INPUT_PATH",
            f"RUN_START missing {label} input path",
        )
        return
    full_path = run_path / path
    if not full_path.exists():
        _add_issue(
            issues,
            "ERROR",
            "MISSING_INPUT_FILE",
            f"Missing {label} input file at {path}",
        )
        return
    if sha:
        actual = sha256_hexdigest(full_path.read_bytes())
        if actual != sha:
            _add_issue(
                issues,
                "ERROR",
                "INPUT_HASH_MISMATCH",
                f"{label} input hash mismatch for {path}",
            )


def _validate_state_file(
    run_path: Path,
    payload: dict[str, Any] | None,
    issues: list[ValidationIssue],
) -> None:
    if not payload:
        _add_issue(
            issues,
            "ERROR",
            "MISSING_STATE",
            "Missing state payload in ledger record",
        )
        return
    path = payload.get("path")
    sha = payload.get("sha256")
    if not path:
        _add_issue(
            issues,
            "ERROR",
            "MISSING_STATE_PATH",
            "Missing state path in ledger record",
        )
        return
    full_path = run_path / path
    if not full_path.exists():
        _add_issue(
            issues,
            "ERROR",
            "MISSING_STATE_FILE",
            f"Missing state file at {path}",
        )
        return
    if sha:
        try:
            data = json.loads(full_path.read_text("utf-8"), parse_float=Decimal)
        except json.JSONDecodeError:
            _add_issue(
                issues,
                "ERROR",
                "STATE_JSON_INVALID",
                f"State file at {path} is not valid JSON",
            )
            return
        actual = sha256_canonical_json_hexdigest(data)
        if actual != sha:
            _add_issue(
                issues,
                "ERROR",
                "STATE_HASH_MISMATCH",
                f"State hash mismatch for {path}",
            )


def _validate_artifact_file(
    run_path: Path,
    payload: dict[str, Any] | None,
    issues: list[ValidationIssue],
) -> None:
    if not payload:
        _add_issue(
            issues,
            "ERROR",
            "MISSING_ARTIFACT",
            "Missing artifact payload in ledger record",
        )
        return
    path = payload.get("path")
    sha = payload.get("sha256")
    if not path:
        _add_issue(
            issues,
            "ERROR",
            "MISSING_ARTIFACT_PATH",
            "Missing artifact path in ledger record",
        )
        return
    full_path = run_path / path
    if not full_path.exists():
        _add_issue(
            issues,
            "ERROR",
            "MISSING_ARTIFACT_FILE",
            f"Missing artifact file at {path}",
        )
        return
    if sha:
        actual = sha256_hexdigest(full_path.read_bytes())
        if actual != sha:
            _add_issue(
                issues,
                "ERROR",
                "ARTIFACT_HASH_MISMATCH",
                f"Artifact hash mismatch for {path}",
            )


def _add_issue(
    issues: list[ValidationIssue], level: str, code: str, message: str
) -> None:
    issues.append(ValidationIssue(level=level, code=code, message=message))
