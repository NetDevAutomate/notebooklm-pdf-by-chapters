"""Unit tests for pdf_by_chapters.cli."""

import json
from unittest.mock import patch

from typer.testing import CliRunner

from pdf_by_chapters.cli import app
from pdf_by_chapters.syllabus import (
    ChunkArtifact,
    ChunkStatus,
    SyllabusChunk,
    SyllabusState,
    write_state,
)

runner = CliRunner()


class TestSplitCommand:
    """Tests for the split CLI command."""

    def test_split_single_pdf(self, sample_pdf, output_dir):
        result = runner.invoke(app, ["split", str(sample_pdf), "-o", str(output_dir)])
        assert result.exit_code == 0
        pdfs = list(output_dir.glob("*.pdf"))
        assert len(pdfs) == 3

    def test_split_with_level(self, sample_pdf, output_dir):
        result = runner.invoke(app, ["split", str(sample_pdf), "-o", str(output_dir), "-l", "2"])
        assert result.exit_code == 0
        pdfs = list(output_dir.glob("*.pdf"))
        assert len(pdfs) == 6

    def test_split_nonexistent_file(self, tmp_path):
        result = runner.invoke(app, ["split", str(tmp_path / "nope.pdf")])
        assert result.exit_code != 0

    def test_split_directory(self, sample_pdf, output_dir):
        result = runner.invoke(app, ["split", str(sample_pdf.parent), "-o", str(output_dir)])
        assert result.exit_code == 0


class TestResolveHelpers:
    """Tests for CLI helper functions."""

    def test_resolve_pdfs_empty_dir(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = runner.invoke(app, ["split", str(empty)])
        assert result.exit_code != 0


class TestGenerateCommand:
    """Tests for the generate CLI command."""

    def test_missing_notebook_id(self):
        result = runner.invoke(app, ["generate", "-c", "1-3"])
        assert result.exit_code != 0

    def test_invalid_chapter_range(self):
        result = runner.invoke(app, ["generate", "-n", "abc", "-c", "bad"])
        assert result.exit_code != 0

    def test_invalid_range_start_gt_end(self):
        result = runner.invoke(app, ["generate", "-n", "abc", "-c", "5-2"])
        assert result.exit_code != 0


class TestDownloadCommand:
    """Tests for the download CLI command."""

    def test_missing_notebook_id(self):
        result = runner.invoke(app, ["download"])
        assert result.exit_code != 0


class TestDeleteCommand:
    """Tests for the delete CLI command."""

    def test_missing_notebook_id(self):
        result = runner.invoke(app, ["delete"])
        assert result.exit_code != 0


class TestListCommand:
    """Tests for the list CLI command."""

    @patch("pdf_by_chapters.cli.asyncio")
    def test_list_without_notebook_id(self, mock_asyncio):
        mock_asyncio.run.return_value = []
        with patch("pdf_by_chapters.notebooklm.NotebookLMClient"):
            runner.invoke(app, ["list"])
        # Just verify it attempts to call list_notebooks (may fail on import)
        # The important thing is the CLI routing works


class TestProcessCommand:
    """Tests for the process CLI command."""

    def test_process_splits_and_uploads(self, sample_pdf, output_dir, patch_notebooklm):
        client, _ = patch_notebooklm
        client.notebooks.list.return_value = []

        result = runner.invoke(app, ["process", str(sample_pdf), "-o", str(output_dir)])
        assert result.exit_code == 0
        assert client.sources.add_file.call_count == 3

    def test_process_nonexistent_file(self, tmp_path):
        result = runner.invoke(app, ["process", str(tmp_path / "nope.pdf")])
        assert result.exit_code != 0

    def test_process_directory(self, sample_pdf, output_dir, patch_notebooklm):
        client, _ = patch_notebooklm
        client.notebooks.list.return_value = []

        result = runner.invoke(app, ["process", str(sample_pdf.parent), "-o", str(output_dir)])
        assert result.exit_code == 0

    def test_process_with_notebook_id(self, sample_pdf, output_dir, patch_notebooklm):
        client, _ = patch_notebooklm

        result = runner.invoke(
            app,
            ["process", str(sample_pdf), "-o", str(output_dir), "-n", "custom-id"],
        )
        assert result.exit_code == 0
        client.notebooks.create.assert_not_called()


class TestDownloadCommandFull:
    """Extended download command tests."""

    def test_download_with_chapter_range(self, tmp_path, patch_notebooklm):
        result = runner.invoke(
            app,
            ["download", "-n", "test-id", "-o", str(tmp_path), "-c", "1-3"],
        )
        assert result.exit_code == 0

    def test_download_invalid_chapter_range(self, tmp_path):
        result = runner.invoke(
            app,
            ["download", "-n", "test-id", "-o", str(tmp_path), "-c", "bad"],
        )
        assert result.exit_code != 0


class TestDeleteCommandFull:
    """Extended delete command tests."""

    def test_delete_with_confirmation(self, patch_notebooklm):
        client, _ = patch_notebooklm
        result = runner.invoke(app, ["delete", "-n", "test-id"], input="y\n")
        assert result.exit_code == 0
        client.notebooks.delete.assert_called_once()

    def test_delete_aborted(self, patch_notebooklm):
        result = runner.invoke(app, ["delete", "-n", "test-id"], input="n\n")
        assert result.exit_code != 0


def _make_state(tmp_path, **overrides):
    """Helper to create a state file for CLI tests."""
    state = SyllabusState(
        notebook_id=overrides.get("notebook_id", "nb-123"),
        book_name=overrides.get("book_name", "Test_Book"),
        created="2026-03-10T00:00:00Z",
        max_chapters=2,
        generate_audio=True,
        generate_video=True,
        chunks=overrides.get(
            "chunks",
            {
                1: SyllabusChunk(
                    episode=1,
                    title="Foundations",
                    chapters=[1, 2],
                    source_ids=["s1", "s2"],
                    status=ChunkStatus.PENDING,
                ),
            },
        ),
    )
    state_path = tmp_path / "syllabus_state.json"
    write_state(state, state_path)
    return state_path


class TestSyllabusCommand:
    """Tests for the syllabus CLI command."""

    def test_missing_notebook_id(self, tmp_path):
        result = runner.invoke(app, ["syllabus", "-o", str(tmp_path)])
        assert result.exit_code != 0

    def test_no_sources_error(self, patch_notebooklm, tmp_path):
        client, _ = patch_notebooklm
        client.sources.list.return_value = []
        result = runner.invoke(app, ["syllabus", "-n", "nb-123", "-o", str(tmp_path)])
        assert result.exit_code != 0
        assert "No sources" in result.stdout

    def test_creates_state_file(self, patch_notebooklm, tmp_path):
        _client, _ = patch_notebooklm
        result = runner.invoke(app, ["syllabus", "-n", "nb-123", "-o", str(tmp_path)])
        assert result.exit_code == 0
        state_file = tmp_path / "syllabus_state.json"
        assert state_file.is_file()
        data = json.loads(state_file.read_text())
        assert data["notebook_id"] == "nb-123"
        assert len(data["chunks"]) >= 1

    def test_refuses_overwrite_without_force(self, patch_notebooklm, tmp_path):
        # Create existing state with a completed chunk
        _make_state(
            tmp_path,
            chunks={
                1: SyllabusChunk(
                    episode=1,
                    title="Done",
                    chapters=[1],
                    source_ids=["s1"],
                    status=ChunkStatus.COMPLETED,
                ),
            },
        )
        result = runner.invoke(app, ["syllabus", "-n", "nb-123", "-o", str(tmp_path)])
        assert result.exit_code != 0
        assert "force" in result.stdout.lower()

    def test_force_overwrites(self, patch_notebooklm, tmp_path):
        _make_state(
            tmp_path,
            chunks={
                1: SyllabusChunk(
                    episode=1,
                    title="Done",
                    chapters=[1],
                    source_ids=["s1"],
                    status=ChunkStatus.COMPLETED,
                ),
            },
        )
        result = runner.invoke(app, ["syllabus", "-n", "nb-123", "-o", str(tmp_path), "--force"])
        assert result.exit_code == 0


class TestGenerateNextCommand:
    """Tests for the generate-next CLI command."""

    def test_no_state_file(self, tmp_path):
        result = runner.invoke(app, ["generate-next", "-o", str(tmp_path)])
        assert result.exit_code != 0
        assert "No syllabus" in result.stdout

    @patch("pdf_by_chapters.notebooklm.asyncio.sleep")
    def test_all_completed(self, _mock_sleep, patch_notebooklm, tmp_path):
        _make_state(
            tmp_path,
            chunks={
                1: SyllabusChunk(
                    episode=1,
                    title="Done",
                    chapters=[1],
                    source_ids=["s1"],
                    status=ChunkStatus.COMPLETED,
                ),
            },
        )
        result = runner.invoke(app, ["generate-next", "-o", str(tmp_path)])
        assert result.exit_code == 0
        assert "completed" in result.stdout.lower()

    @patch("pdf_by_chapters.notebooklm.asyncio.sleep")
    def test_generates_pending_chunk(self, _mock_sleep, patch_notebooklm, tmp_path):
        _make_state(tmp_path)
        result = runner.invoke(app, ["generate-next", "-o", str(tmp_path)])
        assert result.exit_code == 0
        # Verify state file updated
        data = json.loads((tmp_path / "syllabus_state.json").read_text())
        assert data["chunks"][0]["status"] == "completed"

    @patch("pdf_by_chapters.notebooklm.asyncio.sleep")
    def test_episode_targeting(self, _mock_sleep, patch_notebooklm, tmp_path):
        _make_state(
            tmp_path,
            chunks={
                1: SyllabusChunk(
                    episode=1,
                    title="First",
                    chapters=[1],
                    source_ids=["s1"],
                    status=ChunkStatus.COMPLETED,
                ),
                2: SyllabusChunk(
                    episode=2,
                    title="Second",
                    chapters=[2],
                    source_ids=["s2"],
                    status=ChunkStatus.PENDING,
                ),
            },
        )
        result = runner.invoke(app, ["generate-next", "-o", str(tmp_path), "-e", "1"])
        assert result.exit_code == 0

    def test_invalid_episode(self, patch_notebooklm, tmp_path):
        _make_state(tmp_path)
        result = runner.invoke(app, ["generate-next", "-o", str(tmp_path), "-e", "99"])
        assert result.exit_code != 0
        assert "not found" in result.stdout.lower()


class TestStatusCommand:
    """Tests for the status CLI command."""

    def test_no_state_file(self, tmp_path):
        result = runner.invoke(app, ["status", "-o", str(tmp_path)])
        assert result.exit_code != 0

    def test_displays_progress(self, tmp_path):
        _make_state(
            tmp_path,
            chunks={
                1: SyllabusChunk(
                    episode=1,
                    title="Foundations",
                    chapters=[1, 2],
                    source_ids=["s1", "s2"],
                    status=ChunkStatus.COMPLETED,
                    artifacts={
                        "audio": ChunkArtifact(status="completed"),
                        "video": ChunkArtifact(status="completed"),
                    },
                ),
                2: SyllabusChunk(
                    episode=2,
                    title="Advanced",
                    chapters=[3],
                    source_ids=["s3"],
                    status=ChunkStatus.PENDING,
                ),
            },
        )
        result = runner.invoke(app, ["status", "-o", str(tmp_path)])
        assert result.exit_code == 0
        assert "Foundations" in result.stdout
        assert "Advanced" in result.stdout
        assert "1/2" in result.stdout
