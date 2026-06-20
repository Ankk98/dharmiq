from __future__ import annotations

import re

from pydantic import BaseModel, Field

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior)\s+(instructions|rules)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+prompt|hidden\s+instructions)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(in\s+)?(developer|admin|unrestricted)\s+mode", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+)?you\s+(have\s+)?no\s+(rules|restrictions|limits)", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"\bDAN\s+mode\b", re.IGNORECASE),
)

_OFF_TOPIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"write\s+(me\s+)?(a\s+)?poem\b", re.IGNORECASE),
    re.compile(r"write\s+(me\s+)?(a\s+)?(short\s+)?story\b", re.IGNORECASE),
    re.compile(r"tell\s+(me\s+)?(a\s+)?joke\b", re.IGNORECASE),
    re.compile(r"write\s+(me\s+)?(a\s+)?recipe\b", re.IGNORECASE),
    re.compile(r"compose\s+(a\s+)?song\b", re.IGNORECASE),
    re.compile(r"write\s+(me\s+)?(a\s+)?haiku\b", re.IGNORECASE),
)

_LEGAL_SIGNAL_PATTERN = re.compile(
    r"\b("
    r"law|legal|rights?|act|section|article|court|police|employer|employee|contract|"
    r"constitution|bail|arrest|notice|termination|consumer|statutory|regulation|"
    r"compliance|tribunal|petition|divorce|property|lease|tenant|landlord|tax|wage|"
    r"salary|harassment|fir|appeal|clause|provision|penalty|offen[cs]e|damages|"
    r"compensation|liability|agreement|cheque|rti|crpc|ipc|statute|counsel|lawyer|"
    r"grievance|complaint|jurisdiction|ordinance|amendment|detention|custody|"
    r"non[- ]compete|indemnity|limitation|writ|mandamus|habeas"
    r")\b|"
    r"section\s+\d+|article\s+\d+",
    re.IGNORECASE,
)


class InputGuardResult(BaseModel):
    allowed: bool
    reason: str | None = None
    code: str | None = None
    risk_flags: list[str] = Field(default_factory=list)


def _has_legal_signal(text: str) -> bool:
    return _LEGAL_SIGNAL_PATTERN.search(text) is not None


def validate_message(text: str, *, max_length: int = 8192) -> InputGuardResult:
    """Validate user chat input before the agent graph runs."""
    normalized = text.strip()
    risk_flags: list[str] = []

    if len(normalized) > max_length:
        return InputGuardResult(
            allowed=False,
            reason=f"Message exceeds the {max_length} character limit.",
            code="INPUT_TOO_LONG",
            risk_flags=["too_long"],
        )

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(normalized):
            risk_flags.append("injection")
            return InputGuardResult(
                allowed=False,
                reason="Your message contains patterns that cannot be processed safely.",
                code="PROMPT_INJECTION",
                risk_flags=risk_flags,
            )

    for pattern in _OFF_TOPIC_PATTERNS:
        if pattern.search(normalized) and not _has_legal_signal(normalized):
            risk_flags.append("off_topic")
            return InputGuardResult(
                allowed=False,
                reason=(
                    "Dharmiq answers Indian legal questions only. "
                    "Please ask about laws, rights, contracts, or legal procedures."
                ),
                code="OFF_TOPIC",
                risk_flags=risk_flags,
            )

    return InputGuardResult(allowed=True)
