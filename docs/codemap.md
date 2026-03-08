# Code Map — notebooklm-pdf-by-chapters

> Architecture, module relationships, and data flows for the `pdf-by-chapters` CLI tool.

## Overview

`notebooklm-pdf-by-chapters` splits ebook PDFs by chapter using TOC bookmarks, uploads chapters to Google NotebookLM as individual sources, and generates audio/video overviews per chapter range.

```mermaid
graph LR
    subgraph "Input"
        PDF[Ebook PDF<br/>with TOC bookmarks]
    end

    subgraph "pdf-by-chapters CLI"
        CLI[cli.py<br/>Typer commands]
        SPL[splitter.py<br/>PDF splitting]
        NLM[notebooklm.py<br/>API integration]
    end

    subgraph "External"
        NLMAPI[Google NotebookLM]
    end

    subgraph "Output"
        CHAPS[Chapter PDFs]
        AUDIO[Audio overviews]
        VIDEO[Video explainers]
    end

    PDF --> SPL
    SPL --> CHAPS
    CHAPS --> NLM
    NLM --> NLMAPI
    NLMAPI --> AUDIO & VIDEO
    CLI --> SPL & NLM
```

## Module Breakdown

### cli.py — Command Router

Entry point using [Typer](https://typer.tiangolo.com/). Routes to splitter and NotebookLM modules.

| Command | Description | Calls |
|---------|-------------|-------|
| `split` | Split PDF into chapter files | `splitter` |
| `process` | Split + upload to NotebookLM | `splitter` → `notebooklm` |
| `generate` | Generate audio/video for chapter range | `notebooklm` |
| `download` | Download generated artifacts | `notebooklm` |
| `list` | List notebooks or sources | `notebooklm` |
| `delete` | Delete a notebook | `notebooklm` |

### splitter.py — PDF Chapter Splitting

Uses [PyMuPDF](https://pymupdf.readthedocs.io/) to split PDFs by TOC bookmarks.

```mermaid
graph TD
    A[Input PDF] --> B[Extract TOC bookmarks]
    B --> C{TOC exists?}
    C -->|No| D[Error: no bookmarks]
    C -->|Yes| E[Filter by level]
    E --> F{Entries at level?}
    F -->|No| G[Error: wrong level]
    F -->|Yes| H[Calculate page ranges]
    H --> I[Loop: extract pages]
    I --> J[Rebuild sub-TOC]
    J --> K[Save chapter PDF]
    K --> L[chapter_01_introduction.pdf<br/>chapter_02_architecture.pdf<br/>...]
```

**Key features:**
- Splits on any TOC level (default: level 1 = top-level chapters)
- Preserves sub-TOC within each chapter PDF
- Sanitises filenames (lowercase, underscores, max 80 chars)
- Handles single files or directories of PDFs

### notebooklm.py — NotebookLM API Integration

Manages notebook lifecycle and chapter-aware generation.

```mermaid
sequenceDiagram
    actor User
    participant CLI
    participant NLM as notebooklm.py
    participant API as NotebookLM API

    User->>CLI: process book.pdf
    CLI->>NLM: upload_chapters(chapter_pdfs)
    loop Each chapter PDF
        NLM->>API: add_file(chapter.pdf)
        Note over NLM: 2s delay between uploads
    end
    API-->>NLM: notebook_id

    User->>CLI: generate -c 1-3
    CLI->>NLM: generate_for_chapters(range=1-3)
    NLM->>NLM: Select source_ids for chapters 1-3
    NLM->>API: generate_audio(source_ids)
    NLM->>API: generate_video(source_ids)
    loop Poll every 30s
        NLM->>API: poll_status
        alt Failed
            NLM->>API: Retry (max 3)
        end
    end

    User->>CLI: download -c 1-3
    CLI->>NLM: download_artifacts(chapter_range)
    NLM-->>User: audio_ch1-3.mp3, video_ch1-3.mp4
```

**Chapter-aware generation:** Unlike `repo-artefacts` which generates for the whole repo, this tool selects specific NotebookLM sources by chapter range, allowing focused overviews of specific sections.

## Interfaces

| Module | Exports | Used By |
|--------|---------|---------|
| `splitter` | `split_pdf_by_chapters()`, `sanitize_filename()` | `cli.split`, `cli.process` |
| `notebooklm` | `upload_chapters()`, `generate_for_chapters()`, `download_artifacts()`, `list_notebooks()`, `list_sources()`, `delete_notebook()` | `cli.*` |

## Dependencies

```mermaid
graph BT
    CLI[cli.py] --> SPL[splitter.py]
    CLI --> NLM[notebooklm.py]

    SPL -.-> PYMUPDF[pymupdf]
    NLM -.-> NLMPY[notebooklm-py]
    CLI -.-> TYPER[typer]
    CLI -.-> RICH[rich]
```
