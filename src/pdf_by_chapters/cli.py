"""CLI entry point for pdf-by-chapters."""

import asyncio
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from pdf_by_chapters.splitter import sanitize_filename, split_pdf_by_chapters

app = typer.Typer(help="Split ebook PDFs by chapter and upload to Google NotebookLM.")
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, show_path=False, show_time=False)],
)


def _resolve_pdfs(source: Path) -> list[Path]:
    """Resolve source to a list of PDF paths (single file or directory glob)."""
    if source.is_dir():
        pdfs = sorted(source.glob("*.pdf"))
        if not pdfs:
            console.print(f"[red]No PDF files found in {source}[/red]")
            raise typer.Exit(1)
        return pdfs
    if not source.is_file():
        console.print(f"[red]'{source}' does not exist[/red]")
        raise typer.Exit(1)
    return [source]


def _get_notebook_id(notebook_id: str | None) -> str:
    """Resolve notebook ID from argument or NOTEBOOK_ID env var."""
    if not notebook_id:
        console.print("[red]No notebook ID. Use -n or set NOTEBOOK_ID env var.[/red]")
        raise typer.Exit(1)
    return notebook_id


def _parse_chapter_range(raw: str) -> tuple[int, int]:
    """Parse a chapter range string like '1-3' into (start, end).

    Validates that start >= 1 and end >= start.
    """
    try:
        parts = raw.split("-")
        start, end = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        console.print(f"[red]Invalid chapter range '{raw}'. Use format: 1-3[/red]")
        raise typer.Exit(1) from None

    if start < 1 or end < start:
        console.print(
            f"[red]Invalid range: start must be >= 1 and <= end (got {start}-{end})[/red]"
        )
        raise typer.Exit(1)

    return (start, end)


@app.command()
def split(
    source: Path = typer.Argument(..., help="PDF file or directory of PDFs.", exists=True),
    output_dir: Path = typer.Option(Path("./chapters"), "--output-dir", "-o"),
    level: int = typer.Option(1, "--level", "-l", help="TOC level to split on (1=top-level)."),
) -> None:
    """Split a PDF (or all PDFs in a directory) into per-chapter files."""
    for pdf_path in _resolve_pdfs(source):
        book_name = sanitize_filename(pdf_path.stem)
        split_pdf_by_chapters(pdf_path, output_dir, book_name, level=level)


@app.command()
def process(
    source: Path = typer.Argument(..., help="PDF file or directory of PDFs.", exists=True),
    output_dir: Path = typer.Option(Path("./chapters"), "--output-dir", "-o"),
    level: int = typer.Option(1, "--level", "-l", help="TOC level to split on (1=top-level)."),
    notebook_id: str | None = typer.Option(
        None,
        "--notebook-id",
        "-n",
        envvar="NOTEBOOK_ID",
        help="Existing NotebookLM notebook ID.",
    ),
) -> None:
    """Split PDFs by chapter, upload to NotebookLM, and show summary.

    Handles single files or directories. For directories, each PDF gets its
    own subdirectory and notebook.
    """
    from pdf_by_chapters.notebooklm import UploadResult, upload_chapters

    pdfs = _resolve_pdfs(source)
    all_uploads: list[tuple[list[Path], str, str | None]] = []

    for pdf_path in pdfs:
        book_title = pdf_path.stem
        file_name = sanitize_filename(book_title)
        book_output_dir = output_dir / file_name if len(pdfs) > 1 else output_dir
        chapters = split_pdf_by_chapters(pdf_path, book_output_dir, file_name, level=level)

        if not chapters:
            console.print(f"[red]No chapters produced for {book_title}. Skipping.[/red]")
            continue

        nb_id = notebook_id if len(pdfs) == 1 else None
        all_uploads.append((chapters, book_title, nb_id))

    async def _upload_all() -> list[UploadResult]:
        results: list[UploadResult] = []
        for chapters, book_title, nb_id in all_uploads:
            result = await upload_chapters(
                chapter_pdfs=chapters,
                book_name=book_title,
                notebook_id=nb_id,
            )
            results.append(result)
        return results

    results = asyncio.run(_upload_all())

    if results:
        table = Table(title="Notebooks Created")
        table.add_column("Notebook Name", style="bold")
        table.add_column("ID", style="cyan")
        table.add_column("Chapters", justify="right")
        for r in results:
            table.add_row(r.title, r.id, str(r.chapters))
        console.print(table)

        last_id = results[-1].id
        console.print("\nTo use this notebook in other commands:")
        console.print(f"  export NOTEBOOK_ID={last_id}")


@app.command("list")
def list_cmd(
    notebook_id: str | None = typer.Option(
        None,
        "--notebook-id",
        "-n",
        envvar="NOTEBOOK_ID",
        help="List sources in this notebook instead of listing notebooks.",
    ),
) -> None:
    """List notebooks, or sources within a notebook."""
    from pdf_by_chapters.notebooklm import list_notebooks as _list_notebooks
    from pdf_by_chapters.notebooklm import list_sources

    if notebook_id:
        results = asyncio.run(list_sources(notebook_id))
        table = Table(title=f"Sources in {notebook_id}")
        table.add_column("#", justify="right", style="dim")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="bold")
        for i, r in enumerate(results, 1):
            table.add_row(str(i), r.id, r.title)
        console.print(table)
    else:
        results = asyncio.run(_list_notebooks())
        table = Table(title="Notebooks")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="bold")
        table.add_column("Sources", justify="right")
        for r in results:
            table.add_row(r.id, r.title, str(r.sources_count))
        console.print(table)


@app.command()
def generate(
    notebook_id: str | None = typer.Option(
        None,
        "--notebook-id",
        "-n",
        envvar="NOTEBOOK_ID",
        help="Notebook ID to generate from.",
    ),
    chapters: str = typer.Option(
        ...,
        "--chapters",
        "-c",
        help="Chapter range, e.g. '1-3' (1-indexed, inclusive).",
    ),
    no_audio: bool = typer.Option(False, "--no-audio", help="Skip audio generation."),
    no_video: bool = typer.Option(False, "--no-video", help="Skip video generation."),
    timeout: int = typer.Option(
        900, "--timeout", "-t", help="Timeout in seconds (default: 900 = 15min)."
    ),
) -> None:
    """Generate audio/video overviews for a chapter range.

    Fires off requests concurrently, polls every 30s until complete.
    """
    from pdf_by_chapters.notebooklm import generate_for_chapters

    nb_id = _get_notebook_id(notebook_id)
    chapter_range = _parse_chapter_range(chapters)

    asyncio.run(
        generate_for_chapters(
            nb_id,
            chapter_range,
            generate_audio=not no_audio,
            generate_video=not no_video,
            timeout=timeout,
        )
    )


@app.command()
def download(
    notebook_id: str | None = typer.Option(
        None,
        "--notebook-id",
        "-n",
        envvar="NOTEBOOK_ID",
        help="Notebook ID to download from.",
    ),
    output_dir: Path = typer.Option(
        Path("./overviews"), "--output-dir", "-o", help="Output directory."
    ),
    chapters: str | None = typer.Option(
        None, "--chapters", "-c", help="Chapter range label for filenames, e.g. '1-3'."
    ),
) -> None:
    """Download audio and video artifacts from a notebook.

    Use -c to name files by chapter range (e.g. audio_ch1-3.mp3).
    """
    from pdf_by_chapters.notebooklm import download_artifacts

    nb_id = _get_notebook_id(notebook_id)
    chapter_range = _parse_chapter_range(chapters) if chapters else None
    asyncio.run(download_artifacts(nb_id, output_dir, chapter_range=chapter_range))


@app.command("delete")
def delete_cmd(
    notebook_id: str | None = typer.Option(
        None, "--notebook-id", "-n", envvar="NOTEBOOK_ID", help="Notebook ID to delete."
    ),
) -> None:
    """Delete a notebook and all its contents."""
    from pdf_by_chapters.notebooklm import delete_notebook

    nb_id = _get_notebook_id(notebook_id)
    typer.confirm(f"Delete notebook {nb_id}?", abort=True)
    asyncio.run(delete_notebook(nb_id))
