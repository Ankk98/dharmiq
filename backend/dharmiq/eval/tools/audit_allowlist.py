from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

from dharmiq.config.settings import REPO_ROOT
from dharmiq.eval.tools.allowlist import (
    CENTRAL_HANDLE_RE,
    VALID_PDF_SOURCES,
    VALID_STATUSES,
    V06_DOMAINS,
    load_allowlist,
    load_allowlist_domains,
)
from dharmiq.eval.tools.indiacode_http import (
    DEFAULT_HEADERS,
    fetch_pdf_with_fallback,
    iter_pdf_url_candidates,
)


def _default_allowlist() -> Path:
    return REPO_ROOT / "docs" / "plans" / "v0.6" / "central-corpus-allowlist.yaml"


def _default_mvp_allowlist() -> Path:
    return REPO_ROOT / "docs" / "plans" / "v0.5" / "mvp-corpus-allowlist.yaml"


def _load_mvp_ids(path: Path) -> set[str]:
    return {item.id for item in load_allowlist(path)}


def audit_allowlist_yaml(
    allowlist_path: Path,
    *,
    expected_count: int | None = 62,
    mvp_allowlist_path: Path | None = None,
) -> list[str]:
    """Validate allowlist structure; return list of error messages."""
    errors: list[str] = []
    grouped = load_allowlist_domains(allowlist_path)
    instruments = [item for items in grouped.values() for item in items]

    if expected_count is not None and len(instruments) != expected_count:
        errors.append(
            f"expected {expected_count} instruments, found {len(instruments)}"
        )

    domain_keys = set(grouped)
    if not domain_keys.issubset(V06_DOMAINS):
        extra = sorted(domain_keys - V06_DOMAINS)
        errors.append(f"unexpected domains: {extra}")

    seen_ids: set[str] = set()
    for instrument in instruments:
        if instrument.id in seen_ids:
            errors.append(f"duplicate id: {instrument.id}")
        seen_ids.add(instrument.id)

        if instrument.status not in VALID_STATUSES:
            errors.append(
                f"{instrument.id}: invalid status {instrument.status!r}"
            )

        if instrument.jurisdiction != "central":
            errors.append(
                f"{instrument.id}: jurisdiction must be central, "
                f"got {instrument.jurisdiction!r}"
            )

        if instrument.pdf_source and instrument.pdf_source not in VALID_PDF_SOURCES:
            errors.append(
                f"{instrument.id}: invalid pdf_source {instrument.pdf_source!r}"
            )

        if instrument.pdf_source in {
            "parent_view_file",
            "bundle",
            "subset",
            "external",
        } and not instrument.pdf_url:
            errors.append(f"{instrument.id}: pdf_url required for {instrument.pdf_source}")

        if instrument.pdf_source != "external":
            if not instrument.canonical_url:
                errors.append(f"{instrument.id}: missing canonical_url")
            elif not CENTRAL_HANDLE_RE.match(instrument.canonical_url):
                errors.append(
                    f"{instrument.id}: non-central canonical_url "
                    f"{instrument.canonical_url}"
                )

    mvp_path = mvp_allowlist_path or _default_mvp_allowlist()
    if mvp_path.is_file():
        mvp_ids = _load_mvp_ids(mvp_path)
        v06_ids = {item.id for item in instruments}
        missing = sorted(mvp_ids - v06_ids)
        if missing:
            errors.append(f"MVP ids missing from v0.6 allowlist: {missing}")

    required_superseded = {
        "IN-IPC-1860": "IN-BNS-2023",
        "IN-CRPC-1973": "IN-BNSS-2023",
        "IN-CPA-1986": "IN-CPA-2019",
    }
    by_id = {item.id: item for item in instruments}
    for source_id, replacement in required_superseded.items():
        row = by_id.get(source_id)
        if row is None:
            errors.append(f"missing superseded instrument {source_id}")
        elif row.status != "superseded":
            errors.append(f"{source_id}: expected status=superseded")
        elif row.superseded_by != replacement:
            errors.append(
                f"{source_id}: expected superseded_by={replacement}, "
                f"got {row.superseded_by!r}"
            )

    return errors


def verify_handles(
    allowlist_path: Path,
    *,
    timeout: float = 90.0,
) -> list[str]:
    errors: list[str] = []
    instruments = load_allowlist(allowlist_path)

    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
    ) as client:
        for instrument in instruments:
            if instrument.pdf_source == "external":
                continue
            if instrument.pdf_source in {"parent_view_file", "subset", "bundle"}:
                if instrument.canonical_url:
                    response = client.get(instrument.canonical_url)
                    if response.status_code != 200:
                        errors.append(
                            f"{instrument.id}: parent handle HTTP {response.status_code}"
                        )
                continue

            if not instrument.canonical_url:
                errors.append(f"{instrument.id}: missing canonical_url")
                continue

            response = client.get(instrument.canonical_url)
            if response.status_code != 200:
                errors.append(
                    f"{instrument.id}: handle HTTP {response.status_code} "
                    f"({instrument.canonical_url})"
                )
                continue

            if "/bitstream/123456789/" not in response.text and not instrument.pdf_url:
                errors.append(
                    f"{instrument.id}: handle page has no bitstream and no pdf_url"
                )

    return errors


def verify_pdf_sources(
    allowlist_path: Path,
    *,
    timeout: float = 90.0,
) -> list[str]:
    errors: list[str] = []
    instruments = load_allowlist(allowlist_path)

    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
    ) as client:
        for instrument in instruments:
            fetched = fetch_pdf_with_fallback(client, instrument)
            if fetched is None:
                candidates = iter_pdf_url_candidates(client, instrument)
                tried = ", ".join(url for _, url in candidates) or "none"
                errors.append(
                    f"{instrument.id}: no working PDF URL (tried: {tried})"
                )

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit v0.6 central corpus allowlist YAML",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=_default_allowlist(),
    )
    parser.add_argument(
        "--mvp-allowlist",
        type=Path,
        default=_default_mvp_allowlist(),
    )
    parser.add_argument(
        "--verify-handles",
        action="store_true",
        help="GET each canonical_url; require HTTP 200",
    )
    parser.add_argument(
        "--verify-pdf-sources",
        action="store_true",
        help="GET each resolved PDF; require %%PDF and size >= 5000",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=62,
    )
    args = parser.parse_args()

    if not args.allowlist.is_file():
        print(f"Error: allowlist not found: {args.allowlist}", file=sys.stderr)
        raise SystemExit(1)

    errors = audit_allowlist_yaml(
        args.allowlist,
        expected_count=args.expected_count,
        mvp_allowlist_path=args.mvp_allowlist,
    )
    if args.verify_handles:
        errors.extend(verify_handles(args.allowlist))
    if args.verify_pdf_sources:
        errors.extend(verify_pdf_sources(args.allowlist))

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        raise SystemExit(1)

    count = len(load_allowlist(args.allowlist))
    print(f"audit_allowlist OK ({count} instruments)")


if __name__ == "__main__":
    main()
