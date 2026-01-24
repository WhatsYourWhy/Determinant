"""Ledger validation utilities."""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from .hashing import sha256_bytes
from .json_canonical import canonical_json_bytes
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
    ledger_bytes: bytes | None = None
    last_hash: str | None = None

    if ledger_path.exists():
        ledger_bytes = ledger_path.read_bytes()
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
            last_hash = previous_hash
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
        if ledger_bytes is not None:
            expected_ledger_hash = manifest.get("ledger_sha256")
            if expected_ledger_hash and sha256_bytes(ledger_bytes) != expected_ledger_hash:
                issues.append(
                    ValidationIssue(
                        level="ERROR",
                        code="LEDGER_HASH_MISMATCH",
                        message="ledger.ndjson hash does not match manifest.",
                    )
                )
        expected_chain_head = manifest.get("chain_head_hash")
        if expected_chain_head and expected_chain_head != last_hash:
            issues.append(
                ValidationIssue(
                    level="ERROR",
                    code="HASH_CHAIN_BROKEN",
                    message="Chain head hash does not match manifest.",
                )
            )
        for entry in _collect_manifest_hash_entries(manifest):
            file_path = run_path / entry.path
            if not file_path.exists():
                issues.append(
                    ValidationIssue(
                        level="ERROR",
                        code="REFERENCED_FILE_MISSING",
                        message=f"{entry.label} missing: {entry.path}",
                    )
                )
                continue
            actual_hash = sha256_bytes(file_path.read_bytes())
            if actual_hash != entry.sha256:
                issues.append(
                    ValidationIssue(
                        level="ERROR",
                        code="REFERENCED_FILE_HASH_MISMATCH",
                        message=f"{entry.label} hash mismatch for {entry.path}.",
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
    ledger_path_a = Path(run_dir_a) / "ledger.ndjson"
    ledger_path_b = Path(run_dir_b) / "ledger.ndjson"
    if not ledger_path_a.exists():
        issues.append(
            ValidationIssue(
                level="ERROR",
                code="LEDGER_MISSING",
                message=f"ledger.ndjson is missing for {run_dir_a}.",
            )
        )
    if not ledger_path_b.exists():
        issues.append(
            ValidationIssue(
                level="ERROR",
                code="LEDGER_MISSING",
                message=f"ledger.ndjson is missing for {run_dir_b}.",
            )
        )
    records_a = _load_projected_records(ledger_path_a)
    records_b = _load_projected_records(ledger_path_b)
    if len(records_a) != len(records_b):
        issues.append(
            ValidationIssue(
                level="ERROR",
                code="RUN_LENGTH_MISMATCH",
                message=(
                    "Run ledgers differ in length after normalization: "
                    f"{len(records_a)} vs {len(records_b)}."
                ),
            )
        )
    for index, (record_a, record_b) in enumerate(
        zip(records_a, records_b), start=1
    ):
        if record_a != record_b:
            type_a = record_a.get("type", "<unknown>")
            type_b = record_b.get("type", "<unknown>")
            issues.append(
                ValidationIssue(
                    level="ERROR",
                    code="RUN_RECORD_MISMATCH",
                    message=(
                        f"Record {index} differs after normalization: "
                        f"{type_a} vs {type_b}."
                    ),
                )
            )
    return ValidationResult(ok=not issues, issues=issues)


@dataclass(frozen=True)
class ManifestHashEntry:
    path: str
    sha256: str
    label: str


def _collect_manifest_hash_entries(
    manifest: dict[str, Any],
) -> list[ManifestHashEntry]:
    entries: list[ManifestHashEntry] = []

    def add_entry(info: Any, label: str) -> None:
        if not isinstance(info, dict):
            return
        path = info.get("path")
        sha256 = info.get("sha256")
        if isinstance(path, str) and isinstance(sha256, str):
            entries.append(ManifestHashEntry(path=path, sha256=sha256, label=label))

    inputs = manifest.get("inputs", {})
    add_entry(inputs.get("graph"), "inputs.graph")
    add_entry(inputs.get("config"), "inputs.config")
    add_entry(inputs.get("env"), "inputs.env")
    add_entry(inputs.get("initial_state"), "inputs.initial_state")

    for step_index, step in enumerate(manifest.get("steps", [])):
        add_entry(step.get("state_in"), f"steps[{step_index}].state_in")
        add_entry(step.get("state_out"), f"steps[{step_index}].state_out")
        for artifact_index, artifact in enumerate(step.get("artifacts", [])):
            add_entry(
                artifact,
                f"steps[{step_index}].artifacts[{artifact_index}]",
            )

    for artifact_index, artifact in enumerate(manifest.get("artifacts", [])):
        add_entry(artifact, f"artifacts[{artifact_index}]")

    add_entry(manifest.get("final_state"), "final_state")
    return entries


def _load_projected_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        records.append(_project_record(record))
    return records


def _project_record(record: dict[str, Any]) -> dict[str, Any]:
    record_type = record.get("type")
    projection: dict[str, Any] = {"type": record_type}
    if record_type == "RUN_START":
        projection["runtime"] = {
            "name": record.get("runtime", {}).get("name"),
            "version": record.get("runtime", {}).get("version"),
        }
        run_info = record.get("run", {})
        projection["run"] = {"mode": run_info.get("mode"), "seed": run_info.get("seed")}
        inputs = record.get("inputs", {})
        projection["inputs"] = {
            "graph": inputs.get("graph", {}).get("sha256"),
            "config": inputs.get("config", {}).get("sha256"),
            "env": inputs.get("env", {}).get("sha256"),
            "initial_state": inputs.get("initial_state", {}).get("sha256"),
        }
        return projection
    if record_type == "STEP_START":
        step_info = record.get("step", {})
        projection["step"] = {
            "index": step_info.get("index"),
            "step_id": step_info.get("step_id"),
            "step_version": step_info.get("step_version"),
            "graph_node_id": step_info.get("graph_node_id"),
        }
        projection["state_in"] = record.get("state_in", {}).get("sha256")
        return projection
    if record_type == "STEP_EVENT":
        step_info = record.get("step", {})
        projection["step"] = {
            "index": step_info.get("index"),
            "step_id": step_info.get("step_id"),
        }
        event = record.get("event", {})
        projection["event"] = {
            "event_type": event.get("event_type"),
            "code": event.get("code"),
            "data": _canonicalize_event_data(event.get("data")),
        }
        return projection
    if record_type == "ARTIFACT_WRITTEN":
        step_info = record.get("step", {})
        artifact = record.get("artifact", {})
        projection["step"] = {
            "index": step_info.get("index"),
            "step_id": step_info.get("step_id"),
        }
        projection["artifact"] = {
            "artifact_id": artifact.get("artifact_id"),
            "logical_name": artifact.get("logical_name"),
            "media_type": artifact.get("media_type"),
            "path": artifact.get("path"),
            "sha256": artifact.get("sha256"),
            "size_bytes": artifact.get("size_bytes"),
        }
        return projection
    if record_type == "STEP_END":
        step_info = record.get("step", {})
        projection["step"] = {
            "index": step_info.get("index"),
            "step_id": step_info.get("step_id"),
        }
        projection["status"] = record.get("status")
        projection["state_out"] = record.get("state_out", {}).get("sha256")
        return projection
    if record_type == "RUN_END":
        rollup = record.get("rollup", {})
        projection["status"] = record.get("status")
        projection["final_state"] = record.get("final_state", {}).get("sha256")
        projection["rollup"] = {
            "steps_ok": rollup.get("steps_ok"),
            "steps_failed": rollup.get("steps_failed"),
            "artifacts": rollup.get("artifacts"),
        }
        return projection
    if record_type == "RUN_FAIL":
        failed_step = record.get("failed_step", {})
        error = record.get("error", {})
        projection["failed_step"] = {
            "index": failed_step.get("index"),
            "step_id": failed_step.get("step_id"),
        }
        projection["error"] = {
            "exc_type": error.get("exc_type"),
            "code": error.get("code"),
            "message": error.get("message"),
            "trace": error.get("trace"),
        }
        return projection
    return projection


def _canonicalize_event_data(data: Any) -> str | None:
    if data is None:
        return None
    return canonical_json_bytes(data).decode("utf-8")
