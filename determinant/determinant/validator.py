"""Validation utilities for Determinant run artifacts."""

from __future__ import annotations

import json
from decimal import Decimal
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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


@dataclass(frozen=True)
class ComparisonIssue:
    level: str
    code: str
    message: str


@dataclass(frozen=True)
class ComparisonResult:
    ok: bool
    issues: list[ComparisonIssue]


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


def compare_runs(
    run_dir_a: str | Path,
    run_dir_b: str | Path,
    *,
    strict: bool = True,
    normalize_run_id: bool = True,
) -> ComparisonResult:
    """Compare two run directories for deterministic ledger equivalence."""
    run_path_a = Path(run_dir_a)
    run_path_b = Path(run_dir_b)
    issues: list[ComparisonIssue] = []

    ledger_path_a = run_path_a / "ledger.ndjson"
    ledger_path_b = run_path_b / "ledger.ndjson"
    if not ledger_path_a.exists():
        _add_comparison_issue(
            issues,
            "ERROR",
            "LEDGER_NOT_FOUND",
            f"Missing ledger file at {ledger_path_a}",
        )
    if not ledger_path_b.exists():
        _add_comparison_issue(
            issues,
            "ERROR",
            "LEDGER_NOT_FOUND",
            f"Missing ledger file at {ledger_path_b}",
        )
    if issues:
        return ComparisonResult(ok=False, issues=issues)

    records_a = list(_load_ledger_records_for_compare(ledger_path_a, issues))
    records_b = list(_load_ledger_records_for_compare(ledger_path_b, issues))
    if issues:
        return ComparisonResult(ok=False, issues=issues)

    _compare_record_sequence(records_a, records_b, issues)

    projected_a = _project_ledger_records(records_a, normalize_run_id=normalize_run_id)
    projected_b = _project_ledger_records(records_b, normalize_run_id=normalize_run_id)
    _compare_projected_records(projected_a, projected_b, issues, strict=strict)
    return ComparisonResult(ok=not issues, issues=issues)


def deterministic_equivalence(
    records_a: Sequence[Mapping[str, Any]],
    records_b: Sequence[Mapping[str, Any]],
    *,
    normalize_run_id: bool = True,
    strict: bool = True,
) -> ComparisonResult:
    """Compare projected ledger records for deterministic equivalence."""
    issues: list[ComparisonIssue] = []
    projected_a = _project_ledger_records(records_a, normalize_run_id=normalize_run_id)
    projected_b = _project_ledger_records(records_b, normalize_run_id=normalize_run_id)
    _compare_projected_records(projected_a, projected_b, issues, strict=strict)
    return ComparisonResult(ok=not issues, issues=issues)


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


def _load_ledger_records_for_compare(
    ledger_path: Path, issues: list[ComparisonIssue]
) -> Iterable[dict[str, Any]]:
    for line_number, raw_line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            _add_comparison_issue(
                issues,
                "ERROR",
                "INVALID_LEDGER_JSON",
                f"Line {line_number}: {exc.msg}",
            )
            continue
        if not isinstance(record, dict):
            _add_comparison_issue(
                issues,
                "ERROR",
                "INVALID_RECORD",
                f"Line {line_number}: ledger record is not an object",
            )
            continue
        yield record


def _project_ledger_records(
    records: Sequence[Mapping[str, Any]],
    *,
    normalize_run_id: bool,
) -> list[dict[str, Any]]:
    return [
        _project_ledger_record(record, normalize_run_id=normalize_run_id)
        for record in records
    ]


def _project_ledger_record(
    record: Mapping[str, Any],
    *,
    normalize_run_id: bool,
) -> dict[str, Any]:
    record_type = record.get("type")
    if not record_type:
        return {}
    projected: dict[str, Any] = {"type": record_type}
    if record_type == "RUN_START":
        _project_run_start(record, projected)
    elif record_type == "STEP_START":
        _project_step_start(record, projected)
    elif record_type == "STEP_EVENT":
        _project_step_event(record, projected)
    elif record_type == "ARTIFACT_WRITTEN":
        _project_artifact_written(record, projected)
    elif record_type == "STEP_END":
        _project_step_end(record, projected)
    elif record_type == "RUN_END":
        _project_run_end(record, projected)
    elif record_type == "RUN_FAIL":
        _project_run_fail(record, projected)
    else:
        return {}
    return projected


def _project_run_start(record: Mapping[str, Any], projected: dict[str, Any]) -> None:
    runtime = _select_keys(record.get("runtime"), ("name", "version"))
    if runtime:
        projected["runtime"] = runtime
    run = _select_keys(record.get("run"), ("mode", "seed"))
    if run:
        projected["run"] = run
    inputs = _project_inputs(record.get("inputs"))
    if inputs:
        projected["inputs"] = inputs


def _project_step_start(record: Mapping[str, Any], projected: dict[str, Any]) -> None:
    step = _select_keys(record.get("step"), ("index", "step_id", "step_version"))
    if step:
        projected["step"] = step
    state_in = _project_sha256_only(record.get("state_in"))
    if state_in:
        projected["state_in"] = state_in


def _project_step_event(record: Mapping[str, Any], projected: dict[str, Any]) -> None:
    step = _select_keys(record.get("step"), ("index", "step_id"))
    if step:
        projected["step"] = step
    event = _select_keys(record.get("event"), ("event_type", "code", "data"))
    if event:
        projected["event"] = event


def _project_artifact_written(record: Mapping[str, Any], projected: dict[str, Any]) -> None:
    step = _select_keys(record.get("step"), ("index", "step_id"))
    if step:
        projected["step"] = step
    artifact = _select_keys(
        record.get("artifact"),
        ("artifact_id", "logical_name", "media_type", "sha256"),
    )
    if artifact:
        projected["artifact"] = artifact


def _project_step_end(record: Mapping[str, Any], projected: dict[str, Any]) -> None:
    step = _select_keys(record.get("step"), ("index", "step_id"))
    if step:
        projected["step"] = step
    status = record.get("status")
    if status is not None:
        projected["status"] = status
    state_out = _project_sha256_only(record.get("state_out"))
    if state_out:
        projected["state_out"] = state_out


def _project_run_end(record: Mapping[str, Any], projected: dict[str, Any]) -> None:
    status = record.get("status")
    if status is not None:
        projected["status"] = status
    final_state = _project_sha256_only(record.get("final_state"))
    if final_state:
        projected["final_state"] = final_state


def _project_run_fail(record: Mapping[str, Any], projected: dict[str, Any]) -> None:
    status = record.get("status")
    if status is not None:
        projected["status"] = status
    failed_step = _select_keys(record.get("step"), ("index", "step_id"))
    if failed_step:
        projected["failed_step"] = failed_step
    error = record.get("error")
    if isinstance(error, Mapping):
        projected_error: dict[str, Any] = {}
        exc_type = error.get("type")
        if exc_type is not None:
            projected_error["exc_type"] = exc_type
        code = error.get("code")
        if code is not None:
            projected_error["code"] = code
        message = error.get("message")
        if message is not None:
            projected_error["message"] = message
        if projected_error:
            projected["error"] = projected_error


def _project_inputs(inputs: Any) -> dict[str, Any]:
    if not isinstance(inputs, Mapping):
        return {}
    projected_inputs: dict[str, Any] = {}
    for key, payload in inputs.items():
        sha_payload = _project_sha256_only(payload)
        if sha_payload:
            projected_inputs[key] = sha_payload
    return projected_inputs


def _project_sha256_only(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping) and "sha256" in payload:
        return {"sha256": payload.get("sha256")}
    return {}


def _select_keys(payload: Any, keys: Iterable[str]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    selected: dict[str, Any] = {}
    for key in keys:
        if key in payload:
            selected[key] = payload[key]
    return selected


def _compare_projected_records(
    records_a: Sequence[Mapping[str, Any]],
    records_b: Sequence[Mapping[str, Any]],
    issues: list[ComparisonIssue],
    *,
    strict: bool,
) -> None:
    if len(records_a) != len(records_b):
        _add_comparison_issue(
            issues,
            "ERROR",
            "RECORD_COUNT_MISMATCH",
            f"Record count mismatch: {len(records_a)} != {len(records_b)}",
        )

    for index, (record_a, record_b) in enumerate(zip(records_a, records_b)):
        if record_a == record_b:
            continue
        diffs = _diff_fields(record_a, record_b)
        if not diffs:
            continue
        lenient_fields = {"runtime.version", "inputs.env.sha256"}
        lenient_diffs = [diff for diff in diffs if diff[0] in lenient_fields]
        hard_diffs = [diff for diff in diffs if diff[0] not in lenient_fields]
        context = _format_record_context(record_a or record_b)
        if hard_diffs:
            _add_comparison_issue(
                issues,
                "ERROR",
                "RECORD_MISMATCH",
                _format_record_mismatch_message(index, context, hard_diffs),
            )
        if lenient_diffs and not strict:
            _add_comparison_issue(
                issues,
                "WARN",
                "RECORD_MISMATCH",
                _format_record_mismatch_message(index, context, lenient_diffs),
            )
        elif lenient_diffs and strict:
            _add_comparison_issue(
                issues,
                "ERROR",
                "RECORD_MISMATCH",
                _format_record_mismatch_message(index, context, lenient_diffs),
            )


def _compare_record_sequence(
    records_a: Sequence[Mapping[str, Any]],
    records_b: Sequence[Mapping[str, Any]],
    issues: list[ComparisonIssue],
) -> None:
    if len(records_a) != len(records_b):
        _add_comparison_issue(
            issues,
            "ERROR",
            "RECORD_COUNT_MISMATCH",
            f"Record count mismatch: {len(records_a)} != {len(records_b)}",
        )

    for index, (record_a, record_b) in enumerate(zip(records_a, records_b)):
        type_a = record_a.get("type")
        type_b = record_b.get("type")
        if type_a != type_b:
            _add_comparison_issue(
                issues,
                "ERROR",
                "TYPE_SEQUENCE_MISMATCH",
                (
                    "Record type mismatch at index "
                    f"{index}: {type_a!r} != {type_b!r}"
                ),
            )


def _diff_fields(
    record_a: Mapping[str, Any],
    record_b: Mapping[str, Any],
) -> list[tuple[str, Any, Any]]:
    diffs: list[tuple[str, Any, Any]] = []

    def walk(path: str, value_a: Any, value_b: Any) -> None:
        if isinstance(value_a, Mapping) and isinstance(value_b, Mapping):
            keys = sorted(set(value_a.keys()) | set(value_b.keys()))
            for key in keys:
                next_path = f"{path}.{key}" if path else str(key)
                if key in value_a and key in value_b:
                    walk(next_path, value_a[key], value_b[key])
                else:
                    diffs.append((next_path, value_a.get(key), value_b.get(key)))
            return
        if value_a != value_b:
            diffs.append((path or "<root>", value_a, value_b))

    walk("", record_a, record_b)
    return diffs


def _format_record_context(record: Mapping[str, Any]) -> str:
    parts: list[str] = []
    record_type = record.get("type")
    if record_type:
        parts.append(f"type={record_type}")
    step_payload = record.get("step") or record.get("failed_step")
    if isinstance(step_payload, Mapping):
        step_index = step_payload.get("index")
        step_id = step_payload.get("step_id")
        if step_index is not None:
            parts.append(f"step.index={step_index}")
        if step_id is not None:
            parts.append(f"step.step_id={step_id}")
    return ", ".join(parts) if parts else "type=<unknown>"


def _format_record_mismatch_message(
    index: int,
    context: str,
    diffs: Sequence[tuple[str, Any, Any]],
) -> str:
    details = ", ".join(
        f"{field}: {value_a!r} != {value_b!r}" for field, value_a, value_b in diffs
    )
    return f"Record mismatch at index {index} ({context}): {details}"


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
    state = "START"
    step_open = False
    saw_run_start = False
    saw_terminal = False

    for record in records:
        record_type = record.get("type")
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


def _add_comparison_issue(
    issues: list[ComparisonIssue], level: str, code: str, message: str
) -> None:
    issues.append(ComparisonIssue(level=level, code=code, message=message))
