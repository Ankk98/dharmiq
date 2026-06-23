"""Shared IndiaCode PDF URL resolution helpers (v0.6 P0)."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from dharmiq.eval.tools.allowlist import AllowlistInstrument

INDIACODE_BASE = "https://www.indiacode.nic.in"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": f"{INDIACODE_BASE}/",
}
BITSTREAM_RE = re.compile(
    r'href="(/bitstream/123456789/\d+/\d+/[^"]+\.pdf[^"]*)"',
    re.IGNORECASE,
)
MIN_PDF_BYTES = 5000
CANDIDATE_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def resolve_handle(instrument: AllowlistInstrument) -> str | None:
    from dharmiq.eval.tools.allowlist import handle_from_canonical_url

    if instrument.india_code_handle:
        return instrument.india_code_handle
    return handle_from_canonical_url(instrument.canonical_url)


def canonical_handle_url(handle: str) -> str:
    return f"{INDIACODE_BASE}/handle/123456789/{handle}"


def pick_bitstream_url(html: str, handle: str) -> str | None:
    """Prefer English bitstream filename; else first PDF for the handle."""
    matches = BITSTREAM_RE.findall(html)
    if not matches:
        return None
    eng = [m for m in matches if re.search(r"eng", m, re.IGNORECASE)]
    chosen = eng[0] if eng else matches[0]
    if chosen.startswith("http"):
        return chosen
    return f"{INDIACODE_BASE}{chosen}"


def iter_pdf_url_candidates(
    client: httpx.Client,
    instrument: AllowlistInstrument,
) -> list[tuple[str, str]]:
    """Return ordered (label, url) PDF candidates: primary, bitstream, then alts."""
    from dharmiq.eval.tools.allowlist import resolve_pdf_source

    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, url: str | None) -> None:
        if url and url not in seen:
            candidates.append((label, url))
            seen.add(url)

    pdf_source = resolve_pdf_source(instrument)
    add("primary", instrument.pdf_url)

    if not instrument.pdf_url and pdf_source == "bitstream":
        handle = resolve_handle(instrument)
        if handle:
            response = client.get(canonical_handle_url(handle))
            if response.status_code == 200:
                add("bitstream", pick_bitstream_url(response.text, handle))

    for index, alt_url in enumerate(instrument.pdf_url_alt, start=1):
        add(f"alt-{index}", alt_url)

    return candidates


def resolve_pdf_url(
    client: httpx.Client,
    instrument: AllowlistInstrument,
    *,
    delay_s: float = 0.0,
) -> tuple[str | None, str]:
    """Return the first candidate URL and pdf_source for an allowlist instrument."""
    from dharmiq.eval.tools.allowlist import resolve_pdf_source

    if delay_s:
        time.sleep(delay_s)

    candidates = iter_pdf_url_candidates(client, instrument)
    if candidates:
        return candidates[0][1], resolve_pdf_source(instrument)
    return None, resolve_pdf_source(instrument)


def fetch_pdf_with_fallback(
    client: httpx.Client,
    instrument: AllowlistInstrument,
) -> tuple[bytes, str, str] | None:
    """Fetch PDF bytes from the first working candidate URL.

    Returns (content, url_used, label) or None when all candidates fail.
    """
    candidates = iter_pdf_url_candidates(client, instrument)
    per_candidate_timeout = CANDIDATE_TIMEOUT if len(candidates) > 1 else None

    for label, url in candidates:
        content, status = fetch_pdf_bytes(
            client,
            url,
            timeout=per_candidate_timeout,
        )
        if status == 200 and is_valid_pdf(content):
            return content, url, label
    return None


def is_valid_pdf(content: bytes) -> bool:
    return content.startswith(b"%PDF") and len(content) >= MIN_PDF_BYTES


def fetch_pdf_bytes(
    client: httpx.Client,
    url: str,
    *,
    timeout: httpx.Timeout | float | None = None,
) -> tuple[bytes, int]:
    try:
        response = client.get(url, timeout=timeout)
        return response.content, response.status_code
    except httpx.HTTPError:
        return b"", 0
