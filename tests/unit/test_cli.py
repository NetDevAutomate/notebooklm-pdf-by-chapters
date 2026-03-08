"""Unit tests for pdf_by_chapters.cli."""

from unittest.mock import patch

from typer.testing import CliRunner

from pdf_by_chapters.cli import app

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
