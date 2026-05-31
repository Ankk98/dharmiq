"""Corpus ingestion pipeline – PDF scan, parse, chunk, embed, and index."""

from dharmiq.ingestion.chunker import chunk_document, detect_sections, split_section_into_chunks
from dharmiq.ingestion.parser import PageText, get_pdf_parser
from dharmiq.ingestion.pipeline import process_document, sync_corpus_documents
from dharmiq.ingestion.scanner import ScannedDocument, compute_file_hash, scan_corpus_directory

__all__ = [
    "PageText",
    "ScannedDocument",
    "chunk_document",
    "compute_file_hash",
    "detect_sections",
    "get_pdf_parser",
    "process_document",
    "scan_corpus_directory",
    "split_section_into_chunks",
    "sync_corpus_documents",
]
