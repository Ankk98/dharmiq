from __future__ import annotations

from typing import Any


class DharmiqError(Exception):
    """Base exception for Dharmiq application errors."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(DharmiqError):
    """Raised when configuration is invalid or missing."""


class DatabaseError(DharmiqError):
    """Raised for database connectivity or query failures."""
