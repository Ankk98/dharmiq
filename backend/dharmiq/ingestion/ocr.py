from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import IngestionError
from dharmiq.core.logging import get_logger

if TYPE_CHECKING:
    from PIL import Image

logger = get_logger(__name__)


class OcrBackend(ABC):
    @abstractmethod
    def extract_text_from_image(self, image: Image.Image) -> str:
        raise NotImplementedError


class PytesseractOcrBackend(OcrBackend):
    """OCR via system Tesseract (English by default; Hindi packs optional)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._languages = (settings or get_settings()).ingestion.ocr_languages

    def extract_text_from_image(self, image: Image.Image) -> str:
        try:
            import pytesseract
        except ImportError as exc:
            raise IngestionError("pytesseract is not installed", details={"error": str(exc)}) from exc

        try:
            return pytesseract.image_to_string(image, lang=self._languages)
        except pytesseract.TesseractNotFoundError as exc:
            raise IngestionError(
                "Tesseract binary not found; install tesseract-ocr system package",
                details={"languages": self._languages},
            ) from exc
        except Exception as exc:
            logger.warning("ocr_failed", error=str(exc))
            return ""


def get_ocr_backend(settings: Settings | None = None) -> OcrBackend:
    return PytesseractOcrBackend(settings=settings)
