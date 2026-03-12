"""CLI entry point for pdf-by-chapters."""

import asyncio
import logging
from pathlib import Path
from typing import Any

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
    from pdf_by_chapters.models import UploadResult
    from pdf_by_chapters.notebooklm import upload_chapters

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


# ---------------------------------------------------------------------------
# Syllabus workflow commands
# ---------------------------------------------------------------------------


@app.command(rich_help_panel="Syllabus")
def syllabus(
    notebook_id: str | None = typer.Option(
        None,
        "--notebook-id",
        "-n",
        envvar="NOTEBOOK_ID",
        help="Notebook ID to generate syllabus for.",
    ),
    output_dir: Path = typer.Option(Path("./chapters"), "--output-dir", "-o"),
    max_chapters: int = typer.Option(
        2, "--max-chapters", "-m", help="Maximum chapters per episode (default: 2)."
    ),
    book_name: str | None = typer.Option(
        None, "--book-name", "-b", help="Book name for state file. Defaults to output dir name."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing syllabus even if chunks are in progress."
    ),
    no_audio: bool = typer.Option(False, "--no-audio", help="Skip audio generation."),
    no_video: bool = typer.Option(False, "--no-video", help="Skip video generation."),
) -> None:
    """Generate a podcast syllabus via NotebookLM chat and save as a plan."""
    from datetime import UTC, datetime

    from notebooklm import NotebookLMClient

    from pdf_by_chapters.notebooklm import create_syllabus as _create_syllabus
    from pdf_by_chapters.notebooklm import list_sources
    from pdf_by_chapters.syllabus import (
        STATE_FILENAME,
        SyllabusParseError,
        SyllabusState,
        SyllabusStateError,
        build_fixed_size_chunks,
        build_prompt,
        has_non_pending_chunks,
        map_sources_to_chapters,
        parse_syllabus_response,
        read_state,
        write_state,
    )

    nb_id = _get_notebook_id(notebook_id)
    state_path = output_dir / STATE_FILENAME
    resolved_book_name = book_name or output_dir.resolve().name

    # Check for existing state
    if state_path.is_file() and not force:
        try:
            existing = read_state(state_path)
            if has_non_pending_chunks(existing):
                console.print(
                    "[red]Syllabus already exists with in-progress chunks. "
                    "Use --force to overwrite.[/red]"
                )
                raise typer.Exit(1)
        except SyllabusStateError:
            pass  # Corrupt file — safe to overwrite

    # Fetch sources and build mapping
    sources_list = asyncio.run(list_sources(nb_id))
    if not sources_list:
        console.print("[red]No sources found in notebook. Upload chapters first.[/red]")
        raise typer.Exit(1)

    source_tuples = [(s.id, s.title) for s in sources_list]
    source_map, title_map = map_sources_to_chapters(source_tuples)

    # Build and send prompt
    prompt = build_prompt(source_tuples, max_chapters)

    async def _run_syllabus() -> str:
        async with await NotebookLMClient.from_storage() as client:
            return await _create_syllabus(client, nb_id, prompt)

    response = asyncio.run(_run_syllabus())

    # Parse response, fall back to fixed-size on failure
    try:
        chunks = parse_syllabus_response(response, source_map, title_map)
        console.print("[green]Syllabus parsed successfully from NotebookLM.[/green]")
    except SyllabusParseError as exc:
        console.print(f"[yellow]Could not parse syllabus: {exc}[/yellow]")
        console.print("[yellow]Falling back to fixed-size chunks.[/yellow]")
        chunks = build_fixed_size_chunks(source_map, max_chapters, title_map)

    # Build and save state
    state = SyllabusState(
        notebook_id=nb_id,
        book_name=resolved_book_name,
        created=datetime.now(UTC).isoformat(),
        max_chapters=max_chapters,
        generate_audio=not no_audio,
        generate_video=not no_video,
        chunks=chunks,
    )
    write_state(state, state_path)

    # Display syllabus table
    table = Table(title=f"Syllabus: {resolved_book_name}")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Title", style="bold")
    table.add_column("Chapters", style="cyan")
    table.add_column("Status")
    for chunk in state.chunks.values():
        ch_str = ", ".join(str(c) for c in chunk.chapters)
        table.add_row(str(chunk.episode), chunk.title, ch_str, chunk.status.value)
    console.print(table)
    console.print(f"\nState saved to {state_path}")
    console.print(f"Next: Run [bold]pdf-by-chapters generate-next -o {output_dir}[/bold]")


_RETRY_WAITS = [60, 180, 300]  # seconds between retries in --all mode
_EPISODE_GAP = 30  # seconds between episodes in --all mode


def _generate_one_episode(
    state: Any,
    chunk: Any,
    state_path: Path,
    output_dir: Path,
    gen_audio: bool,
    gen_video: bool,
    no_wait: bool,
    timeout: int,
) -> bool:
    """Generate a single episode. Returns True if completed, False if failed."""
    from notebooklm import NotebookLMClient

    from pdf_by_chapters.notebooklm import poll_chunk_status, start_chunk_generation
    from pdf_by_chapters.syllabus import ChunkArtifact, ChunkStatus, title_case_name, write_state

    console.print(
        f"Generating episode {chunk.episode}: [bold]{chunk.title}[/bold] "
        f"(chapters {', '.join(str(c) for c in chunk.chapters)})"
    )

    # Fire generation and persist task IDs immediately
    async def _start() -> dict[str, str]:
        async with await NotebookLMClient.from_storage() as client:
            return await start_chunk_generation(
                client,
                state.notebook_id,
                chunk.source_ids,
                chunk.title,
                generate_audio=gen_audio,
                generate_video=gen_video,
                chapter_titles=chunk.chapter_titles or None,
            )

    tasks = asyncio.run(_start())
    if not tasks:
        console.print("[red]Failed to start any generation requests.[/red]")
        chunk.status = ChunkStatus.FAILED
        write_state(state, state_path)
        return False

    for label, task_id in tasks.items():
        chunk.artifacts[label] = ChunkArtifact(task_id=task_id, status="in_progress")
    chunk.status = ChunkStatus.GENERATING
    write_state(state, state_path)

    if no_wait:
        console.print(
            f"[green]Generation started for episode {chunk.episode}.[/green]\n"
            f"Use [bold]pdf-by-chapters status -o {output_dir} --poll[/bold] to check progress."
        )
        return True  # "started" counts as success for no-wait

    console.print("[dim]Polling every 30s... (Ctrl+C is safe)[/dim]")

    async def _poll_loop() -> None:
        import contextlib

        elapsed = 0
        poll_interval = 30
        async with await NotebookLMClient.from_storage() as client:
            while elapsed < timeout:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                pending_tasks = {
                    lbl: art.task_id
                    for lbl, art in chunk.artifacts.items()
                    if art.task_id and art.status not in ("completed", "failed")
                }
                if not pending_tasks:
                    break
                statuses = await poll_chunk_status(client, state.notebook_id, pending_tasks)
                for lbl, new_status in statuses.items():
                    chunk.artifacts[lbl].status = new_status
                write_state(state, state_path)
                if all(a.status in ("completed", "failed") for a in chunk.artifacts.values()):
                    break

            # Rename completed artifacts (best-effort, Title Case)
            display_title = title_case_name(chunk.title)
            if display_title:
                for _lbl, art in chunk.artifacts.items():
                    if art.task_id and art.status == "completed":
                        with contextlib.suppress(Exception):
                            await client.artifacts.rename(
                                state.notebook_id, art.task_id, display_title
                            )

    try:
        asyncio.run(_poll_loop())
    except KeyboardInterrupt:
        console.print(
            "\n[yellow]Interrupted. Task IDs saved to state file.[/yellow]\n"
            f"Resume with: [bold]pdf-by-chapters status -o {output_dir} --poll[/bold]"
        )
        raise typer.Exit(0) from None

    all_done = all(a.status == "completed" for a in chunk.artifacts.values())
    chunk.status = ChunkStatus.COMPLETED if all_done else ChunkStatus.FAILED
    write_state(state, state_path)

    if chunk.status == ChunkStatus.COMPLETED:
        console.print(f"[green]Episode {chunk.episode} completed.[/green]")
        return True

    console.print(f"[yellow]Episode {chunk.episode} had failures.[/yellow]")
    for label, art in chunk.artifacts.items():
        if art.status != "completed":
            console.print(f"  {label}: {art.status}")
    return False


def _download_episode(
    state: Any,
    chunk: Any,
    output_dir: Path,
) -> None:
    """Download completed audio for a single episode."""
    from notebooklm import NotebookLMClient

    from pdf_by_chapters.notebooklm import download_episode_audio
    from pdf_by_chapters.splitter import sanitize_filename as _sanitize

    audio_art = chunk.artifacts.get("audio")
    if not audio_art or not audio_art.task_id or audio_art.status != "completed":
        return

    downloads_dir = output_dir / "downloads"
    safe_name = _sanitize(chunk.title)
    filename = f"{chunk.episode:02d}-{safe_name}.mp3"
    out_path = downloads_dir / filename

    if out_path.exists():
        console.print(f"  [dim]Already downloaded: {out_path}[/dim]")
        return

    async def _dl() -> None:
        async with await NotebookLMClient.from_storage() as client:
            await download_episode_audio(client, state.notebook_id, audio_art.task_id, out_path)

    try:
        asyncio.run(_dl())
        console.print(f"  Downloaded: {out_path}")
    except Exception as exc:
        console.print(f"  [yellow]Download failed for episode {chunk.episode}: {exc}[/yellow]")


@app.command("generate-next", rich_help_panel="Syllabus")
def generate_next(
    output_dir: Path = typer.Option(Path("./chapters"), "--output-dir", "-o"),
    episode: int | None = typer.Option(
        None, "--episode", "-e", help="Target a specific episode by number."
    ),
    no_audio: bool = typer.Option(False, "--no-audio", help="Skip audio generation."),
    no_video: bool = typer.Option(False, "--no-video", help="Skip video generation."),
    no_wait: bool = typer.Option(
        False, "--no-wait", help="Start generation and return immediately without polling."
    ),
    timeout: int = typer.Option(
        900, "--timeout", "-t", help="Timeout in seconds (default: 900 = 15min)."
    ),
    all_episodes: bool = typer.Option(
        False, "--all", "-a", help="Generate all episodes sequentially with retry."
    ),
    download: bool = typer.Option(
        False, "--download", "-d", help="Download audio after each completed episode."
    ),
    notebook_id: str | None = typer.Option(
        None,
        "--notebook-id",
        "-n",
        envvar="NOTEBOOK_ID",
        help="Notebook ID (required with --all if no syllabus exists).",
    ),
) -> None:
    """Generate audio/video for the next pending episode.

    Uses notebook_id from the syllabus state file (not --notebook-id).
    With --no-wait, fires the request and returns immediately.
    With --all, generates all episodes sequentially with exponential backoff retry.
    With --download, downloads audio after each completed episode.
    """
    import time

    from notebooklm import NotebookLMClient

    from pdf_by_chapters.notebooklm import delete_artifact
    from pdf_by_chapters.syllabus import (
        STATE_FILENAME,
        ChunkStatus,
        SyllabusStateError,
        get_next_chunk,
        read_state,
        write_state,
    )

    state_path = output_dir / STATE_FILENAME

    # --all mode: auto-create syllabus if missing, then loop all episodes
    if all_episodes:
        if not state_path.is_file():
            nb_id = _get_notebook_id(notebook_id)
            console.print("[dim]No syllabus found. Creating one...[/dim]")
            # Invoke syllabus command programmatically
            syllabus(
                notebook_id=nb_id,
                output_dir=output_dir,
                max_chapters=2,
                book_name=None,
                force=False,
                no_audio=no_audio,
                no_video=no_video,
            )

        state = read_state(state_path)
        gen_audio = (not no_audio) and state.generate_audio
        gen_video = (not no_video) and state.generate_video

        for chunk in sorted(state.chunks.values(), key=lambda c: c.episode):
            if chunk.status == ChunkStatus.COMPLETED:
                console.print(f"[dim]Episode {chunk.episode} already completed. Skipping.[/dim]")
                if download:
                    _download_episode(state, chunk, output_dir)
                continue

            # Attempt generation with exponential backoff retry
            success = False
            for attempt in range(len(_RETRY_WAITS) + 1):
                chunk.status = ChunkStatus.PENDING
                chunk.artifacts = {}
                write_state(state, state_path)

                success = _generate_one_episode(
                    state,
                    chunk,
                    state_path,
                    output_dir,
                    gen_audio,
                    gen_video,
                    no_wait=False,
                    timeout=timeout,
                )

                if success:
                    if download:
                        _download_episode(state, chunk, output_dir)
                    break

                # Failed — delete artifacts and retry with backoff
                artifacts_to_delete = [
                    art.task_id for art in chunk.artifacts.values() if art.task_id
                ]

                async def _cleanup(ids: list[str]) -> None:
                    async with await NotebookLMClient.from_storage() as client:
                        for aid in ids:
                            await delete_artifact(client, state.notebook_id, aid)

                asyncio.run(_cleanup(artifacts_to_delete))

                if attempt < len(_RETRY_WAITS):
                    wait = _RETRY_WAITS[attempt]
                    console.print(
                        f"[yellow]Retrying in {wait}s "
                        f"(attempt {attempt + 2}/{len(_RETRY_WAITS) + 1})...[/yellow]"
                    )
                    time.sleep(wait)
                else:
                    console.print(
                        f"[red]Episode {chunk.episode} failed after "
                        f"{len(_RETRY_WAITS) + 1} attempts. Stopping.[/red]"
                    )
                    raise typer.Exit(1)

            # Gap between episodes to respect rate limits
            remaining = [
                c
                for c in state.chunks.values()
                if c.episode > chunk.episode and c.status != ChunkStatus.COMPLETED
            ]
            if remaining and success:
                console.print(f"[dim]Waiting {_EPISODE_GAP}s before next episode...[/dim]")
                time.sleep(_EPISODE_GAP)

        total = len(state.chunks)
        completed = sum(1 for c in state.chunks.values() if c.status == ChunkStatus.COMPLETED)
        console.print(f"\n[green]Done. {completed}/{total} episodes completed.[/green]")
        return

    # Single-episode mode (existing behaviour)
    try:
        state = read_state(state_path)
    except SyllabusStateError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None

    if episode is not None:
        if episode not in state.chunks:
            max_ep = max(state.chunks.keys()) if state.chunks else 0
            console.print(
                f"[red]Episode {episode} not found. Syllabus has episodes 1-{max_ep}.[/red]"
            )
            raise typer.Exit(1)
        chunk = state.chunks[episode]
        if chunk.status == ChunkStatus.COMPLETED:
            console.print(
                f"[yellow]Episode {episode} already completed. "
                "Resetting to pending (previous artifacts remain in NotebookLM).[/yellow]"
            )
        chunk.status = ChunkStatus.PENDING
        chunk.artifacts = {}
    else:
        chunk = get_next_chunk(state)
        if chunk is None:
            total = len(state.chunks)
            console.print(
                f"[green]All {total} episodes completed. "
                "Use --episode N to regenerate a specific one.[/green]"
            )
            raise typer.Exit(0)

    gen_audio = (not no_audio) and state.generate_audio
    gen_video = (not no_video) and state.generate_video

    success = _generate_one_episode(
        state,
        chunk,
        state_path,
        output_dir,
        gen_audio,
        gen_video,
        no_wait,
        timeout,
    )

    if success and download and not no_wait:
        _download_episode(state, chunk, output_dir)

    if not no_wait:
        console.print("\n[dim]Rate limits apply. Wait before generating the next chunk.[/dim]")


@app.command(rich_help_panel="Syllabus")
def status(
    output_dir: Path = typer.Option(Path("./chapters"), "--output-dir", "-o"),
    poll: bool = typer.Option(False, "--poll", help="Check API for status of generating chunks."),
    tail: bool = typer.Option(
        False, "--tail", help="Live display. Polls every 30s until generation completes."
    ),
) -> None:
    """Show syllabus progress for chunked generation.

    Use --poll to check the NotebookLM API for in-progress artifacts and
    update the state file. Use --tail for a live-updating display.
    """
    from pdf_by_chapters.syllabus import (
        STATE_FILENAME,
        ChunkStatus,
        SyllabusStateError,
        read_state,
        write_state,
    )

    state_path = output_dir / STATE_FILENAME

    try:
        state = read_state(state_path)
    except SyllabusStateError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None

    # If --poll, check API for generating chunks and update state
    if poll:
        generating = [c for c in state.chunks.values() if c.status == ChunkStatus.GENERATING]
        if generating:
            import contextlib

            from notebooklm import NotebookLMClient

            from pdf_by_chapters.notebooklm import poll_chunk_status
            from pdf_by_chapters.syllabus import title_case_name as _title_case

            async def _poll_all() -> None:
                async with await NotebookLMClient.from_storage() as client:
                    for chunk in generating:
                        tasks = {
                            label: art.task_id
                            for label, art in chunk.artifacts.items()
                            if art.task_id and art.status != "completed"
                        }
                        if not tasks:
                            continue
                        statuses = await poll_chunk_status(client, state.notebook_id, tasks)
                        for label, new_status in statuses.items():
                            chunk.artifacts[label].status = new_status

                        # Update chunk-level status
                        all_done = all(a.status == "completed" for a in chunk.artifacts.values())
                        any_failed = any(a.status == "failed" for a in chunk.artifacts.values())
                        if all_done:
                            chunk.status = ChunkStatus.COMPLETED
                            # Best-effort rename
                            display_title = _title_case(chunk.title)
                            if display_title:
                                for _label, art in chunk.artifacts.items():
                                    if art.task_id and art.status == "completed":
                                        with contextlib.suppress(Exception):
                                            await client.artifacts.rename(
                                                state.notebook_id,
                                                art.task_id,
                                                display_title,
                                            )
                        elif any_failed:
                            chunk.status = ChunkStatus.FAILED

            asyncio.run(_poll_all())
            write_state(state, state_path)
            console.print("[dim]Polled API for in-progress artifacts.[/dim]\n")
        else:
            console.print("[dim]No generating chunks to poll.[/dim]\n")

    def _build_status_table(st: Any, elapsed_str: str = "") -> Table:
        _styles = {
            ChunkStatus.COMPLETED: "[green]completed[/green]",
            ChunkStatus.GENERATING: "[yellow]generating[/yellow]",
            ChunkStatus.FAILED: "[red]failed[/red]",
            ChunkStatus.PENDING: "[dim]pending[/dim]",
        }
        tbl = Table(title=f"Syllabus: {st.book_name}")
        tbl.add_column("#", justify="right", style="dim")
        tbl.add_column("Title", style="bold")
        tbl.add_column("Chapters", style="cyan")
        tbl.add_column("Audio")
        tbl.add_column("Video")
        tbl.add_column("Status")

        done = 0
        for ch in sorted(st.chunks.values(), key=lambda c: c.episode):
            ch_str = ", ".join(str(n) for n in ch.chapters)
            a = ch.artifacts.get("audio")
            v = ch.artifacts.get("video")
            tbl.add_row(
                str(ch.episode),
                ch.title,
                ch_str,
                a.status if a else "-",
                v.status if v else "-",
                _styles.get(ch.status, ch.status.value),
            )
            if ch.status == ChunkStatus.COMPLETED:
                done += 1

        tbl.caption = f"{done}/{len(st.chunks)} episodes completed"
        if elapsed_str:
            tbl.caption += f"  |  Elapsed: {elapsed_str}"
        return tbl

    if tail:
        import time

        from notebooklm import NotebookLMClient
        from rich.live import Live

        from pdf_by_chapters.notebooklm import poll_chunk_status

        poll_interval = 30
        start_time = time.monotonic()

        def _elapsed() -> str:
            secs = int(time.monotonic() - start_time)
            return f"{secs // 60:02d}:{secs % 60:02d}"

        live = Live(
            _build_status_table(state, _elapsed()),
            console=console,
            refresh_per_second=1,
        )
        with live:
            while any(c.status == ChunkStatus.GENERATING for c in state.chunks.values()):
                time.sleep(poll_interval)

                # Poll API
                generating = [
                    c for c in state.chunks.values() if c.status == ChunkStatus.GENERATING
                ]
                if generating:
                    gen_chunks = list(generating)

                    async def _poll_gen(chunks_to_poll: list) -> None:
                        async with await NotebookLMClient.from_storage() as client:
                            for chunk in chunks_to_poll:
                                tasks = {
                                    label: art.task_id
                                    for label, art in chunk.artifacts.items()
                                    if art.task_id and art.status != "completed"
                                }
                                if not tasks:
                                    continue
                                statuses = await poll_chunk_status(
                                    client, state.notebook_id, tasks
                                )
                                for label, new_st in statuses.items():
                                    chunk.artifacts[label].status = new_st
                                all_done = all(
                                    a.status == "completed" for a in chunk.artifacts.values()
                                )
                                any_failed = any(
                                    a.status == "failed" for a in chunk.artifacts.values()
                                )
                                if all_done:
                                    chunk.status = ChunkStatus.COMPLETED
                                elif any_failed:
                                    chunk.status = ChunkStatus.FAILED

                    asyncio.run(_poll_gen(gen_chunks))
                    write_state(state, state_path)

                live.update(_build_status_table(state, _elapsed()))

            # Final update
            live.update(_build_status_table(state, _elapsed()))
        return

    console.print(_build_status_table(state))


# ---------------------------------------------------------------------------
# Obsidian workflow commands
# ---------------------------------------------------------------------------


@app.command("from-obsidian", rich_help_panel="Obsidian")
def from_obsidian(
    source_dir: Path = typer.Argument(..., help="Directory containing .md files."),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", "-o", help="Output directory. Defaults to source directory."
    ),
    notebook_name: str | None = typer.Option(
        None, "--name", help="Notebook name. Defaults to directory name in Title Case."
    ),
    notebook_id: str | None = typer.Option(
        None,
        "--notebook-id",
        "-n",
        envvar="NOTEBOOK_ID",
        help="Use existing notebook instead of creating one.",
    ),
    no_generate: bool = typer.Option(
        False, "--no-generate", help="Upload only, skip artifact generation."
    ),
    no_download: bool = typer.Option(
        False, "--no-download", help="Generate but don't download artifacts."
    ),
    subdir: str | None = typer.Option(
        None, "--subdir", "-s", help="Subdirectory within source (e.g. 'study-notes')."
    ),
) -> None:
    """Convert Obsidian markdown to PDFs, upload to NotebookLM, and generate audio.

    Renders mermaid diagrams and code blocks properly in PDFs using pandoc.
    Requires: pandoc (brew install pandoc) and @mermaid-js/mermaid-cli
    (npm install -g @mermaid-js/mermaid-cli).
    """
    from notebooklm import NotebookLMClient

    from pdf_by_chapters.markdown_converter import ConversionError, convert_directory
    from pdf_by_chapters.splitter import sanitize_filename

    # Resolve paths
    resolved_source = source_dir.expanduser().resolve()
    if subdir:
        resolved_source = resolved_source / subdir

    if not resolved_source.is_dir():
        console.print(f"[red]Directory not found: {resolved_source}[/red]")
        raise typer.Exit(1)

    resolved_output = (output_dir or source_dir).expanduser().resolve()
    name = notebook_name or resolved_source.name.replace("-", " ").replace("_", " ").title()

    console.print(f"[bold]Notebook:[/bold] {name}")
    console.print(f"[bold]Source:[/bold] {resolved_source}")
    console.print(f"[bold]Output:[/bold] {resolved_output}")
    console.print()

    # Step 1: Convert markdown to PDFs
    console.print("[bold]Step 1:[/bold] Converting markdown to PDF...")
    try:
        pdfs = convert_directory(resolved_source, resolved_output)
    except (ConversionError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None

    if not pdfs:
        console.print("[red]No PDFs generated. Check conversion errors above.[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Converted {len(pdfs)} files to PDF.[/green]\n")

    # Step 2: Create notebook and upload
    console.print("[bold]Step 2:[/bold] Uploading to NotebookLM...")

    async def _upload() -> tuple[str, str]:
        async with await NotebookLMClient.from_storage() as client:
            if notebook_id:
                nb_id = notebook_id
                nb_title = name
            else:
                # Check for existing notebook with same name
                notebooks = await client.notebooks.list()
                existing = next((nb for nb in notebooks if nb.title == name), None)
                if existing:
                    nb_id = existing.id
                    nb_title = existing.title
                    console.print(f"  Found existing notebook: {nb_title}")
                else:
                    nb = await client.notebooks.create(name)
                    nb_id = nb.id
                    nb_title = nb.title
                    console.print(f"  Created notebook: {nb_title}")

            for pdf_path in pdfs:
                await client.sources.add_file(nb_id, pdf_path)
                console.print(f"  Uploaded {pdf_path.name}")
                import asyncio as _asyncio

                await _asyncio.sleep(2)

            return nb_id, nb_title

    nb_id, nb_title = asyncio.run(_upload())
    console.print(f"[green]Uploaded {len(pdfs)} sources to '{nb_title}'.[/green]")
    console.print(f"  Notebook ID: [cyan]{nb_id}[/cyan]\n")

    if no_generate:
        console.print("Skipping generation (--no-generate).")
        console.print(f"\nexport NOTEBOOK_ID={nb_id}")
        return

    # Step 3: Generate audio for each source
    console.print("[bold]Step 3:[/bold] Generating audio overviews...")

    async def _generate_and_download() -> None:
        async with await NotebookLMClient.from_storage() as client:
            sources = await client.sources.list(nb_id)
            sources.sort(key=lambda s: s.title or "")

            downloads_dir = resolved_output / "downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)

            for i, source in enumerate(sources, 1):
                src_title = source.title or f"source-{i}"
                console.print(f"\n  [{i}/{len(sources)}] Generating audio for: {src_title}")

                try:
                    status = await client.artifacts.generate_audio(
                        nb_id,
                        source_ids=[source.id],
                        instructions=f"Create an engaging audio deep-dive for: {src_title}",
                    )

                    if status.is_failed or not status.task_id:
                        console.print(
                            f"  [yellow]Generation rejected: "
                            f"{status.error or 'unknown error'}[/yellow]"
                        )
                        continue

                    console.print("  Waiting for completion...")
                    await client.artifacts.wait_for_completion(
                        nb_id, status.task_id, timeout=900.0
                    )
                    console.print("  [green]Audio ready.[/green]")

                    # Rename artifact with Title Case
                    import contextlib

                    safe_name = sanitize_filename(src_title)
                    display_name = src_title.replace("-", " ").replace("_", " ").title()
                    with contextlib.suppress(Exception):
                        await client.artifacts.rename(nb_id, status.task_id, display_name)

                    # Download
                    if not no_download:
                        filename = f"{i:02d}-{safe_name}.mp3"
                        dl_path = downloads_dir / filename
                        await client.artifacts.download_audio(
                            nb_id, str(dl_path), artifact_id=status.task_id
                        )
                        console.print(f"  Downloaded: {dl_path.name}")

                except TimeoutError:
                    console.print(f"  [yellow]Timed out for {src_title}[/yellow]")
                except Exception as exc:
                    console.print(f"  [yellow]Error: {exc}[/yellow]")

                # Gap between generations
                if i < len(sources):
                    import time

                    console.print("  [dim]Waiting 30s before next...[/dim]")
                    time.sleep(30)

    asyncio.run(_generate_and_download())

    console.print(f"\n[green]Done! Notebook: {nb_title} ({nb_id})[/green]")
    console.print(f"export NOTEBOOK_ID={nb_id}")
