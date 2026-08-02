"""Text parser for normalising raw PDF-extracted content.

Applies light cleaning and normalisation so downstream chunking produces
consistent results regardless of PDF source quality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedPage:
    """Cleaned page text ready for chunking."""

    text: str
    page_number: int  # 1-indexed


@dataclass(frozen=True)
class ParsedDocument:
    """Fully parsed document with cleaned pages."""

    filename: str
    page_count: int
    pages: tuple[ParsedPage, ...]


class TextParser:
    """Normalise and clean raw PDF text.

    The parser applies a configurable set of cleaning rules:

    - Collapses multiple blank lines into a single newline.
    - Strips leading/trailing whitespace per page.
    - Optionally removes page headers/footers via regex.
    - Normalises unicode whitespace characters.
    """

    #: Regex patterns for common page-number-only lines to strip.
    DEFAULT_HEADER_FOOTER_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"^\s*\d+\s*$"),  # standalone page number
    )

    def __init__(
        self,
        *,
        strip_header_footer: bool = True,
        min_text_length: int = 10,
    ) -> None:
        """Create the parser.

        :param strip_header_footer: When True, lines matching known header/
            footer patterns are removed from the start/end of each page.
        :param min_text_length: Pages with fewer characters are not discarded
            but are passed through as-is (preserves mostly-image pages).
        """
        self._strip_header_footer = strip_header_footer
        self._min_text_length = min_text_length

    def parse(self, raw_pages: tuple[object, ...], *, filename: str) -> ParsedDocument:
        """Parse a tuple of raw page objects into cleaned pages.

        :param raw_pages: Tuple of objects with ``.text`` and ``.page_number``
            attributes (e.g. :class:`~app.rag.loader.PdfPage`).
        :param filename: Source filename for metadata.
        :returns: A :class:`ParsedDocument` with cleaned text.
        """
        parsed: list[ParsedPage] = []

        for raw in raw_pages:
            text = raw.text  # type: ignore[union-attr]
            text = self._normalise_whitespace(text)
            if self._strip_header_footer:
                text = self._remove_header_footer(text)
            parsed.append(
                ParsedPage(text=text, page_number=raw.page_number)  # type: ignore[union-attr]
            )

        return ParsedDocument(
            filename=filename,
            page_count=len(parsed),
            pages=tuple(parsed),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_whitespace(text: str) -> str:
        """Collapse excessive blank lines and normalise unicode whitespace."""
        # Replace non-standard whitespace chars with standard space.
        text = re.sub(r"[\u00a0\u2000-\u200a\u202f\u205f]", " ", text)
        # Collapse three or more newlines into two (paragraph break).
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _remove_header_footer(self, text: str) -> str:
        """Strip lines that look like page headers or footers."""
        lines = text.splitlines()
        # Remove matching lines from the top.
        while lines and any(p.match(lines[0]) for p in self.DEFAULT_HEADER_FOOTER_PATTERNS):
            lines.pop(0)
        # Remove matching lines from the bottom.
        while lines and any(p.match(lines[-1]) for p in self.DEFAULT_HEADER_FOOTER_PATTERNS):
            lines.pop()
        return "\n".join(lines).strip()


__all__ = [
    "ParsedDocument",
    "ParsedPage",
    "TextParser",
]
