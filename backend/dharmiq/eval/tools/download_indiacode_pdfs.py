from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

from dharmiq.config.settings import REPO_ROOT
from dharmiq.eval.tools.allowlist import (
    load_allowlist,
    resolve_pdf_source,
    source_id_to_filename,
)
from dharmiq.eval.tools.indiacode_http import (
    DEFAULT_HEADERS,
    fetch_pdf_with_fallback,
    iter_pdf_url_candidates,
)


def _default_allowlist() -> Path:
    return REPO_ROOT / "docs" / "plans" / "v0.6" / "central-corpus-allowlist.yaml"


def _default_corpus_dir() -> Path:
    return REPO_ROOT / "data" / "corpus" / "india_code" / "raw"


def download_pdfs(
    *,
    allowlist_path: Path,
    corpus_dir: Path,
    probe: bool = False,
    write: bool = False,
    limit: int | None = None,
    delay_s: float = 0.5,
    continue_on_error: bool = False,
    source_ids: list[str] | None = None,
) -> int:
    instruments = load_allowlist(allowlist_path)
    if source_ids:
        wanted = set(source_ids)
        instruments = [item for item in instruments if item.id in wanted]
    if limit is not None:
        instruments = instruments[:limit]

    written_urls: dict[str, Path] = {}
    failures: list[str] = []

    with httpx.Client(
        timeout=90,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
    ) as client:
        for index, instrument in enumerate(instruments):
            if delay_s and index:
                time.sleep(delay_s)

            pdf_source = resolve_pdf_source(instrument)
            fetched = fetch_pdf_with_fallback(client, instrument)

            if probe:
                if fetched is None:
                    candidates = iter_pdf_url_candidates(client, instrument)
                    tried = ", ".join(label for label, _ in candidates) or "none"
                    msg = (
                        f"{instrument.id}: all PDF candidates failed "
                        f"({pdf_source}; tried: {tried})"
                    )
                    failures.append(msg)
                    print(f"FAIL\t{instrument.id}\t{pdf_source}\t-\t-\t{msg}")
                    continue

                content, pdf_url, label = fetched
                print(
                    f"OK\t{instrument.id}\t{pdf_source}\t200\t"
                    f"{len(content)}\t{label}\t{pdf_url}"
                )
                continue

            if not write:
                candidates = iter_pdf_url_candidates(client, instrument)
                if not candidates:
                    print(f"  {instrument.id:32} {pdf_source:18} (no candidates)")
                    continue
                label, pdf_url = candidates[0]
                suffix = (
                    f" +{len(candidates) - 1} alt"
                    if len(candidates) > 1
                    else ""
                )
                print(f"  {instrument.id:32} {pdf_source:18} {label}{suffix}")
                continue

            if fetched is None:
                msg = f"{instrument.id}: all PDF candidates failed ({pdf_source})"
                failures.append(msg)
                print(f"FAIL {msg}", file=sys.stderr)
                continue

            content, pdf_url, label = fetched

            if pdf_url in written_urls:
                target = corpus_dir / source_id_to_filename(instrument.id)
                source_file = written_urls[pdf_url]
                if source_file.is_file():
                    target.write_bytes(source_file.read_bytes())
                    print(f"  alias {instrument.id} -> {source_file.name}")
                    continue

            corpus_dir.mkdir(parents=True, exist_ok=True)
            target = corpus_dir / source_id_to_filename(instrument.id)
            target.write_bytes(content)
            written_urls[pdf_url] = target
            via = f" via {label}" if label != "primary" else ""
            print(f"  wrote {target.name} ({len(content)} bytes){via}")

    if failures and not continue_on_error:
        return 1
    return 0 if not failures else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download IndiaCode PDFs for a corpus allowlist (v0.6 P0)",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=_default_allowlist(),
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=_default_corpus_dir(),
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Print resolved PDF URLs without writing files",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Download PDFs to --corpus-dir",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Exit 0 even if some instruments fail",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        dest="source_ids",
        default=None,
        help="Limit to specific source_id (repeatable)",
    )
    args = parser.parse_args()

    if not args.allowlist.is_file():
        print(f"Error: allowlist not found: {args.allowlist}", file=sys.stderr)
        raise SystemExit(1)

    if not args.probe and not args.write:
        args.probe = True

    exit_code = download_pdfs(
        allowlist_path=args.allowlist,
        corpus_dir=args.corpus_dir,
        probe=args.probe and not args.write,
        write=args.write,
        limit=args.limit,
        delay_s=args.delay,
        continue_on_error=args.continue_on_error,
        source_ids=args.source_ids,
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
