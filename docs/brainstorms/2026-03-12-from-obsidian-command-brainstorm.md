# Brainstorm: `from-obsidian` Command — Obsidian Markdown to NotebookLM Artifacts

**Date:** 2026-03-12
**Status:** Draft

## What We're Building

A new `from-obsidian` CLI command that converts Obsidian study-note markdown files into PDFs (with properly rendered mermaid diagrams, code blocks, and formatting), creates a NotebookLM notebook, uploads the PDFs as sources, and generates audio artifacts using `notebooklm-py` directly.

The target use case: AI-augmented course study notes (like ZTM bootcamp sections) with heavy mermaid diagrams, code examples, and structured content become NotebookLM podcast episodes for commute listening.

### Example Usage

```bash
pdf-by-chapters from-obsidian ~/Obsidian/Personal/2-Areas/Courses/ZTM/The-Data-Engineering-Bootcamp-Zero-To-Mastery/study-notes
```

This would:
1. Convert 8 study-note .md files to PDFs with rendered mermaid diagrams
2. Create a notebook named "The Data Engineering Bootcamp Zero To Mastery" (title case from parent directory)
3. Upload the 8 PDFs as sources
4. Generate audio for each source and download to `./downloads/`

## Why This Approach

- **Pandoc + mermaid-filter** for markdown-to-PDF: battle-tested, handles all mermaid diagram types, preserves code highlighting, respects markdown structure. Requires Node.js + `@mermaid-js/mermaid-cli` but these are standard dev tools.
- **One PDF per .md file**: matches the existing chapter-per-source pattern. Each study note section becomes a separate NotebookLM source, enabling per-section audio generation.
- **`notebooklm-py` directly for generation**: the library already has `generate_audio()`, `wait_for_completion()`, `download_audio()` — no need to reimplement polling/retry. This is the same library we already depend on.
- **Strip wikilinks to plain text**: `[[Note Name]]` becomes "Note Name". No need to resolve cross-vault references for NotebookLM.

## Key Decisions

### 1. New top-level command: `from-obsidian`

Separate from `process` (which handles existing PDFs). Takes a directory path, expects `.md` files.

```bash
pdf-by-chapters from-obsidian <path-to-markdown-dir> [options]
```

Notebook name derived from the parent directory name in Title Case.

### 2. Markdown to PDF via Pandoc + mermaid-filter

**Prerequisites** (documented, not bundled):
- `pandoc` (Homebrew: `brew install pandoc`)
- `@mermaid-js/mermaid-cli` (npm: `npm install -g @mermaid-js/mermaid-cli`)

The command checks for these at startup and provides clear install instructions if missing.

**Conversion pipeline per .md file:**
1. Strip YAML frontmatter
2. Convert wikilinks `[[text]]` to plain text
3. Run `pandoc` with mermaid-filter to produce PDF

### 3. Upload + generate using `notebooklm-py` directly

After conversion, uses the existing `notebooklm-py` client API:
- `client.notebooks.create(title)` — create notebook
- `client.sources.add_file(nb_id, pdf_path)` — upload each PDF
- `client.artifacts.generate_audio(nb_id, source_ids=[...])` — generate per source
- `client.artifacts.wait_for_completion(nb_id, task_id)` — wait
- `client.artifacts.download_audio(nb_id, output_path)` — download

No custom polling/retry code needed — the library handles it.

### 4. File ordering

Study notes are ordered by filename (they have section prefixes like `Section-00-`, `Section-02-`, etc.). The command sorts `.md` files alphabetically before processing.

### 5. Output structure

```
<output_dir>/
  pdfs/                          # Converted PDFs
    01-introduction.pdf
    02-section-00-introduction-to-data-engineering.pdf
    ...
  downloads/                     # Generated audio
    01-introduction.mp3
    02-section-00-introduction-to-data-engineering.mp3
    ...
```

### 6. CLI signature

```python
@app.command("from-obsidian", rich_help_panel="Obsidian")
def from_obsidian(
    source_dir: Path = typer.Argument(..., help="Directory containing .md files."),
    output_dir: Path = typer.Option(None, "--output-dir", "-o",
        help="Output directory. Defaults to source directory."),
    notebook_name: str | None = typer.Option(None, "--name",
        help="Notebook name. Defaults to parent directory in Title Case."),
    notebook_id: str | None = typer.Option(None, "--notebook-id", "-n",
        envvar="NOTEBOOK_ID", help="Use existing notebook instead of creating."),
    no_generate: bool = typer.Option(False, "--no-generate",
        help="Upload only, skip artifact generation."),
    no_download: bool = typer.Option(False, "--no-download",
        help="Generate but don't download artifacts."),
    subdirectory: str | None = typer.Option(None, "--subdir", "-s",
        help="Subdirectory within source to use (e.g. 'study-notes')."),
) -> None:
```

## Content Analysis (from real data)

The target content (`study-notes/` directory) contains:
- **8 files**, ~19,500 lines total
- **181 mermaid diagrams** (14-37 per section) — all diagram types (graph, sequence, flowchart)
- **Extensive code blocks** (Python, SQL, shell)
- **YAML frontmatter** with metadata (title, course, AI model used, etc.)
- **3 files with wikilinks** (`[[...]]`)
- **No Obsidian callouts**
- Well-structured headings (H1-H4)

## Resolved Questions

1. **Mermaid rendering**: Pandoc + mermaid-filter. Requires Node.js + mmdc CLI as prerequisites.
2. **File-to-PDF mapping**: One PDF per .md file. 8 files = 8 sources.
3. **CLI command name**: `from-obsidian` as new top-level command.
4. **Generation approach**: Use `notebooklm-py` directly — no custom polling/retry needed.
5. **Wikilinks**: Strip to plain text.
6. **Pipeline scope**: Convert + upload + generate + download in one command, with `--no-generate` and `--no-download` flags for partial runs.

## Open Questions

None — all questions resolved during brainstorm.
