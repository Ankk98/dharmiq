from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dharmiq.config.settings import REPO_ROOT
from dharmiq.eval.tools.allowlist import build_manifest_entries, load_allowlist

DOWNLOAD_HELP = """\
Operational steps to populate the MVP corpus:

1. Clone indian-law-dataset-scraper and fetch central instruments:
     git clone https://github.com/your-org/indian-law-dataset-scraper
     cd indian-law-dataset-scraper
     indiacode init
     indiacode metadata --scope central
     indiacode download --scope central --extract-text --resume

2. Copy PDFs for each allowlist instrument into:
     data/corpus/india_code/raw/

   Rename each PDF to match the manifest `file` field (e.g. cpa_2019.pdf).
   Use `scraper_instrument_id` / `india_code_handle` from the allowlist YAML.

3. Generate manifest.json:
     cd backend
     uv run python -m dharmiq.eval.tools.build_manifest \\
       --allowlist ../docs/plans/v0.5/mvp-corpus-allowlist.yaml \\
       --corpus-dir ../data/corpus/india_code/raw \\
       --write

4. Sync into Postgres:
     uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs

5. Verify indexing:
     uv run python -m dharmiq.eval.tools.verify_corpus_index \\
       --allowlist ../docs/plans/v0.5/mvp-corpus-allowlist.yaml
"""


def _default_allowlist() -> Path:
    return REPO_ROOT / "docs" / "plans" / "v0.5" / "mvp-corpus-allowlist.yaml"


def _default_corpus_dir() -> Path:
    return REPO_ROOT / "data" / "corpus" / "india_code" / "raw"


def build_manifest(
    *,
    allowlist_path: Path,
    corpus_dir: Path,
    write: bool = False,
) -> list[dict[str, str]]:
    instruments = load_allowlist(allowlist_path)
    entries = build_manifest_entries(instruments)

    missing_pdfs: list[str] = []
    for entry in entries:
        pdf_path = corpus_dir / entry["file"]
        status = "ok" if pdf_path.is_file() else "MISSING"
        if status == "MISSING":
            missing_pdfs.append(entry["file"])
        print(f"  {entry['file']:40} {entry['source_id']:22} [{status}]")

    print(f"\nTotal instruments: {len(entries)}")
    if missing_pdfs:
        print(f"Missing PDFs on disk: {len(missing_pdfs)}")
        for name in missing_pdfs:
            print(f"  - {name}")

    if write:
        corpus_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = corpus_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote {manifest_path}")

    return entries


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build manifest.json from the MVP corpus allowlist YAML",
        epilog=DOWNLOAD_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=_default_allowlist(),
        help="Path to mvp-corpus-allowlist.yaml",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=_default_corpus_dir(),
        help="Corpus directory containing PDFs and manifest.json",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write manifest.json to --corpus-dir",
    )
    args = parser.parse_args()

    if not args.allowlist.is_file():
        print(f"Error: allowlist not found: {args.allowlist}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Allowlist: {args.allowlist}")
    print(f"Corpus dir: {args.corpus_dir}")
    print("Expected files:")
    build_manifest(
        allowlist_path=args.allowlist,
        corpus_dir=args.corpus_dir,
        write=args.write,
    )


if __name__ == "__main__":
    main()
