from __future__ import annotations

from pathlib import Path

from docx import Document

from dharmiq.core.errors import IngestionError
from dharmiq.core.logging import get_logger
from dharmiq.ingestion.parser import PageText

logger = get_logger(__name__)

_HEADING_STYLE_PREFIX = "heading"


def _is_heading(paragraph) -> bool:
    style_name = (paragraph.style.name or "").lower() if paragraph.style else ""
    return style_name.startswith(_HEADING_STYLE_PREFIX)


def extract_docx_pages(file_path: Path) -> list[PageText]:
    if not file_path.is_file():
        raise IngestionError("DOCX file not found", details={"path": str(file_path)})

    try:
        document = Document(str(file_path))
    except Exception as exc:
        raise IngestionError(
            "Failed to open DOCX",
            details={"path": str(file_path), "error": str(exc)},
        ) from exc

    sections: list[tuple[str, list[str]]] = []
    current_heading = "Document"
    current_paragraphs: list[str] = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if _is_heading(paragraph):
            if current_paragraphs or current_heading != "Document" or sections:
                sections.append((current_heading, current_paragraphs))
            current_heading = text
            current_paragraphs = []
        else:
            current_paragraphs.append(text)

    if current_paragraphs or not sections:
        sections.append((current_heading, current_paragraphs))

    pages: list[PageText] = []
    for index, (heading, paragraphs) in enumerate(sections, start=1):
        body = "\n\n".join(paragraphs).strip()
        section_text = f"{index}. {heading}\n\n{body}" if body else f"{index}. {heading}"
        pages.append(PageText(page_number=index, text=section_text))

    if not pages:
        raise IngestionError("DOCX contained no extractable text", details={"path": str(file_path)})

    logger.info("docx_extract_complete", path=str(file_path), section_count=len(pages))
    return pages
