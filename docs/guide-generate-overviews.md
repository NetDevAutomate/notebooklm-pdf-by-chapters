# Generating Audio & Video Overviews

Create deep-dive audio podcasts and whiteboard video explainers from your uploaded chapters.

## ✅ Prerequisites

- [ ] Chapters already uploaded to NotebookLM (see [Uploading Chapters](guide-upload-notebooklm.md))
- [ ] Your notebook ID (from the summary table or `list` command)

## Step 1: Find Your Notebook ID

```bash
pdf-by-chapters list
```

This shows all your notebooks with their IDs and source counts.

## Step 2: See Available Chapters

```bash
pdf-by-chapters list -n NOTEBOOK_ID
```

Shows numbered chapters — use these numbers for the `-c` range.

## Step 3: Generate Overviews

Audio + video for chapters 1–3:

```bash
pdf-by-chapters generate -n NOTEBOOK_ID -c 1-3
```

Audio only (faster):

```bash
pdf-by-chapters generate -n NOTEBOOK_ID -c 1-3 --no-video
```

Video only:

```bash
pdf-by-chapters generate -n NOTEBOOK_ID -c 4-6 --no-audio
```

💡 Chapter range is **1-indexed** and **inclusive** — `-c 1-3` = chapters 1, 2, and 3.

## How Generation Works

```mermaid
sequenceDiagram
    participant You
    participant CLI
    participant NotebookLM

    You->>CLI: generate -n ID -c 1-3
    CLI->>NotebookLM: Select sources 1-3
    CLI->>NotebookLM: Request audio generation
    CLI->>NotebookLM: Request video generation
    Note over CLI,NotebookLM: Both requests fire concurrently
    loop Poll every 30s
        CLI->>NotebookLM: Check audio status
        CLI->>NotebookLM: Check video status
    end
    NotebookLM-->>CLI: Audio ready
    NotebookLM-->>CLI: Video ready
    CLI-->>You: Done!
```

## ⏱️ How Long Does It Take?

| Type | Default timeout | Typical wait |
|------|----------------|-------------|
| Audio + Video | 900s (15 min) | 5-15 min |

Both audio and video share a single `--timeout` flag (default 900s). Override with `-t`:

💡 Start with `--no-video` if you just want audio fast.

## Step 4: Download the Results

```bash
pdf-by-chapters download -n NOTEBOOK_ID -o ./overviews
```

```mermaid
flowchart LR
    A["generate\n(creates artifacts)"] --> B["download\n(fetches files)"]
    B --> C["📁 overviews/"]
    C --> D["audio_01.mp3"]
    C --> E["audio_02.mp3"]
    C --> F["video_01.mp4"]
```

## 💡 Suggested Chapter Groupings

| Goal | Range size | Example |
|------|-----------|---------|
| Deep understanding | 1–2 chapters | `-c 1-2` |
| Broad overview | 3–4 chapters | `-c 1-4` |
| Quick scan | 5+ chapters | `-c 1-6` |

Smaller ranges = more detailed overviews. Start small.

## Automated: Syllabus Workflow

Instead of manually choosing chapter ranges, let NotebookLM create a podcast syllabus that groups chapters into logical episodes.

### Step 1: Generate a Syllabus

```bash
pdf-by-chapters syllabus -n NOTEBOOK_ID -o ./chapters --no-video
```

This sends a prompt to NotebookLM's chat, asking it to group your chapters into 1-2 chapter episodes by topic. The result is saved as `syllabus_state.json`.

### Step 2: Generate Episodes One at a Time

```bash
# Non-blocking (returns immediately)
pdf-by-chapters generate-next -o ./chapters --no-wait

# Or blocking (waits for completion, Ctrl+C safe)
pdf-by-chapters generate-next -o ./chapters
```

### Step 3: Check Progress

```bash
pdf-by-chapters status -o ./chapters --poll
```

Use `--tail` for a live-updating display that polls every 30 seconds.

### Step 4: Repeat

Run `generate-next` again for the next episode. The tool automatically picks the next pending episode from the syllabus.

```mermaid
flowchart LR
    A[syllabus] --> B[generate-next]
    B --> C[status --poll]
    C --> D{All done?}
    D -->|No| B
    D -->|Yes| E[download]
```

> **Known behaviour:** The `syllabus` command uses NotebookLM's chat API (`chat.ask()`), which may trigger Google's backend to auto-generate artifacts (an audio overview and slide deck) as a platform side effect. These are separate from the scoped artifacts created by `generate-next` and can be safely ignored or deleted.

## ❌ Something Went Wrong?

See [Troubleshooting](troubleshooting.md) for:

- Generation timeout → try smaller ranges or audio-only
- Auth errors → re-run `notebooklm login`
- Download fails → artifact may not be ready yet
- Syllabus parsing failed → falls back to fixed-size chunks automatically
- Duplicate audio content → ensure `generate-next` is using scoped `source_ids`
