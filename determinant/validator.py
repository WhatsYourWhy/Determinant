"""Ledger validation utilities."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    """Validate a run directory (placeholder)."""
    raise NotImplementedError("validate_run is not implemented yet.")
