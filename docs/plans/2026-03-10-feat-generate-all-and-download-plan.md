---
title: "feat: Title Case naming, --all pipeline, --download flag"
type: feat
status: active
date: 2026-03-10
---

# feat: Title Case Naming, --all Pipeline, --download Flag

## Overview

Three enhancements to the syllabus-driven generation workflow:

1. **Title Case artifact naming** - Rename artifacts in NotebookLM using Title Case ("Setting The Stage") instead of the current lowercase/underscored output ("setting_the_stage") from `sanitize_filename()`
2. **`--all` flag** on `generate-next` - Auto-creates the syllabus if missing, then generates ALL episodes sequentially with exponential backoff retry on failures
3. **`--download` flag** on `generate-next` - Downloads completed audio artifacts to `<output_dir>/downloads/` with index-prefixed filenames (`01-setting_the_stage.mp3`)

## Problem Statement

Current issues observed in live testing:
- Artifacts renamed in NotebookLM show as `setting_the_stage` (lowercase, underscored) instead of readable "Setting The Stage" because `sanitize_filename()` lowercases everything
- Generating all episodes requires running `generate-next` manually for each episode
- Downloading syllabus-generated artifacts requires using the separate `download` command which doesn't know about episode ordering

## Proposed Solution

### 1. Title Case Naming

The rename operation currently uses `sanitize_filename(chunk.title)[:100]` which lowercases. Instead, create a new `title_case_name()` function that preserves capitalisation for NotebookLM display names (not filesystem paths).

```python
def title_case_name(name: str) -> str:
    """Clean a title for NotebookLM artifact display. Preserves Title Case."""
    name = re.sub(r"[^\w\s-]", "", name)
    name = " ".join(name.split())  # normalise whitespace to single spaces
    return name[:100].strip()
```

This is used ONLY for `client.artifacts.rename()` calls. Filesystem paths continue using `sanitize_filename()`.

### 2. `--all` Flag

Add `--all` / `-a` to `generate-next`. When set:

1. Check if `syllabus_state.json` exists. If not, auto-run the syllabus generation (requires `-n NOTEBOOK_ID`)
2. Loop through all episodes in order:
   - Fire generation for the next pending episode (`--no-wait` internally)
   - Poll until complete
   - On failure: delete the failed artifact, wait with exponential backoff, retry
   - Retry schedule: 1 min, 3 min, 5 min, then stop
   - On success: move to next episode
3. Display progress table between episodes

**Retry with deletion flow:**
```
Attempt 1: generate -> fail -> delete artifact -> wait 60s
Attempt 2: generate -> fail -> delete artifact -> wait 180s
Attempt 3: generate -> fail -> delete artifact -> wait 300s
Attempt 4: generate -> fail -> delete artifact -> STOP (error)
```

The delete step uses the task_id (which equals artifact_id in notebooklm-py) to remove the failed artifact before retrying. This prevents orphaned failed artifacts.

### 3. `--download` Flag

Add `--download` / `-d` to `generate-next`. When set (typically combined with `--all`):

After each episode completes successfully, download the audio artifact to `<output_dir>/downloads/` with naming: `{NN}-{sanitized_title}.mp3`

Example output:
```
downloads/
  01-setting_the_stage.mp3
  02-defining_the_role_and_the_lifecycle.mp3
  03-architecture_and_technology_choices.mp3
  ...
```

The index `NN` is the episode number from the syllabus, zero-padded to 2 digits.

## Technical Approach

### Files to modify

| File | Change |
|------|--------|
| `src/pdf_by_chapters/syllabus.py` | Add `title_case_name()` function |
| `src/pdf_by_chapters/notebooklm.py` | Use `title_case_name()` for renames; add `delete_artifact()` and `download_episode_audio()` functions |
| `src/pdf_by_chapters/cli.py` | Add `--all` and `--download` flags to `generate-next`; implement the pipeline loop |
| `tests/unit/test_syllabus.py` | Tests for `title_case_name()` |
| `tests/unit/test_notebooklm.py` | Tests for new async functions |
| `tests/unit/test_cli.py` | Tests for `--all` and `--download` flags |

### New functions

**`syllabus.py`:**
```python
def title_case_name(name: str) -> str:
    """Clean a title for NotebookLM artifact display. Preserves Title Case."""
```

**`notebooklm.py`:**
```python
async def delete_artifact(
    client: NotebookLMClient,
    notebook_id: str,
    artifact_id: str,
) -> None:
    """Delete an artifact by ID. Best-effort, logs warning on failure."""

async def download_episode_audio(
    client: NotebookLMClient,
    notebook_id: str,
    artifact_id: str,
    output_path: Path,
) -> None:
    """Download a single audio artifact to the specified path."""
```

### CLI changes to `generate-next`

```python
@app.command("generate-next", rich_help_panel="Syllabus")
def generate_next(
    output_dir: Path = ...,
    episode: int | None = ...,
    no_audio: bool = ...,
    no_video: bool = ...,
    no_wait: bool = ...,
    timeout: int = ...,
    all_episodes: bool = typer.Option(
        False, "--all", "-a",
        help="Generate all episodes sequentially with retry.",
    ),
    download: bool = typer.Option(
        False, "--download", "-d",
        help="Download audio after each completed episode.",
    ),
    notebook_id: str | None = typer.Option(
        None, "--notebook-id", "-n", envvar="NOTEBOOK_ID",
        help="Notebook ID (required with --all if no syllabus exists).",
    ),
) -> None:
```

### `--all` pipeline pseudocode

```python
if all_episodes:
    # Auto-create syllabus if missing
    if not state_path.is_file():
        if not notebook_id:
            error("--all requires -n NOTEBOOK_ID when no syllabus exists")
        # run syllabus generation inline
        ...

    state = read_state(state_path)
    retry_waits = [60, 180, 300]  # seconds

    for chunk in sorted(state.chunks.values(), key=lambda c: c.episode):
        if chunk.status == ChunkStatus.COMPLETED:
            if download:
                _download_episode(chunk, ...)
            continue

        for attempt in range(len(retry_waits) + 1):
            # Fire generation
            tasks = start_chunk_generation(...)
            # Save task_ids
            # Poll to completion
            ...

            if chunk.status == ChunkStatus.COMPLETED:
                if download:
                    _download_episode(chunk, ...)
                break
            else:
                # Delete failed artifact
                delete_artifact(client, notebook_id, task_id)
                if attempt < len(retry_waits):
                    wait_secs = retry_waits[attempt]
                    console.print(f"Retrying in {wait_secs}s...")
                    time.sleep(wait_secs)
                else:
                    console.print("Failed after all retries. Stopping.")
                    raise typer.Exit(1)
```

## Acceptance Criteria

- [ ] Artifacts renamed in NotebookLM use Title Case ("Setting The Stage")
- [ ] `sanitize_filename()` still used for filesystem paths (unchanged)
- [ ] `--all` creates syllabus if missing (requires `-n`)
- [ ] `--all` generates all episodes sequentially
- [ ] `--all` retries with exponential backoff (60s, 180s, 300s) on failure
- [ ] `--all` deletes failed artifacts before retrying
- [ ] `--all` stops after 4 failed attempts on same episode
- [ ] `--download` creates `<output_dir>/downloads/` directory
- [ ] `--download` names files as `{NN}-{sanitized_title}.mp3` (e.g. `01-setting_the_stage.mp3`)
- [ ] `--download` works both standalone and with `--all`
- [ ] Existing `generate-next` behaviour unchanged when flags not used

## Commit Strategy

1. `feat: add title_case_name for artifact display names`
2. `feat: add --all flag for full pipeline generation`
3. `feat: add --download flag for episode audio download`
