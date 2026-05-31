from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import IngestionError
from dharmiq.core.logging import get_logger
from dharmiq.ingestion.ocr import OcrBackend, get_ocr_backend

logger = get_logger(__name__)


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str
    used_ocr: bool = False


class PdfParserBackend(ABC):
    @abstractmethod
    def extract_pages(self, file_path: Path) -> list[PageText]:
        raise NotImplementedError


class HybridPdfParser(PdfParserBackend):
    """Extract text with pypdf, fall back to pdfplumber and OCR for sparse pages."""

    def __init__(
        self,
        settings: Settings | None = None,
        ocr_backend: OcrBackend | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._ocr = ocr_backend or get_ocr_backend(self._settings)
        self._min_chars = self._settings.ingestion.min_page_text_chars

    def extract_pages(self, file_path: Path) -> list[PageText]:
        if not file_path.is_file():
            raise IngestionError("PDF file not found", details={"path": str(file_path)})

        pages: list[PageText] = []
        try:
            reader = PdfReader(str(file_path))
        except Exception as exc:
            raise IngestionError("Failed to open PDF", details={"path": str(file_path), "error": str(exc)}) from exc

        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            used_ocr = False

            if len(text) < self._min_chars:
                text, used_ocr = self._extract_with_pdfplumber(file_path, index, text)

            pages.append(PageText(page_number=index, text=text, used_ocr=used_ocr))

        logger.info(
            "pdf_extract_complete",
            path=str(file_path),
            page_count=len(pages),
            ocr_pages=sum(1 for page in pages if page.used_ocr),
        )
        return pages

    def _extract_with_pdfplumber(
        self,
        file_path: Path,
        page_number: int,
        existing_text: str,
    ) -> tuple[str, bool]:
        import pdfplumber

        try:
            with pdfplumber.open(str(file_path)) as pdf:
                if page_number > len(pdf.pages):
                    return existing_text, False
                page = pdf.pages[page_number - 1]
                text = (page.extract_text() or existing_text or "").strip()
                if len(text) >= self._min_chars:
                    return text, False

                image = page.to_image(resolution=300)
                ocr_text = self._ocr.extract_text_from_image(image.original).strip()
                if ocr_text:
                    return ocr_text, True
                return text, False
        except Exception as exc:
            logger.warning(
                "pdfplumber_page_failed",
                path=str(file_path),
                page=page_number,
                error=str(exc),
            )
            return existing_text, False


def get_pdf_parser(settings: Settings | None = None) -> PdfParserBackend:
    return HybridPdfParser(settings=settings)


def extract_image_pages(
    file_path: Path,
    *,
    settings: Settings | None = None,
    ocr_backend: OcrBackend | None = None,
) -> list[PageText]:
    """OCR a single image file into one page of text."""
    from PIL import Image

    if not file_path.is_file():
        raise IngestionError("Image file not found", details={"path": str(file_path)})

    ocr = ocr_backend or get_ocr_backend(settings)
    try:
        with Image.open(file_path) as image:
            text = ocr.extract_text_from_image(image).strip()
    except Exception as exc:
        raise IngestionError(
            "Failed to read image",
            details={"path": str(file_path), "error": str(exc)},
        ) from exc

    return [PageText(page_number=1, text=text, used_ocr=True)]
