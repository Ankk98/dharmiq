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


class OpenRouterError(DharmiqError):
    """Raised when OpenRouter API calls fail after retries."""


class EmbeddingError(DharmiqError):
    """Raised when embedding generation fails."""


class IngestionError(DharmiqError):
    """Raised when corpus ingestion or PDF processing fails."""


class UploadError(DharmiqError):
    """Raised when user upload validation or storage fails."""


class EvalError(DharmiqError):
    """Raised when evaluation cannot run (missing corpus, config, etc.)."""


class InputValidationError(DharmiqError):
    """Raised when chat input fails guardrail validation."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "INPUT_INVALID",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.code = code


class RateLimitExceededError(DharmiqError):
    """Raised when a user exceeds configured chat rate limits."""

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after_seconds = retry_after_seconds
