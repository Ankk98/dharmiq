from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

from dharmiq.config.settings import REPO_ROOT
from dharmiq.eval.tools.allowlist import load_allowlist, source_id_to_filename


def _default_allowlist() -> Path:
    return REPO_ROOT / "docs" / "plans" / "v0.6" / "central-corpus-allowlist.yaml"


def _default_corpus_dir() -> Path:
    return REPO_ROOT / "data" / "corpus" / "india_code" / "raw"


def _find_scraper_pdf(
    conn: sqlite3.Connection,
    scraper_instrument_id: str,
    pdfs_dir: Path,
) -> Path | None:
    row = conn.execute(
        """
        SELECT ivf.file_path
        FROM instrument_version_files ivf
        JOIN instrument_versions iv ON iv.version_id = ivf.version_id
        JOIN instruments i ON i.instrument_id = iv.instrument_id
        WHERE i.instrument_id = ? AND ivf.file_path IS NOT NULL
        ORDER BY iv.version_id DESC
        LIMIT 1
        """,
        (scraper_instrument_id,),
    ).fetchone()
    if not row or not row[0]:
        return None
    candidate = pdfs_dir / row[0]
    if candidate.is_file():
        return candidate
    alt = Path(row[0])
    if alt.is_file():
        return alt
    return None


def copy_pdfs_from_scraper(
    *,
    allowlist_path: Path,
    corpus_dir: Path,
    scraper_db: Path,
    pdfs_dir: Path,
) -> int:
    if not scraper_db.is_file():
        print(f"Error: scraper DB not found: {scraper_db}", file=sys.stderr)
        return 1

    instruments = load_allowlist(allowlist_path)
    conn = sqlite3.connect(scraper_db)
    copied = 0
    missing = 0

    corpus_dir.mkdir(parents=True, exist_ok=True)
    for instrument in instruments:
        if not instrument.scraper_instrument_id:
            continue
        source_pdf = _find_scraper_pdf(
            conn,
            instrument.scraper_instrument_id,
            pdfs_dir,
        )
        if source_pdf is None:
            missing += 1
            print(
                f"  skip {instrument.id}: no scraper PDF "
                f"(instrument_id={instrument.scraper_instrument_id})"
            )
            continue
        target = corpus_dir / source_id_to_filename(instrument.id)
        shutil.copy2(source_pdf, target)
        copied += 1
        print(f"  copied {instrument.id} -> {target.name}")

    conn.close()
    print(f"\nCopied {copied} PDFs; {missing} without scraper files")
    return 0 if copied or missing == len(instruments) else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Optional: copy PDFs from indian-law-dataset-scraper pdfs_dir",
    )
    parser.add_argument("--allowlist", type=Path, default=_default_allowlist())
    parser.add_argument("--corpus-dir", type=Path, default=_default_corpus_dir())
    parser.add_argument("--scraper-db", type=Path, required=True)
    parser.add_argument(
        "--pdfs-dir",
        type=Path,
        required=True,
        help="Scraper pdfs_dir (instrument_version_files paths are relative to this)",
    )
    parser.add_argument(
        "--copy-pdfs",
        action="store_true",
        help="Copy matching PDFs into corpus-dir",
    )
    args = parser.parse_args()

    if not args.copy_pdfs:
        parser.error("--copy-pdfs is required to copy files")

    raise SystemExit(
        copy_pdfs_from_scraper(
            allowlist_path=args.allowlist,
            corpus_dir=args.corpus_dir,
            scraper_db=args.scraper_db,
            pdfs_dir=args.pdfs_dir,
        )
    )


if __name__ == "__main__":
    main()
