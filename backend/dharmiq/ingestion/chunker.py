from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from dharmiq.config.settings import Settings, get_settings
from dharmiq.ingestion.context_text import build_context_text
from dharmiq.ingestion.parser import PageText
from dharmiq.ingestion.tokens import count_tokens

# Token counts use the local MiniLM tokenizer (sentence-transformers/all-MiniLM-L6-v2),
# matching the fixed 384-dim embedding model (R4-2). child_chunk_target_tokens counts
# tokens via encode(..., add_special_tokens=False), not characters.
CHUNK_SCHEMA_V02 = "v02"

SECTION_HEADING_RE = re.compile(
    r"^(?:"
    r"(?:CHAPTER|Chapter)\s+(?:[IVXLCDM]+|\d+)"
    r"|(?:Section|SECTION)\s+\d+[A-Za-z]?"
    r"|(?:Article|ARTICLE)\s+\d+"
    r"|\d+\.\s+[A-Z][^\n]{0,120}"
    r")",
    re.MULTILINE,
)

ChunkType = Literal["parent", "child"]


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
    context_text: str | None = None
    chunk_type: ChunkType = "child"
    chunk_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SectionChunkGroup:
    parent: TextChunk
    children: list[TextChunk]


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


def _split_parent_text(section: DetectedSection, *, max_tokens: int, overlap_tokens: int) -> list[str]:
    text = section.text.strip()
    if count_tokens(text) <= max_tokens:
        return [text]

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        paragraphs = [text]

    parts: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for paragraph in paragraphs:
        paragraph_tokens = count_tokens(paragraph)
        if paragraph_tokens > max_tokens:
            if current:
                parts.append("\n\n".join(current))
                current = []
                current_tokens = 0
            cursor = 0
            words = paragraph.split()
            while cursor < len(words):
                chunk_words: list[str] = []
                while cursor < len(words):
                    candidate = words[cursor]
                    next_tokens = count_tokens(candidate if not chunk_words else " ".join([*chunk_words, candidate]))
                    if chunk_words and next_tokens > max_tokens:
                        break
                    chunk_words.append(candidate)
                    cursor += 1
                    if count_tokens(" ".join(chunk_words)) >= max_tokens:
                        break
                if chunk_words:
                    parts.append(" ".join(chunk_words))
            continue

        projected = current_tokens + paragraph_tokens + (2 if current else 0)
        if current and projected > max_tokens:
            parts.append("\n\n".join(current))
            overlap: list[str] = []
            overlap_count = 0
            for item in reversed(current):
                item_tokens = count_tokens(item)
                if overlap_count + item_tokens > overlap_tokens and overlap:
                    break
                overlap.insert(0, item)
                overlap_count += item_tokens
            current = overlap.copy()
            current_tokens = count_tokens("\n\n".join(current)) if current else 0

        current.append(paragraph)
        current_tokens = count_tokens("\n\n".join(current))

    if current:
        parts.append("\n\n".join(current))

    return parts or [text]


def _split_section_into_children(
    section: DetectedSection,
    *,
    target_tokens: int,
    overlap_tokens: int,
    start_index: int,
    settings: Settings | None = None,
) -> list[TextChunk]:
    cfg = settings or get_settings()
    text = section.text.strip()
    if not text:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[TextChunk] = []
    current: list[str] = []
    current_tokens = 0
    chunk_index = start_index

    def flush() -> None:
        nonlocal chunk_index, current, current_tokens
        if not current:
            return
        chunk_text = "\n\n".join(current).strip()
        chunks.append(
            TextChunk(
                chunk_index=chunk_index,
                text=chunk_text,
                page_start=section.start_page,
                page_end=section.end_page,
                section_label=section.label,
                section_number=section.number,
                context_text=build_context_text(
                    chunk_text,
                    section_label=section.label,
                    settings=cfg,
                ),
                chunk_type="child",
                chunk_metadata={
                    "schema_version": CHUNK_SCHEMA_V02,
                    "chunk_type": "child",
                    "section_label": section.label,
                    "section_number": section.number,
                },
            )
        )
        chunk_index += 1
        overlap: list[str] = []
        overlap_count = 0
        for item in reversed(current):
            item_tokens = count_tokens(item)
            if overlap_count + item_tokens > overlap_tokens and overlap:
                break
            overlap.insert(0, item)
            overlap_count += item_tokens
        current = overlap.copy()
        current_tokens = count_tokens("\n\n".join(current)) if current else 0

    for paragraph in paragraphs:
        paragraph_tokens = count_tokens(paragraph)
        if paragraph_tokens > target_tokens * 2:
            if current:
                flush()
            words = paragraph.split()
            cursor = 0
            while cursor < len(words):
                chunk_words: list[str] = []
                while cursor < len(words):
                    candidate = words[cursor]
                    next_text = candidate if not chunk_words else " ".join([*chunk_words, candidate])
                    if chunk_words and count_tokens(next_text) > target_tokens:
                        break
                    chunk_words.append(candidate)
                    cursor += 1
                    if count_tokens(" ".join(chunk_words)) >= target_tokens:
                        break
                if chunk_words:
                    chunk_text = " ".join(chunk_words)
                    chunks.append(
                        TextChunk(
                            chunk_index=chunk_index,
                            text=chunk_text,
                            page_start=section.start_page,
                            page_end=section.end_page,
                            section_label=section.label,
                            section_number=section.number,
                            context_text=build_context_text(
                                chunk_text,
                                section_label=section.label,
                                settings=cfg,
                            ),
                            chunk_type="child",
                            chunk_metadata={
                                "schema_version": CHUNK_SCHEMA_V02,
                                "chunk_type": "child",
                                "section_label": section.label,
                                "section_number": section.number,
                            },
                        )
                    )
                    chunk_index += 1
            continue

        projected = current_tokens + paragraph_tokens + (2 if current else 0)
        if current and projected > target_tokens:
            flush()

        current.append(paragraph)
        current_tokens = count_tokens("\n\n".join(current))

    if current:
        flush()

    if not chunks:
        chunks.append(
            TextChunk(
                chunk_index=start_index,
                text=text,
                page_start=section.start_page,
                page_end=section.end_page,
                section_label=section.label,
                section_number=section.number,
                context_text=build_context_text(text, section_label=section.label, settings=cfg),
                chunk_type="child",
                chunk_metadata={
                    "schema_version": CHUNK_SCHEMA_V02,
                    "chunk_type": "child",
                    "section_label": section.label,
                    "section_number": section.number,
                },
            )
        )

    return chunks


def chunk_section(
    section: DetectedSection,
    *,
    start_index: int = 0,
    settings: Settings | None = None,
) -> SectionChunkGroup:
    """Create one parent chunk and token-sized child chunks for a detected section."""
    cfg = settings or get_settings()
    parent_text = section.text.strip()

    parent = TextChunk(
        chunk_index=start_index,
        text=parent_text,
        page_start=section.start_page,
        page_end=section.end_page,
        section_label=section.label,
        section_number=section.number,
        context_text=build_context_text(parent_text, section_label=section.label, settings=cfg),
        chunk_type="parent",
        chunk_metadata={
            "schema_version": CHUNK_SCHEMA_V02,
            "chunk_type": "parent",
            "section_label": section.label,
            "section_number": section.number,
        },
    )
    children = _split_section_into_children(
        section,
        target_tokens=cfg.ingestion.child_chunk_target_tokens,
        overlap_tokens=cfg.ingestion.overlap_tokens,
        start_index=start_index + 1,
        settings=cfg,
    )
    return SectionChunkGroup(parent=parent, children=children)


def chunk_document(
    pages: list[PageText],
    *,
    settings: Settings | None = None,
) -> list[SectionChunkGroup]:
    """Detect sections and emit parent/child chunk groups for v0.2 ingestion."""
    sections = detect_sections(pages)
    groups: list[SectionChunkGroup] = []
    next_index = 0
    for section in sections:
        group = chunk_section(section, start_index=next_index, settings=settings)
        groups.append(group)
        next_index += 1 + len(group.children)
    return groups


def flatten_chunk_groups(groups: list[SectionChunkGroup]) -> list[TextChunk]:
    """Flatten parent/child groups into persistence order (parent before its children)."""
    ordered: list[TextChunk] = []
    for group in groups:
        ordered.append(group.parent)
        ordered.extend(group.children)
    return ordered


# Legacy char-based splitter retained for tests that pin explicit char limits.
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
