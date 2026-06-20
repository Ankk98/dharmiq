from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher


DEFAULT_MIN_SIMILARITY = 0.95
ACT_ABBREVIATIONS = frozenset({"crpc", "cpc", "ipc", "itc", "gst", "bnss", "bsa"})


@dataclass(frozen=True)
class QuoteMatch:
    quote_text: str
    start_char: int
    end_char: int
    similarity: float


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("§", "section ")
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    tokens = [
        token
        for token in re.sub(r"\s+", " ", normalized).strip().casefold().split()
        if token not in ACT_ABBREVIATIONS
    ]
    return " ".join(tokens)


def span_similarity(left: str, right: str) -> float:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def quotes_match(quote: str, source_span: str, *, min_similarity: float = DEFAULT_MIN_SIMILARITY) -> bool:
    return span_similarity(quote, source_span) >= min_similarity


def _word_spans(text: str) -> list[tuple[str, int, int]]:
    return [(match.group(), match.start(), match.end()) for match in re.finditer(r"\S+", text)]


def find_quote_span(
    quote: str,
    chunk_text: str,
    *,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> QuoteMatch | None:
    quote_norm = normalize_text(quote)
    if not quote_norm:
        return None

    words = _word_spans(chunk_text)
    if not words:
        return None

    target_words = len(quote_norm.split())
    best: QuoteMatch | None = None

    for start_idx in range(len(words)):
        min_len = max(1, target_words - 2)
        max_len = min(len(words) - start_idx, target_words + 2)
        for length in range(min_len, max_len + 1):
            end_idx = start_idx + length
            start_char = words[start_idx][1]
            end_char = words[end_idx - 1][2]
            span = chunk_text[start_char:end_char]
            similarity = span_similarity(quote, span)
            if similarity < min_similarity:
                continue
            candidate = QuoteMatch(
                quote_text=span,
                start_char=start_char,
                end_char=end_char,
                similarity=similarity,
            )
            if best is None or candidate.similarity > best.similarity:
                best = candidate

    return best


def extract_blockquotes(text: str) -> list[str]:
    quotes: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            quote = stripped.lstrip(">").strip()
            if quote:
                quotes.append(quote)
    return quotes
