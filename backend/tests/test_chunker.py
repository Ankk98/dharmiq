from __future__ import annotations

from dharmiq.ingestion.chunker import (
    chunk_document,
    detect_sections,
    split_section_into_chunks,
)
from dharmiq.ingestion.chunker import DetectedSection
from dharmiq.ingestion.parser import PageText


def test_detect_sections_finds_statute_headings() -> None:
    pages = [
        PageText(
            page_number=1,
            text=(
                "Section 1. Short title.\n"
                "This Act may be called the Test Act.\n\n"
                "Section 2. Definitions.\n"
                "In this Act, unless the context otherwise requires."
            ),
        )
    ]

    sections = detect_sections(pages)

    assert len(sections) == 2
    assert sections[0].label.startswith("Section 1")
    assert sections[0].number == "1"
    assert sections[1].label.startswith("Section 2")
    assert sections[1].number == "2"


def test_split_section_into_chunks_respects_max_size() -> None:
    section = DetectedSection(
        label="Section 10. Long section",
        number="10",
        start_page=1,
        end_page=2,
        text="word " * 1200,
    )

    chunks = split_section_into_chunks(
        section,
        min_chars=200,
        max_chars=500,
        overlap_chars=50,
        start_index=0,
    )

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 500 for chunk in chunks)
    assert chunks[0].section_number == "10"


def test_chunk_document_assigns_incrementing_indexes() -> None:
    pages = [
        PageText(
            page_number=1,
            text="Section 1. Intro.\nIntro text.\n\nSection 2. Details.\nMore text here.",
        )
    ]

    chunks = chunk_document(pages)

    assert len(chunks) >= 2
    indexes = [chunk.chunk_index for chunk in chunks]
    assert indexes == list(range(len(chunks)))
