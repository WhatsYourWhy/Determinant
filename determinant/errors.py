"""Custom error types for Determinant."""


class DeterminantError(Exception):
    """Base error for Determinant."""


class LedgerValidationError(DeterminantError):
    """Raised when ledger validation fails."""
