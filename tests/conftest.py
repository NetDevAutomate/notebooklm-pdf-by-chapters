"""Shared test fixtures."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pymupdf
import pytest


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a minimal PDF with a 3-level TOC for testing."""
    doc = pymupdf.open()
    for i in range(10):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1} content")

    toc = [
        [1, "Chapter 1: Introduction", 1],
        [2, "1.1 Background", 1],
        [2, "1.2 Overview", 2],
        [1, "Chapter 2: Core Concepts", 4],
        [2, "2.1 Fundamentals", 4],
        [2, "2.2 Advanced Topics", 6],
        [1, "Chapter 3: Conclusion", 8],
        [2, "3.1 Summary", 8],
        [2, "3.2 Next Steps", 9],
    ]
    doc.set_toc(toc)

    pdf_path = tmp_path / "test_book.pdf"
    doc.ez_save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def sample_pdf_no_toc(tmp_path: Path) -> Path:
    """Create a PDF with no TOC/bookmarks."""
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1}")
    pdf_path = tmp_path / "no_toc.pdf"
    doc.ez_save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Provide a clean output directory."""
    out = tmp_path / "output"
    out.mkdir()
    return out


@pytest.fixture
def mock_notebooklm_client():
    """Mock NotebookLMClient for testing without real API calls."""
    client = AsyncMock()

    mock_notebook = MagicMock()
    mock_notebook.id = "test-notebook-id"
    mock_notebook.title = "Test Book"
    client.notebooks.list.return_value = [mock_notebook]
    client.notebooks.create.return_value = mock_notebook
    client.notebooks.delete.return_value = None

    mock_source = MagicMock()
    mock_source.id = "test-source-id"
    mock_source.title = "chapter_01"
    client.sources.list.return_value = [mock_source]
    client.sources.add_file.return_value = mock_source

    mock_status = MagicMock()
    mock_status.task_id = "test-task-id"
    mock_status.is_complete = True
    mock_status.is_failed = False
    client.artifacts.generate_audio.return_value = mock_status
    client.artifacts.generate_video.return_value = mock_status
    client.artifacts.poll_status.return_value = mock_status

    mock_audio = MagicMock()
    mock_audio.id = "audio-artifact-id"
    client.artifacts.list_audio.return_value = [mock_audio]

    mock_video = MagicMock()
    mock_video.id = "video-artifact-id"
    client.artifacts.list_video.return_value = [mock_video]

    client.artifacts.download_audio.return_value = None
    client.artifacts.download_video.return_value = None
    client.artifacts.rename.return_value = None

    mock_ask_result = MagicMock()
    mock_ask_result.answer = 'Episode 1: "Test Episode"\nChapters: 1\nSummary: Test.'
    mock_ask_result.conversation_id = "test-conv-id"
    client.chat.ask.return_value = mock_ask_result

    return client


@pytest.fixture
def patch_notebooklm(mock_notebooklm_client):
    """Patch NotebookLMClient.from_storage to return mock client.

    The real client uses `async with await Client.from_storage() as client:`
    so we need to mock both the await and the async context manager.
    """
    acm = AsyncMock()
    acm.__aenter__.return_value = mock_notebooklm_client
    acm.__aexit__.return_value = None

    with patch(
        "pdf_by_chapters.notebooklm.NotebookLMClient.from_storage",
        return_value=acm,
    ) as mock_from_storage:
        yield mock_notebooklm_client, mock_from_storage
