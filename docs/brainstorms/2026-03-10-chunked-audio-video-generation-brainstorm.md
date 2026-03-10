# Brainstorm: Chunked Audio/Video Generation via Auto-Syllabus

**Date:** 2026-03-10
**Status:** Draft

## What We're Building

A workflow that automates generating NotebookLM audio/video overviews for an entire book, broken into logical chapter chunks. The tool:

1. Sends a "syllabus generator" prompt to NotebookLM's chat API, scoped to all uploaded chapter sources
2. Parses the response into a numbered chunk plan (episode title + chapter numbers per chunk)
3. Persists the plan as a JSON state file alongside the chapter PDFs
4. Lets the user step through chunk generation one-at-a-time via a `generate-next` command
5. Renames each completed artifact in NotebookLM using the syllabus episode title
6. Tracks progress across sessions so the user can resume at any time

### Why This Approach

- **Auto-syllabus via chat**: NotebookLM's AI has read all the chapter sources and can group them by related concepts (1-2 chapters per chunk). This produces smarter groupings than fixed-size chunking (e.g. it won't split a two-part chapter across chunks).
- **Stateful stepping over batch**: NotebookLM has rate limits and quota constraints. Audio/video generation takes minutes per chunk. A fire-and-forget batch risks hitting rate limits mid-run with no easy recovery. Stateful stepping lets the user control pacing, walk away, and resume later.
- **JSON state file**: Simple, inspectable, portable. Saved alongside chapter PDFs so it gets cleaned up naturally with the output directory.
- **Episode title naming**: Each artifact gets renamed in NotebookLM's UI to the syllabus-generated episode title (e.g. "Foundations & The Data Engineering Lifecycle"). More meaningful than `<book>-1`, `-2` numbering, and visible in the NotebookLM web UI.

## Key Decisions

### 1. Chunk Definition: Auto-Syllabus via NotebookLM Chat

The tool sends a structured prompt to `client.chat.ask()` requesting a numbered syllabus with strict 1-2 chapter limits per chunk. The prompt requests a specific format to make parsing reliable:

```
Episode N: "<Episode Title>"
Chapters: X-Y
Summary: ...
```

**Fallback**: If parsing fails (regex can't extract structured chunks), fall back to fixed-size chunks of 2 chapters each and warn the user. The user can also manually edit the JSON state file to adjust groupings before running `generate-next`.

### 2. Execution Model: Stateful Next-Chunk Stepping

- `syllabus` command creates the plan and saves state
- `generate-next` reads state, generates the next pending chunk, updates state
- User controls when to invoke each step (accommodates rate limits, quotas, time)
- State file tracks: notebook_id, book_name, chunks[], per-chunk status + artifact_ids

### 3. State Persistence: JSON File Alongside Chapters

```json
{
  "notebook_id": "decbc8d1-...",
  "book_name": "Fundamentals_of_Data_Engineering_Joe_Reis",
  "created": "2026-03-10T14:52:00Z",
  "chunks": [
    {
      "episode": 1,
      "title": "Foundations & The Data Engineering Lifecycle",
      "chapters": [1, 2],
      "source_ids": ["abc-123", "def-456"],
      "status": "completed",
      "artifacts": {
        "audio": {"task_id": "...", "artifact_id": "...", "status": "completed"},
        "video": {"task_id": "...", "artifact_id": "...", "status": "completed"}
      }
    },
    {
      "episode": 2,
      "title": "Designing Good Data Architecture",
      "chapters": [3, 4],
      "source_ids": ["ghi-789", "jkl-012"],
      "status": "pending",
      "artifacts": {}
    }
  ]
}
```

File location: `<output_dir>/syllabus_state.json`

### 4. Artifact Scope: Audio and Video Only

Matches the existing `generate` command's capabilities. The upstream library supports many more artifact types (quizzes, flashcards, reports, etc.) but we're keeping scope tight. Can be extended later.

### 5. Naming Convention: Episode Title from Syllabus

After an artifact completes generation, the tool calls `client.artifacts.rename()` to set the title to the syllabus episode title. This makes artifacts identifiable in the NotebookLM web UI.

For downloaded files, the naming convention is: `<book_stem>_episode_<N>_<type>.<ext>`
e.g. `fundamentals_of_data_engineering_episode_01_audio.mp3`

### 6. CLI Commands: New Top-Level Commands

Three new commands added to the flat command structure:

| Command | Purpose |
|---------|---------|
| `syllabus` | Generate a chunk plan via NotebookLM chat, save to state file |
| `generate-next` | Generate audio/video for the next pending chunk |
| `status` | Show chunk plan with per-chunk generation progress |

Existing commands (`split`, `process`, `generate`, `download`, `delete`, `list`) remain unchanged.

## Workflow Example

```bash
# Step 1: Split and upload (existing)
pdf-by-chapters process ./Fundamentals_of_Data_Engineering.pdf
export NOTEBOOK_ID=decbc8d1-...

# Step 2: Generate syllabus
pdf-by-chapters syllabus -n $NOTEBOOK_ID -o ./chapters
# -> Sends prompt to NotebookLM chat
# -> Parses response into chunks
# -> Saves ./chapters/syllabus_state.json
# -> Displays the syllabus table

# Step 3: Generate chunks one at a time
pdf-by-chapters generate-next -o ./chapters
# -> Reads state, finds chunk 1
# -> Generates audio + video for chapters 1-2
# -> Polls until complete
# -> Renames artifacts to episode title
# -> Updates state file
# -> Warns: "Rate limits apply. Wait before generating next chunk."

# Step 4: Check progress
pdf-by-chapters status -o ./chapters
# -> Shows table: Episode | Title | Chapters | Audio | Video

# Step 5: Generate next chunk when ready
pdf-by-chapters generate-next -o ./chapters
# -> Picks up chunk 2 automatically

# Step 6: Download all completed artifacts
pdf-by-chapters download -n $NOTEBOOK_ID -o ./overviews
```

## Technical Integration Points

### notebooklm.py additions
- `generate_syllabus()` - sends chat prompt, parses response, returns chunk plan
- `generate_next_chunk()` - reads state, generates artifacts for next pending chunk, renames on completion
- Reuses existing `_request_chapter_artifact()` for the actual generation
- Reuses existing polling logic from `generate_for_chapters()`

### cli.py additions
- `syllabus` command - orchestrates syllabus generation, displays plan table
- `generate-next` command - orchestrates next chunk generation, displays progress
- `status` command - reads state file, displays progress table

### New module: syllabus.py (optional)
- Syllabus prompt template
- Response parsing (regex-based)
- State file read/write
- Fixed-size fallback logic

Could also live in `notebooklm.py` if the module doesn't get too large.

## Resolved Questions

1. **Syllabus prompt design**: Include source titles in the prompt. The tool lists all uploaded sources by number and title, embedding them in the prompt so the LLM has an explicit chapter-to-number mapping. This makes the response easier to parse and reduces ambiguity.

2. **Source ID mapping**: Parse chapter numbers from source titles using regex (e.g. `chapter_03` -> 3) rather than relying on alphabetical sort position. Falls back to positional sort if title parsing fails. More robust against out-of-order uploads or extra sources.

3. **Regeneration**: Yes - `generate-next` supports a `--episode N` flag to target a specific chunk. Resets that chunk's status to pending and regenerates. Useful for retries after failures or getting a different take.

4. **Chunk size override**: Yes - `syllabus` accepts `--max-chapters N` (default 2) to constrain the LLM's grouping. The prompt template interpolates this value. Useful for shorter books where 3-4 chapters per chunk makes more sense.

## Open Questions

None - all questions resolved during brainstorm.
