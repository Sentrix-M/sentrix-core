"""PDF document loader using PyMuPDF (fitz).

Extracts text content and metadata from uploaded PDF files. The loader
operates on raw bytes so it can be used directly from a FastAPI
``UploadFile`` without writing to disk.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class PdfLoadError(Exception):
    """Raised when a PDF cannot be loaded or parsed."""


@dataclass(frozen=True)
class PdfPage:
    """Text and metadata for a single PDF page."""

    text: str
    page_number: int  # 1-indexed


@dataclass(frozen=True)
class PdfDocument:
    """Fully loaded PDF document with all pages."""

    filename: str
    page_count: int
    pages: tuple[PdfPage, ...] = field(default_factory=tuple)


class PdfLoader:
    """Load and extract text from PDF byte content using PyMuPDF.

    Usage::

        loader = PdfLoader()
        doc = loader.load(pdf_bytes, filename="report.pdf")
        for page in doc.pages:
            print(page.text)
    """

    #: Characters below this threshold cause a page to be considered empty.
    MIN_PAGE_TEXT_LENGTH = 10

    def load(self, content: bytes, *, filename: str = "document.pdf") -> PdfDocument:
        """Load a PDF from raw bytes and extract all page text.

        :param content: Raw PDF file bytes.
        :param filename: Original filename (for logging / metadata).
        :returns: A :class:`PdfDocument` with extracted pages.
        :raises PdfLoadError: If PyMuPDF cannot open or parse the content.
        """
        try:
            import fitz  # PyMuPDF  # noqa: PLC0415 - lazy import
        except ImportError as exc:
            raise PdfLoadError(
                "PyMuPDF (fitz) is required. Install it with: pip install PyMuPDF"
            ) from exc

        try:
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:
            logger.exception("Failed to open PDF stream.")
            raise PdfLoadError(f"Cannot open PDF: {exc}") from exc

        pages: list[PdfPage] = []
        page_count = doc.page_count

        for page_num in range(page_count):
            try:
                page = doc[page_num]
                text = page.get_text().strip()
            except Exception as exc:
                logger.warning("Failed to extract text from page %d: %s", page_num + 1, exc)
                text = ""

            if len(text) < self.MIN_PAGE_TEXT_LENGTH:
                logger.debug(
                    "Page %d of '%s' has very little text (%d chars); "
                    "including as-is.",
                    page_num + 1,
                    filename,
                    len(text),
                )

            pages.append(PdfPage(text=text, page_number=page_num + 1))

        doc.close()

        return PdfDocument(
            filename=filename,
            page_count=page_count,
            pages=tuple(pages),
        )


__all__ = [
    "PdfDocument",
    "PdfLoadError",
    "PdfLoader",
    "PdfPage",
]
