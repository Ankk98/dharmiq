from __future__ import annotations

import json
from pathlib import Path

from pypdf import PdfWriter

from dharmiq.db.models.documents import DocType
from dharmiq.ingestion.scanner import compute_file_hash, scan_corpus_directory


def _write_sample_pdf(path: Path, pages: list[str]) -> None:
    writer = PdfWriter()
    for text in pages:
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)


def test_compute_file_hash_is_stable(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _write_sample_pdf(pdf_path, ["page one"])

    first = compute_file_hash(pdf_path)
    second = compute_file_hash(pdf_path)

    assert first == second
    assert len(first) == 64


def test_scan_corpus_directory_uses_manifest(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    pdf_path = corpus_dir / "constitution.pdf"
    _write_sample_pdf(pdf_path, ["Article 21"])

    manifest = [
        {
            "file": "constitution.pdf",
            "source_id": "IN-CONSTITUTION-1950",
            "title": "Constitution of India",
            "doc_type": "act",
            "jurisdiction": "central",
        }
    ]
    (corpus_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    scanned = scan_corpus_directory(corpus_dir)

    assert len(scanned) == 1
    doc = scanned[0]
    assert doc.source_id == "IN-CONSTITUTION-1950"
    assert doc.title == "Constitution of India"
    assert doc.doc_type == DocType.ACT
    assert doc.content_hash == compute_file_hash(pdf_path)


def test_scan_corpus_directory_infers_metadata_without_manifest(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    pdf_path = corpus_dir / "consumer_protection_act.pdf"
    _write_sample_pdf(pdf_path, ["Section 2"])

    scanned = scan_corpus_directory(corpus_dir)

    assert len(scanned) == 1
    assert scanned[0].source_id == "consumer_protection_act"
    assert scanned[0].doc_type == DocType.ACT
