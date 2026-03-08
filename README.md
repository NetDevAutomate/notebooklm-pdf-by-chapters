# notebooklm-pdf-by-chapters

Split ebook PDFs by chapter using PDF bookmarks, then upload chapters to Google NotebookLM for audio/video overview generation.

## Table of Contents

- [How It Works](#how-it-works)
- [Installation](#installation)
- [Prerequisites](#prerequisites)
- [Usage](#usage)
  - [split — Extract chapters from PDFs](#split--extract-chapters-from-pdfs)
  - [process — Split + upload to NotebookLM](#process--split--upload-to-notebooklm)
  - [list — View notebooks and sources](#list--view-notebooks-and-sources)
  - [generate — Create audio/video overviews](#generate--create-audiovideo-overviews)
  - [download — Fetch generated artifacts](#download--fetch-generated-artifacts)
  - [delete — Remove a notebook](#delete--remove-a-notebook)
- [Typical Workflow](#typical-workflow)
- [Options Reference](#options-reference)
- [How Chapter Detection Works](#how-chapter-detection-works)
- [Troubleshooting](#troubleshooting)
- [Acknowledgements](#acknowledgements)
- [License](#license)

## How It Works

Most ebook PDFs contain a Table of Contents (TOC) stored as PDF bookmarks — structured markers that map chapter titles to page numbers. This tool:

1. Reads those bookmark entries via PyMuPDF's `get_toc()` API
2. Splits the PDF at chapter boundaries into individual files
3. Preserves the internal TOC structure within each chapter file
4. Uploads the chapter files to Google NotebookLM (one notebook per book)
5. Lets you generate deep-dive audio overviews and whiteboard video explainers for any chapter range on demand

Output files are named `{book}_chapter_{nn}_{title}.pdf` and written to the output directory.

## Installation

Requires Python 3.11+.

```bash
# From local checkout
uv tool install .

# From git
uv tool install git+https://github.com/NetDevAutomate/notebooklm-pdf-by-chapters.git
```

## Prerequisites

The `split` command works out of the box — no extra setup needed.

For NotebookLM features (`process`, `list`, `generate`, `download`), authenticate first:

```bash
pip install notebooklm-py[browser]
notebooklm login
```

This opens a browser for Google cookie-based auth. Credentials are stored locally.

## Usage

### `split` — Extract chapters from PDFs

Split a single PDF into per-chapter files:

```bash
pdf-by-chapters split "my_ebook.pdf"
```

Specify an output directory:

```bash
pdf-by-chapters split "my_ebook.pdf" -o ./chapters
```

Split all PDFs in a directory:

```bash
pdf-by-chapters split ./ebooks/ -o ./chapters
```

Split at a different TOC level (e.g., level 2 for sub-chapters):

```bash
pdf-by-chapters split "my_ebook.pdf" -l 2
```

### `process` — Split + upload to NotebookLM

Split a PDF and upload all chapters to a new NotebookLM notebook:

```bash
pdf-by-chapters process "my_ebook.pdf"
```

If a notebook with the same book title already exists, it reuses it instead of creating a duplicate.

Process a directory of PDFs — each book gets its own subdirectory and notebook:

```bash
pdf-by-chapters process ./ebooks/ -o ./chapters
```

This creates `chapters/{book_name}/` for each PDF and a separate notebook per book.

Upload to an existing notebook by ID:

```bash
pdf-by-chapters process "my_ebook.pdf" -n NOTEBOOK_ID
```

On completion, a summary table is displayed:

```
┌──────────────────────────────────────┬──────────────────────────────────────┬──────────┐
│ Notebook Name                        │ ID                                   │ Chapters │
├──────────────────────────────────────┼──────────────────────────────────────┼──────────┤
│ Fundamentals of Data Engineering     │ ba6fa92e-f174-4a77-8fc6-fc4fc12a625d │       19 │
│ Designing Data-Intensive Apps        │ c7d8e9f0-a1b2-4c3d-9e8f-7a6b5c4d3e2f │       12 │
└──────────────────────────────────────┴──────────────────────────────────────┴──────────┘
```

### `list` — View notebooks and sources

List all your NotebookLM notebooks:

```bash
pdf-by-chapters list
```

List the sources (chapters) within a specific notebook:

```bash
pdf-by-chapters list -n NOTEBOOK_ID
```

This shows numbered chapters so you know which range to pass to `generate`.

### `generate` — Create audio/video overviews

Generate audio and video overviews for a specific chapter range:

```bash
pdf-by-chapters generate -n NOTEBOOK_ID -c 1-3
```

Audio only:

```bash
pdf-by-chapters generate -n NOTEBOOK_ID -c 1-3 --no-video
```

Video only:

```bash
pdf-by-chapters generate -n NOTEBOOK_ID -c 4-6 --no-audio
```

The chapter range is 1-indexed and inclusive on both ends — `-c 1-3` covers chapters 1, 2, and 3.

### `download` — Fetch generated artifacts

Download all audio and video artifacts from a notebook:

```bash
pdf-by-chapters download -n NOTEBOOK_ID -o ./overviews
```

Files are saved as `audio_01.mp3`, `audio_02.mp3`, `video_01.mp4`, etc.

### `delete` — Remove a notebook

Delete a notebook and all its contents:

```bash
pdf-by-chapters delete -n NOTEBOOK_ID
```

You will be prompted for confirmation before deletion.

## Typical Workflow

```bash
# 1. Split and upload a book (or a whole directory of books)
pdf-by-chapters process "Fundamentals of Data Engineering.pdf"

# 2. Find the notebook ID
pdf-by-chapters list

# 3. Check which chapters are in the notebook
pdf-by-chapters list -n NOTEBOOK_ID

# 4. Generate audio/video for chapters 1-3
pdf-by-chapters generate -n NOTEBOOK_ID -c 1-3

# 5. Generate for the next batch
pdf-by-chapters generate -n NOTEBOOK_ID -c 4-6

# 6. Download everything
pdf-by-chapters download -n NOTEBOOK_ID -o ./overviews
```

## Options Reference

| Option | Command | Description | Default |
|---|---|---|---|
| `source` | split, process | PDF file or directory of PDFs (positional arg) | — |
| `-o, --output-dir` | split, process, download | Output directory | `./chapters` (split/process), `./overviews` (download) |
| `-l, --level` | split, process | TOC level to split on (1 = top-level chapters) | `1` |
| `-n, --notebook-id` | process, list, generate, download, delete | NotebookLM notebook ID | — |
| `-c, --chapters` | generate, download | Chapter range, e.g. `1-3` (1-indexed, inclusive) | — |
| `--no-audio` | generate | Skip audio overview generation | — |
| `--no-video` | generate | Skip video overview generation | — |
| `-t, --timeout` | generate | Timeout in seconds for generation polling | `900` (15 min) |

## How Chapter Detection Works

PDF files can embed a Table of Contents as a tree of bookmarks. Each bookmark entry has three fields:

```
[level, title, page_number]
```

- `level` — depth in the TOC hierarchy (1 = top-level chapter, 2 = sub-chapter, etc.)
- `title` — the chapter/section name
- `page_number` — the 1-indexed page where the chapter starts

This tool calls PyMuPDF's `doc.get_toc()` to retrieve these entries, filters to the requested `--level`, and uses the page numbers to determine chapter boundaries. Each chapter runs from its start page to the page before the next chapter begins (or end of document for the last chapter).

The split chapter files also get a rebuilt TOC containing only the entries that fall within their page range.

## Troubleshooting

### No TOC / bookmarks found

```
ValueError: 'my_ebook.pdf' has no bookmarks/TOC. Cannot split without chapter markers.
```

The PDF doesn't contain embedded bookmarks. This is common with scanned PDFs or older ebooks. Options:

- Open the PDF in a reader that shows bookmarks (e.g., Adobe Acrobat, PDF Expert) to verify
- Some PDF editors can add bookmarks manually
- Consider using a different source file — most publisher ebooks include TOC bookmarks

### No entries at the requested level

```
ValueError: No TOC entries at level 2. Available levels: {1, 3}
```

The TOC doesn't have entries at the level you specified. The error message shows which levels are available — try one of those with `-l`.

### Duplicate notebook detection

When running `process`, the tool checks if a notebook with the same book title already exists. If found, it uploads chapters to the existing notebook instead of creating a duplicate. To force a new notebook, use `-n` with a specific ID or rename the PDF.

### NotebookLM authentication expired

If any NotebookLM command fails with auth errors:

```bash
# Re-authenticate
notebooklm login
```

Cookie-based auth expires periodically. Re-running `notebooklm login` refreshes the session.

### NotebookLM generation timeout

Generation times out after 900 seconds (15 minutes) by default. Both audio and video share the same timeout. If you hit timeouts:

- Increase the timeout: `generate -c 1-3 --timeout 1800` (30 minutes)
- Use smaller chapter ranges with `generate -c 1-1` (single chapter at a time)
- Skip video (which takes longer) with `--no-video` and generate audio first
- Check your network connection — uploads and polling require a stable connection

### Large PDFs produce empty chapters

If a chapter has 0 pages, the TOC bookmarks may be inaccurate or the PDF has unusual page numbering. Try:

- Inspect the TOC: `python -c "import pymupdf; print(pymupdf.open('file.pdf').get_toc())"`
- Try a different `--level` to see if sub-chapters split more cleanly

## Acknowledgements

> **Special thanks to [Teng Lin](https://github.com/teng-lin)** for creating the excellent [notebooklm-py](https://github.com/teng-lin/notebooklm-py) library, which powers all NotebookLM integration in this tool. His work in reverse-engineering and wrapping the NotebookLM API made this project possible.

## License

MIT

<!-- ARTEFACTS:START -->
## Generated Artefacts

> 🔍 **Explore this project** — AI-generated overviews via [Google NotebookLM](https://notebooklm.google.com)

| | |
|---|---|
| 🎧 **[Listen to the Audio Overview](https://netdevautomate.github.io/notebooklm-pdf-by-chapters/artefacts/)** | Two AI hosts discuss the project — great for commutes |
| 🎬 **[Watch the Video Overview](https://netdevautomate.github.io/notebooklm-pdf-by-chapters/artefacts/#video)** | Visual walkthrough of architecture and concepts |
| 🖼️ **[View the Infographic](https://netdevautomate.github.io/notebooklm-pdf-by-chapters/artefacts/#infographic)** | Architecture and flow at a glance |
| 📊 **[Browse the Slide Deck](https://netdevautomate.github.io/notebooklm-pdf-by-chapters/artefacts/#slides)** | Presentation-ready project overview |

*Generated by [notebooklm-repo-artefacts](https://github.com/NetDevAutomate/notebooklm-repo-artefacts)*
<!-- ARTEFACTS:END -->
