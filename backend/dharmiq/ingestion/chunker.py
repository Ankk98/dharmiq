from __future__ import annotations

import re
from dataclasses import dataclass

from dharmiq.config.settings import Settings, get_settings
from dharmiq.ingestion.parser import PageText

SECTION_HEADING_RE = re.compile(
    r"^(?:"
    r"(?:CHAPTER|Chapter)\s+(?:[IVXLCDM]+|\d+)"
    r"|(?:Section|SECTION)\s+\d+[A-Za-z]?"
    r"|(?:Article|ARTICLE)\s+\d+"
    r"|\d+\.\s+[A-Z][^\n]{0,120}"
    r")",
    re.MULTILINE,
)


@dataclass(frozen=True)
class DetectedSection:
    label: str
    number: str | None
    start_page: int
    end_page: int
    text: str


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    section_label: str | None = None
    section_number: str | None = None


def _section_number_from_label(label: str) -> str | None:
    match = re.search(r"(?:Section|SECTION|Article|ARTICLE)\s+(\d+[A-Za-z]?)", label)
    if match:
        return match.group(1)
    chapter_match = re.search(r"(?:CHAPTER|Chapter)\s+([IVXLCDM]+|\d+)", label)
    if chapter_match:
        return chapter_match.group(1)
    numbered_match = re.match(r"(\d+)\.", label.strip())
    if numbered_match:
        return numbered_match.group(1)
    return None


def detect_sections(pages: list[PageText]) -> list[DetectedSection]:
    """Split page texts into statute-like sections using heading heuristics."""
    if not pages:
        return []

    full_text = "\n\n".join(page.text for page in pages if page.text.strip())
    if not full_text.strip():
        return []

    matches = list(SECTION_HEADING_RE.finditer(full_text))
    if not matches:
        return [
            DetectedSection(
                label="Document",
                number=None,
                start_page=pages[0].page_number,
                end_page=pages[-1].page_number,
                text=full_text.strip(),
            )
        ]

    sections: list[DetectedSection] = []
    page_starts = _page_start_offsets(pages)

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(full_text)
        section_text = full_text[start:end].strip()
        label = match.group(0).strip()
        start_page = _page_for_offset(start, page_starts)
        end_page = _page_for_offset(end - 1, page_starts)
        sections.append(
            DetectedSection(
                label=label,
                number=_section_number_from_label(label),
                start_page=start_page,
                end_page=end_page,
                text=section_text,
            )
        )

    return sections


def _page_start_offsets(pages: list[PageText]) -> list[tuple[int, int]]:
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for page in pages:
        offsets.append((cursor, page.page_number))
        cursor += len(page.text) + 2
    return offsets


def _page_for_offset(offset: int, page_starts: list[tuple[int, int]]) -> int:
    page_number = page_starts[-1][1] if page_starts else 1
    for start, number in page_starts:
        if offset >= start:
            page_number = number
    return page_number


def split_section_into_chunks(
    section: DetectedSection,
    *,
    min_chars: int | None = None,
    max_chars: int | None = None,
    overlap_chars: int | None = None,
    start_index: int = 0,
    settings: Settings | None = None,
) -> list[TextChunk]:
    cfg = settings or get_settings()
    min_size = min_chars if min_chars is not None else cfg.ingestion.chunk_min_chars
    max_size = max_chars if max_chars is not None else cfg.ingestion.chunk_max_chars
    overlap = overlap_chars if overlap_chars is not None else cfg.ingestion.chunk_overlap_chars

    text = section.text.strip()
    if not text:
        return []

    if len(text) <= max_size:
        return [
            TextChunk(
                chunk_index=start_index,
                text=text,
                page_start=section.start_page,
                page_end=section.end_page,
                section_label=section.label,
                section_number=section.number,
            )
        ]

    chunks: list[TextChunk] = []
    cursor = 0
    chunk_index = start_index

    while cursor < len(text):
        end = min(cursor + max_size, len(text))
        if end < len(text):
            split_at = text.rfind("\n\n", cursor + min_size, end)
            if split_at == -1:
                split_at = text.rfind(" ", cursor + min_size, end)
            if split_at > cursor:
                end = split_at

        chunk_text = text[cursor:end].strip()
        if chunk_text:
            chunks.append(
                TextChunk(
                    chunk_index=chunk_index,
                    text=chunk_text,
                    page_start=section.start_page,
                    page_end=section.end_page,
                    section_label=section.label,
                    section_number=section.number,
                )
            )
            chunk_index += 1

        if end >= len(text):
            break
        cursor = max(end - overlap, cursor + 1)

    return chunks


def chunk_document(
    pages: list[PageText],
    *,
    settings: Settings | None = None,
) -> list[TextChunk]:
    """Detect sections and split them into retrieval-sized chunks."""
    sections = detect_sections(pages)
    chunks: list[TextChunk] = []
    next_index = 0
    for section in sections:
        section_chunks = split_section_into_chunks(section, start_index=next_index, settings=settings)
        chunks.extend(section_chunks)
        next_index += len(section_chunks)
    return chunks
