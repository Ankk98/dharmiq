from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import REPO_ROOT, Settings, get_settings
from dharmiq.db.models.documents import DocumentChunk, SourceDocument
from dharmiq.db.session import close_db, get_session_factory, init_db
from dharmiq.eval.tools.allowlist import load_allowlist


def _default_allowlist() -> Path:
    return REPO_ROOT / "docs" / "plans" / "v0.5" / "mvp-corpus-allowlist.yaml"


async def _chunk_counts_by_source_id(db: AsyncSession) -> dict[str, int]:
    stmt = (
        select(SourceDocument.source_id, func.count(DocumentChunk.id))
        .outerjoin(DocumentChunk, DocumentChunk.document_id == SourceDocument.id)
        .group_by(SourceDocument.source_id)
    )
    result = await db.execute(stmt)
    return {row[0]: int(row[1]) for row in result.all()}


async def verify_corpus_index(
    db: AsyncSession,
    *,
    allowlist_path: Path,
) -> tuple[bool, dict]:
    """Return (all_ok, report_dict)."""
    instruments = load_allowlist(allowlist_path)
    expected_ids = [instrument.id for instrument in instruments]
    chunk_counts = await _chunk_counts_by_source_id(db)

    per_document: list[dict] = []
    missing: list[str] = []
    stale: list[str] = []

    for instrument in instruments:
        count = chunk_counts.get(instrument.id, 0)
        status = "ok"
        if instrument.id not in chunk_counts:
            status = "missing"
            missing.append(instrument.id)
        elif count <= 0:
            status = "no_chunks"
            stale.append(instrument.id)
        per_document.append(
            {
                "source_id": instrument.id,
                "title": instrument.title,
                "chunk_count": count,
                "status": status,
            }
        )

    total_chunks = sum(chunk_counts.values())
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "allowlist_path": str(allowlist_path),
        "expected_document_count": len(expected_ids),
        "indexed_document_count": sum(1 for row in per_document if row["status"] == "ok"),
        "corpus_document_count": len(chunk_counts),
        "corpus_chunk_count": total_chunks,
        "missing_source_ids": missing,
        "stale_source_ids": stale,
        "documents": per_document,
    }

    ok_count = report["indexed_document_count"]
    expected = report["expected_document_count"]
    print(f"Indexed: {ok_count}/{expected}")

    for row in per_document:
        if row["status"] != "ok":
            print(
                f"  FAIL {row['source_id']}: {row['status']} (chunks={row['chunk_count']})",
                file=sys.stderr,
            )

    return ok_count == expected, report


def write_corpus_index_report(report: dict, *, settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    runs_dir = cfg.eval.resolve_runs_dir(cfg.repo_root)
    runs_dir.mkdir(parents=True, exist_ok=True)
    output_path = runs_dir / "corpus_index_report.json"
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return output_path


async def _main(allowlist_path: Path, *, write_report: bool) -> int:
    settings = get_settings()
    await init_db(settings)
    factory = get_session_factory()

    try:
        async with factory() as db:
            all_ok, report = await verify_corpus_index(db, allowlist_path=allowlist_path)
    finally:
        await close_db()

    if write_report:
        output_path = write_corpus_index_report(report, settings=settings)
        print(f"Report written to: {output_path}")

    return 0 if all_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify all MVP allowlist instruments are indexed with chunks > 0",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=_default_allowlist(),
        help="Path to mvp-corpus-allowlist.yaml",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write data/eval/runs/corpus_index_report.json",
    )
    args = parser.parse_args()

    if not args.allowlist.is_file():
        print(f"Error: allowlist not found: {args.allowlist}", file=sys.stderr)
        raise SystemExit(1)

    import asyncio

    raise SystemExit(asyncio.run(_main(args.allowlist, write_report=args.write_report)))


if __name__ == "__main__":
    main()
