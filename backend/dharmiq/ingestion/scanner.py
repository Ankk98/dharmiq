from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.logging import get_logger
from dharmiq.db.models.documents import DocType, InstrumentStatus

logger = get_logger(__name__)

MANIFEST_FILENAME = "manifest.json"
PDF_SUFFIX = ".pdf"

_MANIFEST_COLUMN_KEYS = frozenset(
    {
        "file",
        "filename",
        "source_id",
        "title",
        "doc_type",
        "jurisdiction",
        "enactment_date",
        "enforcement_date",
        "status",
        "superseded_by",
        "canonical_url",
    }
)


@dataclass(frozen=True)
class ScannedDocument:
    source_id: str
    title: str
    doc_type: DocType
    file_path: Path
    content_hash: str
    jurisdiction: str = "central"
    enactment_date: date | None = None
    enforcement_date: date | None = None
    status: InstrumentStatus = InstrumentStatus.IN_FORCE
    superseded_by_source_id: str | None = None
    canonical_url: str | None = None
    instrument_metadata: dict[str, Any] = field(default_factory=dict)


def compute_file_hash(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return date.fromisoformat(text[:10])


def _status_from_manifest(value: Any) -> InstrumentStatus:
    if not value:
        return InstrumentStatus.IN_FORCE
    try:
        return InstrumentStatus(str(value).lower())
    except ValueError:
        return InstrumentStatus.IN_FORCE


def _instrument_metadata_from_manifest(entry: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        key: value
        for key, value in entry.items()
        if key not in _MANIFEST_COLUMN_KEYS and value is not None
    }
    return metadata


def _infer_doc_type(source_id: str, title: str) -> DocType:
    haystack = f"{source_id} {title}".lower()
    if "act" in haystack:
        return DocType.ACT
    if "rule" in haystack:
        return DocType.RULE
    if "regulation" in haystack:
        return DocType.REGULATION
    if "notification" in haystack:
        return DocType.NOTIFICATION
    return DocType.OTHER


def _title_from_filename(path: Path) -> str:
    title = path.stem.replace("_", " ").replace("-", " ").strip()
    return title or path.name


def _load_manifest(corpus_dir: Path) -> dict[str, dict[str, Any]]:
    manifest_path = corpus_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return {}

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("manifest_parse_failed", path=str(manifest_path), error=str(exc))
        return {}

    entries: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            file_name = item.get("file") or item.get("filename")
            source_id = item.get("source_id")
            if not file_name or not source_id:
                continue
            entries[str(file_name)] = item
    elif isinstance(raw, dict):
        for file_name, item in raw.items():
            if isinstance(item, dict):
                entries[str(file_name)] = item
    return entries


def _doc_type_from_manifest(value: str | None) -> DocType:
    if not value:
        return DocType.OTHER
    try:
        return DocType(value.lower())
    except ValueError:
        return DocType.OTHER


def scan_corpus_directory(
    corpus_dir: Path | None = None,
    *,
    settings: Settings | None = None,
) -> list[ScannedDocument]:
    """Discover PDF files in the corpus directory and compute content hashes."""
    cfg = settings or get_settings()
    directory = corpus_dir or cfg.ingestion.resolve_corpus_dir(cfg.repo_root)
    if not directory.is_dir():
        logger.warning("corpus_dir_missing", path=str(directory))
        return []

    manifest = _load_manifest(directory)
    scanned: list[ScannedDocument] = []

    for path in sorted(directory.rglob(f"*{PDF_SUFFIX}")):
        if not path.is_file():
            continue

        relative_name = path.name
        manifest_entry = manifest.get(relative_name) or manifest.get(str(path.relative_to(directory)))

        source_id = str(manifest_entry.get("source_id")) if manifest_entry else path.stem
        title = str(manifest_entry.get("title")) if manifest_entry and manifest_entry.get("title") else _title_from_filename(path)
        doc_type = (
            _doc_type_from_manifest(manifest_entry.get("doc_type"))
            if manifest_entry
            else _infer_doc_type(source_id, title)
        )
        jurisdiction = str(manifest_entry.get("jurisdiction", "central")) if manifest_entry else "central"
        content_hash = compute_file_hash(path)

        enactment_date = (
            _parse_iso_date(manifest_entry.get("enactment_date")) if manifest_entry else None
        )
        enforcement_date = (
            _parse_iso_date(manifest_entry.get("enforcement_date")) if manifest_entry else None
        )
        status = (
            _status_from_manifest(manifest_entry.get("status")) if manifest_entry else InstrumentStatus.IN_FORCE
        )
        superseded_by = (
            str(manifest_entry["superseded_by"])
            if manifest_entry and manifest_entry.get("superseded_by")
            else None
        )
        canonical_url = (
            str(manifest_entry["canonical_url"])
            if manifest_entry and manifest_entry.get("canonical_url")
            else None
        )
        instrument_metadata = (
            _instrument_metadata_from_manifest(manifest_entry) if manifest_entry else {}
        )

        scanned.append(
            ScannedDocument(
                source_id=source_id,
                title=title,
                doc_type=doc_type,
                file_path=path.resolve(),
                content_hash=content_hash,
                jurisdiction=jurisdiction,
                enactment_date=enactment_date,
                enforcement_date=enforcement_date,
                status=status,
                superseded_by_source_id=superseded_by,
                canonical_url=canonical_url,
                instrument_metadata=instrument_metadata,
            )
        )

    logger.info("corpus_scan_complete", corpus_dir=str(directory), document_count=len(scanned))
    return scanned
