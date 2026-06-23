from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings, get_settings
from dharmiq.db.models.documents import DocumentChunk, SourceDocument
from dharmiq.db.session import close_db, get_session_factory, init_db
from dharmiq.eval.tools.allowlist import (
    load_allowlist,
    resolve_allowlist_cli_arg,
    source_id_to_filename,
)


def _default_allowlist(settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    return cfg.corpus.resolve_allowlist_path(cfg.repo_root)


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
    corpus_dir: Path | None = None,
    max_chunk_count: int | None = None,
) -> tuple[bool, dict]:
    """Return (all_ok, report_dict)."""
    instruments = load_allowlist(allowlist_path)
    expected_ids = [instrument.id for instrument in instruments]
    chunk_counts = await _chunk_counts_by_source_id(db)

    per_document: list[dict] = []
    missing: list[str] = []
    stale: list[str] = []
    missing_pdfs: list[str] = []

    for instrument in instruments:
        count = chunk_counts.get(instrument.id, 0)
        status = "ok"
        if instrument.id not in chunk_counts:
            status = "missing"
            missing.append(instrument.id)
        elif count <= 0:
            status = "no_chunks"
            stale.append(instrument.id)

        pdf_on_disk: bool | None = None
        if corpus_dir is not None:
            pdf_on_disk = (corpus_dir / source_id_to_filename(instrument.id)).is_file()
            if not pdf_on_disk:
                missing_pdfs.append(instrument.id)

        row = {
            "source_id": instrument.id,
            "title": instrument.title,
            "chunk_count": count,
            "status": status,
        }
        if pdf_on_disk is not None:
            row["pdf_on_disk"] = pdf_on_disk
        per_document.append(row)

    total_chunks = sum(chunk_counts.values())
    chunk_limit = max_chunk_count if max_chunk_count is not None else 250_000
    chunk_budget_ok = total_chunks <= chunk_limit

    indexed_ok = sum(1 for row in per_document if row["status"] == "ok") == len(expected_ids)
    pdfs_ok = len(missing_pdfs) == 0 if corpus_dir is not None else True
    all_ok = indexed_ok and chunk_budget_ok and pdfs_ok

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "allowlist_path": str(allowlist_path),
        "expected_document_count": len(expected_ids),
        "indexed_document_count": sum(1 for row in per_document if row["status"] == "ok"),
        "corpus_document_count": len(chunk_counts),
        "corpus_chunk_count": total_chunks,
        "max_chunk_count": chunk_limit,
        "chunk_budget_ok": chunk_budget_ok,
        "missing_source_ids": missing,
        "stale_source_ids": stale,
        "missing_pdf_source_ids": missing_pdfs,
        "documents": per_document,
    }
    if corpus_dir is not None:
        report["corpus_dir"] = str(corpus_dir)

    ok_count = report["indexed_document_count"]
    expected = report["expected_document_count"]
    print(f"Indexed: {ok_count}/{expected}")
    print(f"Chunks: {total_chunks} (budget {chunk_limit}, ok={chunk_budget_ok})")
    if corpus_dir is not None:
        pdf_ok = expected - len(missing_pdfs)
        print(f"PDFs on disk: {pdf_ok}/{expected}")

    for row in per_document:
        if row["status"] != "ok":
            print(
                f"  FAIL {row['source_id']}: {row['status']} (chunks={row['chunk_count']})",
                file=sys.stderr,
            )
        elif corpus_dir is not None and not row.get("pdf_on_disk", True):
            print(
                f"  FAIL {row['source_id']}: missing_pdf (chunks={row['chunk_count']})",
                file=sys.stderr,
            )

    if not chunk_budget_ok:
        print(
            f"  FAIL chunk budget exceeded: {total_chunks} > {chunk_limit}",
            file=sys.stderr,
        )

    return all_ok, report


def write_corpus_index_report(report: dict, *, settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    runs_dir = cfg.eval.resolve_runs_dir(cfg.repo_root)
    runs_dir.mkdir(parents=True, exist_ok=True)
    output_path = runs_dir / "corpus_index_report.json"
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return output_path


async def _main(
    allowlist_path: Path,
    *,
    corpus_dir: Path | None,
    max_chunk_count: int,
    write_report: bool,
) -> int:
    settings = get_settings()
    await init_db(settings)
    factory = get_session_factory()

    try:
        async with factory() as db:
            all_ok, report = await verify_corpus_index(
                db,
                allowlist_path=allowlist_path,
                corpus_dir=corpus_dir,
                max_chunk_count=max_chunk_count,
            )
    finally:
        await close_db()

    if write_report:
        output_path = write_corpus_index_report(report, settings=settings)
        print(f"Report written to: {output_path}")

    return 0 if all_ok else 1


def main() -> None:
    settings = get_settings()
    default_corpus_dir = settings.ingestion.resolve_corpus_dir(settings.repo_root)

    parser = argparse.ArgumentParser(
        description="Verify allowlist instruments are indexed with chunks > 0",
    )
    parser.add_argument(
        "--allowlist",
        default="central",
        help="Path to allowlist YAML or alias 'central' (v0.6 central corpus)",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=default_corpus_dir,
        help="Corpus directory; when set, also verify PDFs exist on disk",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=settings.corpus.max_chunk_count,
        help="Fail when corpus_chunk_count exceeds this limit (TRD-93)",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write data/eval/runs/corpus_index_report.json",
    )
    args = parser.parse_args()

    allowlist_path = resolve_allowlist_cli_arg(
        args.allowlist,
        repo_root=settings.repo_root,
        default_allowlist_path=settings.corpus.default_allowlist_path,
    )
    if not allowlist_path.is_file():
        print(f"Error: allowlist not found: {allowlist_path}", file=sys.stderr)
        raise SystemExit(1)

    import asyncio

    raise SystemExit(
        asyncio.run(
            _main(
                allowlist_path,
                corpus_dir=args.corpus_dir,
                max_chunk_count=args.max_chunks,
                write_report=args.write_report,
            )
        )
    )


if __name__ == "__main__":
    main()
