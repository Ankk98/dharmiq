from __future__ import annotations

import re
import unicodedata


def normalize_for_comparison(text: str) -> str:
    """NFKC normalize, collapse whitespace, lowercase for duplicate detection."""
    normalized = unicodedata.normalize("NFKC", text)
    collapsed = re.sub(r"\s+", " ", normalized).strip().lower()
    return collapsed
