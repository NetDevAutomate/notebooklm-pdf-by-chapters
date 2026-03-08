"""Integration tests — full PDF split roundtrip with real PyMuPDF."""

import pymupdf
import pytest

from pdf_by_chapters.splitter import split_pdf_by_chapters

pytestmark = pytest.mark.integration


class TestSplitRoundtrip:
    """End-to-end split and validate chapter content."""

    def test_chapter_text_preserved(self, sample_pdf, output_dir):
        """Text from each page should survive the split."""
        results = split_pdf_by_chapters(sample_pdf, output_dir, "book", level=1)
        doc = pymupdf.open(results[0])
        text = doc[0].get_text()
        assert "Page 1 content" in text
        doc.close()

    def test_all_pages_accounted_for(self, sample_pdf, output_dir):
        """Sum of chapter pages should equal original page count."""
        original = pymupdf.open(sample_pdf)
        total = original.page_count
        original.close()

        results = split_pdf_by_chapters(sample_pdf, output_dir, "book", level=1)
        split_total = 0
        for path in results:
            doc = pymupdf.open(path)
            split_total += doc.page_count
            doc.close()
        assert split_total == total

    def test_level2_split_covers_all_pages(self, sample_pdf, output_dir):
        """Level-2 split should also cover all pages."""
        original = pymupdf.open(sample_pdf)
        total = original.page_count
        original.close()

        results = split_pdf_by_chapters(sample_pdf, output_dir, "book", level=2)
        split_total = 0
        for path in results:
            doc = pymupdf.open(path)
            split_total += doc.page_count
            doc.close()
        assert split_total == total

    def test_chapter_toc_page_numbers_valid(self, sample_pdf, output_dir):
        """Rebuilt TOC page numbers should be within chapter page range."""
        results = split_pdf_by_chapters(sample_pdf, output_dir, "book", level=1)
        for path in results:
            doc = pymupdf.open(path)
            toc = doc.get_toc()
            for _level, _title, page in toc:
                assert 1 <= page <= doc.page_count
            doc.close()
