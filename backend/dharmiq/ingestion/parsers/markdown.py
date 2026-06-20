from __future__ import annotations

import re
from pathlib import Path

from dharmiq.core.errors import IngestionError
from dharmiq.core.logging import get_logger
from dharmiq.ingestion.parser import PageText

logger = get_logger(__name__)

_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _split_markdown_sections(content: str) -> list[tuple[str, str]]:
    matches = list(_MARKDOWN_HEADING_RE.finditer(content))
    if not matches:
        stripped = content.strip()
        return [("Document", stripped)] if stripped else []

    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        preamble = content[: matches[0].start()].strip()
        if preamble:
            sections.append(("Preamble", preamble))

    for index, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[start:end].strip()
        sections.append((heading, body))

    return sections


def extract_markdown_pages(file_path: Path) -> list[PageText]:
    if not file_path.is_file():
        raise IngestionError("Markdown file not found", details={"path": str(file_path)})

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise IngestionError(
            "Markdown file is not valid UTF-8",
            details={"path": str(file_path), "error": str(exc)},
        ) from exc

    sections = _split_markdown_sections(content)
    if not sections:
        raise IngestionError("Markdown file contained no text", details={"path": str(file_path)})

    pages: list[PageText] = []
    for index, (heading, body) in enumerate(sections, start=1):
        section_text = f"{index}. {heading}\n\n{body}" if body else f"{index}. {heading}"
        pages.append(PageText(page_number=index, text=section_text))

    logger.info("markdown_extract_complete", path=str(file_path), section_count=len(pages))
    return pages
