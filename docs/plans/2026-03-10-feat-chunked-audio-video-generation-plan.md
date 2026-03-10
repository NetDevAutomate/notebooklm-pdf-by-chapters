---
title: "feat: Chunked Audio/Video Generation via Auto-Syllabus"
type: feat
status: active
date: 2026-03-10
origin: docs/brainstorms/2026-03-10-chunked-audio-video-generation-brainstorm.md
deepened: 2026-03-10
---

# feat: Chunked Audio/Video Generation via Auto-Syllabus

## Enhancement Summary

**Deepened on:** 2026-03-10
**Research agents used:** Python reviewer, Architecture strategist, Code simplicity reviewer, Pattern recognition specialist, Best practices researcher, Security sentinel, Python testing patterns

### Key Improvements from Research
1. **Extract `models.py`** -- shared dataclasses move to a dedicated module, preserving the leaf-module independence pattern and keeping `syllabus.py` testable without `notebooklm-py`
2. **Dependency-inject the client** -- async functions accept the client as a parameter instead of opening their own context; caller owns the lifecycle
3. **Use `StrEnum` for chunk status** -- type safety via `ChunkStatus(StrEnum)` instead of bare strings
4. **Use `dict[int, SyllabusChunk]`** internally for O(1) episode lookup; serialize as list in JSON
5. **Sanitize all LLM-derived strings** -- episode titles MUST pass through `sanitize_filename()` before filesystem or API use

### Scope Reductions (YAGNI)
1. **CUT Phase 4** (download --syllabus integration) -- over-coupling; add later if manual renaming proves painful
2. **CUT `validate_source_ids()`** -- the API already returns clear errors when source IDs are stale
3. **CUT state file version field** -- for a personal tool, re-run `syllabus --force` on schema changes
4. **CUT partial-parse-repair** -- binary success/fallback only; no "some chapters parsed, append rest as fixed-size"
5. **SIMPLIFY to 4 chunk states** -- derive "partial" from per-artifact data at display time, don't store it
6. **SIMPLIFY `book_name`** -- default to `output_dir.name`, accept `--book-name` CLI override; no extra API call

---

## Overview

Add a syllabus-driven workflow for generating NotebookLM audio/video overviews across an entire book, broken into logical chapter chunks. Three new CLI commands (`syllabus`, `generate-next`, `status`) and two new modules (`models.py`, `syllabus.py`) enable: auto-generating a chunk plan via NotebookLM's chat API, stepping through generation one chunk at a time with persistent state, and tracking progress across sessions.

## Problem Statement / Motivation

When a 19-chapter book is uploaded to NotebookLM, generating audio/video overviews requires:
1. Manually deciding which chapters to group into each episode
2. Running `pdf-by-chapters generate -c 1-2`, then `-c 3-4`, then `-c 5-6`... N times
3. Tracking which ranges are done, which failed, which need retrying
4. Waiting between each invocation due to rate limits and generation time

This is tedious, error-prone, and breaks across sessions. The feature automates the chunking decision (via NotebookLM's AI), persists progress, and lets the user step through generation at their own pace.

## Proposed Solution

### Architecture

```
                          +-----------------+
                          |    cli.py       |  3 new commands
                          | syllabus        |  (presentation layer)
                          | generate-next   |
                          | status          |
                          +--------+--------+
                                   |
                    +--------------+-----------+
                    |              |           |
             +------+------+ +----+----+ +----+------+
             | syllabus.py | |models.py| |notebooklm |
             | (new)       | | (new)   | |.py (ext)  |
             +-------------+ +---------+ +-----------+
             | prompt tmpl  | UploadRes | create_     |
             | parse resp   | NbInfo    |  syllabus() |
             | state r/w    | SourceInfo| _poll_until |
             | fixed fallbk | ChunkRes  |  _complete()|
             | src mapping  |           |             |
             +------+------+ +----+----+ +-----+-----+
                    |              ^             |
                    +--------------+-------------+
                                   |
                         +---------+---------+
                         | syllabus_state.json|
                         +-------------------+
```

**Key architectural change from original plan:** Extract `models.py` to hold all shared dataclasses (`UploadResult`, `NotebookInfo`, `SourceInfo` moved from `notebooklm.py`, plus new `ChunkResult`). This preserves the leaf-module invariant -- both `syllabus.py` and `notebooklm.py` import from `models.py`, neither imports from each other. `syllabus.py` remains testable without `notebooklm-py` installed. (See Architecture strategist review.)

### New Module: `src/pdf_by_chapters/models.py`

Shared dataclasses extracted from `notebooklm.py`:
- `UploadResult` (moved)
- `NotebookInfo` (moved)
- `SourceInfo` (moved)
- `ChunkResult` (new -- replaces raw `dict[str, str]` return type)

### New Module: `src/pdf_by_chapters/syllabus.py`

Pure logic module (no Rich, no Typer, no async). Follows the `splitter.py` pattern:
- `ChunkStatus(StrEnum)` -- `PENDING`, `GENERATING`, `COMPLETED`, `FAILED`
- Dataclasses: `ChunkArtifact`, `SyllabusChunk`, `SyllabusState`
- `SyllabusState.chunks` is `dict[int, SyllabusChunk]` internally (O(1) lookup), serialized as list
- Prompt template, response parsing, fixed-size fallback, state I/O, source mapping
- Raises `ValueError` / custom exceptions for errors; CLI catches and translates to red output + `typer.Exit(1)`

### Extended: `src/pdf_by_chapters/notebooklm.py`

Two new async functions that **accept the client as a parameter** (dependency injection):
- `create_syllabus(client, notebook_id, prompt) -> str` -- sends chat prompt, returns raw AI response
- `generate_chunk(client, notebook_id, source_ids, ...) -> ChunkResult` -- generates audio/video, polls to completion, renames artifacts (best-effort)

Shared polling logic extracted from existing `generate_for_chapters()`:
- `_poll_until_complete(client, notebook_id, tasks, timeout)` -- reusable poll loop, eliminates duplication

### Extended: `src/pdf_by_chapters/cli.py`

Three new `@app.command()` functions with `rich_help_panel="Syllabus"` for visual grouping in `--help`.

## Technical Approach

### Chunk Status State Machine

```
pending ──> generating ──> completed
                │
                └──> failed ──> (user runs generate-next) ──> generating
```

4 states (not 5). "Partial completion" (audio done, video failed) is derived at display time from per-artifact statuses. `generate-next` inspects artifact-level data to retry only the failed type.

```python
class ChunkStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
```

`generate-next` auto-selects: first `GENERATING` chunk (resume interrupted), then first `FAILED` chunk (retry), then first `PENDING` chunk (new work).

### State File Schema (`syllabus_state.json`)

```json
{
  "notebook_id": "decbc8d1-951e-4ab1-9275-23b4714a6b2b",
  "book_name": "Fundamentals_of_Data_Engineering",
  "created": "2026-03-10T14:52:00Z",
  "max_chapters": 2,
  "generate_audio": true,
  "generate_video": true,
  "chunks": [
    {
      "episode": 1,
      "title": "Foundations & The Data Engineering Lifecycle",
      "chapters": [1, 2],
      "source_ids": ["abc-123", "def-456"],
      "status": "completed",
      "artifacts": {
        "audio": {"task_id": "xxx", "status": "completed"},
        "video": {"task_id": "yyy", "status": "completed"}
      }
    }
  ]
}
```

Design decisions:
- **No version field** -- YAGNI for a personal tool. If schema changes, re-run `syllabus --force`. (See Simplicity review.)
- **`generate_audio`/`generate_video` flags** captured at syllabus time, overridable per-invocation on `generate-next`
- **Artifacts track `task_id`** (same as `artifact_id` in notebooklm-py) and per-type status
- **Atomic writes**: `tempfile.mkstemp(dir=state_path.parent)` + `os.fsync()` + `os.replace()`. Temp file in same directory ensures same-filesystem for POSIX atomicity. Cleanup temp on failure. (See Best practices research.)
- **Chunks stored as list in JSON** but loaded into `dict[int, SyllabusChunk]` keyed by episode for O(1) access

### Deserialization Validation

State file loaded via `SyllabusState.from_json()` classmethod with structural validation:

```python
@classmethod
def from_json(cls, data: dict[str, Any]) -> SyllabusState:
    """Load state from parsed JSON with structural validation."""
    try:
        chunks_list = [SyllabusChunk.from_json(c) for c in data["chunks"]]
    except (KeyError, TypeError) as exc:
        raise SyllabusStateError(f"Corrupt state file: {exc}") from exc
    return cls(
        notebook_id=data["notebook_id"],
        book_name=data["book_name"],
        chunks={c.episode: c for c in chunks_list},
        ...
    )
```

Custom exceptions in `syllabus.py`: `SyllabusParseError`, `SyllabusStateError`. CLI catches these and translates to `console.print("[red]...") + typer.Exit(1)`.

### Syllabus Prompt Design

The prompt is sent to `client.chat.ask(notebook_id, question, source_ids=all_source_ids)` and includes the numbered source titles for reliable mapping:

```
I have uploaded several sources, each representing a sequential chapter
from a single technical eBook. Here are the chapters:

1. fundamentals_of_data_engineering_chapter_01_preface.pdf
2. fundamentals_of_data_engineering_chapter_02_foundation_and_building_blocks.pdf
...

Please divide these chapters into a "Podcast Syllabus" consisting of
logical chunks. Strictly limit each chunk to at most {max_chapters}
chapters. Group them by related technical concepts.

Format your response EXACTLY as follows, one entry per chunk:

Episode 1: "Episode Title Here"
Chapters: 1, 2
Summary: One or two sentence summary.

Episode 2: "Episode Title Here"
Chapters: 3
Summary: One or two sentence summary.

Use ONLY the chapter numbers listed above. Output ONLY the syllabus.
```

### Parsing Strategy

Named regex constant with comment:

```python
# Matches: Episode 1: "Title Here"\nChapters: 1, 2\nSummary: ...
_EPISODE_RE = re.compile(
    r'Episode\s+(\d+):\s*"([^"]+)"\s*\n'
    r'Chapters?:\s*([\d,\s]+)\s*\n'
    r'Summary:\s*(.+)',
    re.IGNORECASE,
)
```

**Binary success/fallback** (no partial-parse-repair):
- If regex extracts episodes AND every chapter number appears in at least one episode: **accept**
- Otherwise: fall back entirely to fixed-size chunks, log raw response at DEBUG level, warn user

ReDoS risk: **none** -- `[\d,\s]+` and `[^"]+` are non-overlapping with their delimiters. Confirmed safe by security review.

### Source ID Mapping

Parse chapter number from source title: `r'chapter_(\d+)'` (case-insensitive).

All-or-nothing: if ANY source title fails to parse, fall back to positional sort for ALL sources.

**Decoupling from notebooklm.py**: `map_sources_to_chapters()` accepts `list[tuple[str, str]]` (id, title pairs) not `list[SourceInfo]`. The CLI extracts the tuples before calling. This keeps `syllabus.py` independent of `notebooklm-py`. (See Pattern recognition review.)

### Security: LLM Output Sanitization

Episode titles from LLM output are **adversarial input** (could contain path traversal, shell metacharacters, or Unicode control characters via indirect prompt injection from uploaded PDFs).

**Mandatory mitigations** (see Security sentinel Finding 6):
1. Pass ALL LLM-derived episode titles through `sanitize_filename()` before any filesystem or API use
2. Truncate to 100 characters before API rename calls
3. After constructing any file path, validate it resolves under `output_dir`:
   ```python
   full_path = (output_dir / filename).resolve()
   if not str(full_path).startswith(str(output_dir.resolve())):
       raise ValueError(f"Path traversal detected: {filename}")
   ```

### Async Function Design

**Client as parameter, not owned** (see Python reviewer):

```python
# Caller owns the client lifecycle
async def create_syllabus(
    client: NotebookLMClient,
    notebook_id: str,
    prompt: str,
) -> str:
    """Send syllabus prompt to NotebookLM chat. Returns raw AI response."""

async def generate_chunk(
    client: NotebookLMClient,
    notebook_id: str,
    source_ids: list[str],
    episode_title: str,
    generate_audio: bool = True,
    generate_video: bool = True,
    timeout: int = 900,
) -> ChunkResult:
    """Generate audio/video for a chunk, poll to completion, rename artifacts."""
```

CLI wraps with a single `asyncio.run()` call that owns the client context:

```python
async def _run_generate_next(state: SyllabusState, chunk: SyllabusChunk, ...) -> ...:
    async with await NotebookLMClient.from_storage() as client:
        result = await generate_chunk(client, state.notebook_id, ...)
    return result

asyncio.run(_run_generate_next(...))
```

### Shared Polling Loop

Extract from existing `generate_for_chapters()` to avoid duplicating ~40 lines:

```python
async def _poll_until_complete(
    client: NotebookLMClient,
    notebook_id: str,
    tasks: dict[str, str],  # {label: task_id}
    timeout: int = 900,
    poll_interval: int = 30,
) -> dict[str, str]:
    """Poll artifact generation tasks until complete or timeout.

    Returns {label: "completed"|"failed"}.
    """
```

Both `generate_for_chapters()` and `generate_chunk()` call this shared helper.

### SpecFlow Gap Resolutions

| Gap | Resolution |
|-----|-----------|
| **State file overwrite** | Refuse if any chunk status != "pending". Add `--force` flag to override. |
| **Partial completion** | Track audio/video independently at artifact level. Chunk-level status is `FAILED` if any artifact failed. `generate-next` retries only failed artifact types. |
| **Atomic writes** | `tempfile.mkstemp(dir=parent)` + `os.fsync()` + `os.replace()`. Cleanup temp on failure. |
| **Stale source_ids** | ~~Pre-validate~~ CUT. API returns clear errors. |
| **Rename failure** | Best-effort. Log warning, mark chunk as completed regardless. |
| **All completed** | Print "All N episodes completed. Use --episode N to regenerate a specific one." Exit 0. |
| **--no-audio/--no-video** | Supported on `generate-next` with `help=` text matching existing `generate` command. |
| **--timeout** | Supported on `generate-next`. Default 900s, matching existing `generate`. |
| **--episode N out of range** | Error: "Episode N not found. Syllabus has episodes 1-M." |
| **--episode N regeneration** | Resets chunk status to pending. Warns about orphaned artifacts. Does not delete. |
| **No state file** | Clear error: "No syllabus found. Run `pdf-by-chapters syllabus` first." |
| **Download integration** | ~~Phase 4~~ CUT. Add later if manual renaming proves painful. |
| **book_name** | Defaults to `output_dir.name`. Accept `--book-name` CLI override. No API call. |
| **Concurrency** | Document unsupported. No file locking. |

## Implementation Phases

### Phase 0: Extract shared models (`models.py`)

**New file:** `src/pdf_by_chapters/models.py`

Move from `notebooklm.py`:
- `UploadResult`, `NotebookInfo`, `SourceInfo`

Add new:
- `ChunkResult` dataclass (replaces `dict[str, str]` return type)

Update imports in `notebooklm.py` and `cli.py`. Update test imports.

This is a pure refactoring commit -- no behavior change, all tests pass.

### Phase 1: State Management Foundation (`syllabus.py`)

**New file:** `src/pdf_by_chapters/syllabus.py`

Deliverables:
- `ChunkStatus(StrEnum)` -- 4 states
- Dataclasses: `ChunkArtifact`, `SyllabusChunk`, `SyllabusState` with `to_json()`/`from_json()` methods
- `SyllabusState.chunks` as `dict[int, SyllabusChunk]`, serialized as list
- Custom exceptions: `SyllabusParseError`, `SyllabusStateError`
- `SYLLABUS_PROMPT_TEMPLATE` -- named constant
- `_EPISODE_RE` -- named regex constant with comment
- `parse_syllabus_response(response: str, source_map: dict[int, str]) -> dict[int, SyllabusChunk]`
- `build_fixed_size_chunks(source_map: dict[int, str], max_chapters: int) -> dict[int, SyllabusChunk]`
- `map_sources_to_chapters(sources: list[tuple[str, str]]) -> dict[int, str]` -- accepts (id, title) tuples
- `read_state(state_path: Path) -> SyllabusState` -- validate structure on load
- `write_state(state: SyllabusState, state_path: Path) -> None` -- atomic write with fsync
- `get_next_chunk(state: SyllabusState) -> SyllabusChunk | None` -- priority: generating > failed > pending
- `STATE_FILENAME = "syllabus_state.json"`

**Test file:** `tests/unit/test_syllabus.py`

Tests (heavy use of `pytest.mark.parametrize`):
- `TestParseSyllabusResponse` -- clean parse, zero parse (fallback), preamble text, unicode titles, empty string, whitespace-only
- `TestBuildFixedSizeChunks` -- even/odd splits, single chapter, chunk_size > total, chunk_size=0 raises ValueError
- `TestMapSourcesToChapters` -- standard format, case-insensitive, no-match (fallback), duplicates, empty list
- `TestReadWriteState` -- round-trip, atomic write (.tmp cleanup), corrupt JSON, missing keys
- `TestGetNextChunk` -- priority ordering, all completed returns None, generating takes priority over failed

### Phase 2: NotebookLM Integration (`notebooklm.py`)

**Additions to** `src/pdf_by_chapters/notebooklm.py`:

```python
async def create_syllabus(
    client: NotebookLMClient,
    notebook_id: str,
    prompt: str,
) -> str:
    """Send syllabus prompt to NotebookLM chat. Returns raw AI response."""

async def _poll_until_complete(
    client: NotebookLMClient,
    notebook_id: str,
    tasks: dict[str, str],
    timeout: int = 900,
    poll_interval: int = 30,
) -> dict[str, str]:
    """Shared polling loop for artifact generation. Returns {label: status}."""

async def generate_chunk(
    client: NotebookLMClient,
    notebook_id: str,
    source_ids: list[str],
    episode_title: str,
    generate_audio: bool = True,
    generate_video: bool = True,
    timeout: int = 900,
) -> ChunkResult:
    """Generate audio/video for a chunk, poll to completion, rename artifacts (best-effort)."""
```

Refactor existing `generate_for_chapters()` to use `_poll_until_complete()` (DRY).

**Updates to** `tests/conftest.py`:
- Add `client.chat.ask` as `AsyncMock` to `mock_notebooklm_client`
- Add `client.artifacts.rename` as `AsyncMock`

**Test additions in** `tests/unit/test_notebooklm.py`:
- `TestCreateSyllabus` -- sends prompt, returns answer, handles empty response
- `TestGenerateChunk` -- happy path, one artifact fails, rename failure (best-effort), timeout
- `TestPollUntilComplete` -- all complete, one fails, timeout

### Phase 3: CLI Commands (`cli.py`)

Three new commands with `rich_help_panel="Syllabus"`:

#### `syllabus` command

```python
@app.command(rich_help_panel="Syllabus")
def syllabus(
    notebook_id: str | None = typer.Option(
        None, "--notebook-id", "-n", envvar="NOTEBOOK_ID",
        help="Notebook ID to generate syllabus for.",
    ),
    output_dir: Path = typer.Option(Path("./chapters"), "--output-dir", "-o"),
    max_chapters: int = typer.Option(2, "--max-chapters", "-m",
        help="Maximum chapters per episode (default: 2).",
    ),
    book_name: str | None = typer.Option(None, "--book-name", "-b",
        help="Book name for state file. Defaults to output directory name.",
    ),
    force: bool = typer.Option(False, "--force",
        help="Overwrite existing syllabus even if chunks are in progress.",
    ),
    no_audio: bool = typer.Option(False, "--no-audio",
        help="Skip audio generation.",
    ),
    no_video: bool = typer.Option(False, "--no-video",
        help="Skip video generation.",
    ),
) -> None:
```

All imports lazy (inside function body). Catches `SyllabusParseError`/`SyllabusStateError` and translates to `console.print("[red]...") + typer.Exit(1)`.

#### `generate-next` command

```python
@app.command("generate-next", rich_help_panel="Syllabus")
def generate_next(
    output_dir: Path = typer.Option(Path("./chapters"), "--output-dir", "-o"),
    episode: int | None = typer.Option(None, "--episode", "-e",
        help="Target a specific episode by number.",
    ),
    no_audio: bool = typer.Option(False, "--no-audio",
        help="Skip audio generation.",
    ),
    no_video: bool = typer.Option(False, "--no-video",
        help="Skip video generation.",
    ),
    timeout: int = typer.Option(900, "--timeout", "-t",
        help="Timeout in seconds (default: 900 = 15min).",
    ),
) -> None:
    """Generate audio/video for the next pending episode.

    Uses notebook_id from the syllabus state file (not --notebook-id).
    """
```

#### `status` command

```python
@app.command(rich_help_panel="Syllabus")
def status(
    output_dir: Path = typer.Option(Path("./chapters"), "--output-dir", "-o"),
) -> None:
```

**Test additions in** `tests/unit/test_cli.py`:
- `TestSyllabusCommand` -- happy path, force overwrite, existing state refusal, no sources
- `TestGenerateNextCommand` -- happy path, --episode targeting, no state file, all completed
- `TestStatusCommand` -- happy path, no state file

### Phase 4: Documentation

- Update `docs/guide-generate-overviews.md` with syllabus workflow
- Update `docs/guide-study-workflow.md` with end-to-end example
- Update `docs/codemap.md` with new modules (`models.py`, `syllabus.py`)

## Acceptance Criteria

### Core Functionality
- [ ] `syllabus` generates valid state file for a multi-chapter book
- [ ] `syllabus` refuses to overwrite non-pending state without `--force`
- [ ] `syllabus` falls back to fixed-size chunks when chat response is unparseable
- [ ] `syllabus --max-chapters N` constrains chunk sizes in the prompt
- [ ] `generate-next` processes one chunk and updates state file atomically
- [ ] `generate-next` resumes correctly after process interruption (chunk left in "generating")
- [ ] `generate-next` retries only failed artifact types on partial completion
- [ ] `generate-next --episode N` targets a specific episode
- [ ] `generate-next` renames artifacts in NotebookLM (best-effort, non-blocking)
- [ ] `generate-next` prints clear message when all episodes are completed
- [ ] `status` displays correct progress table with per-artifact status
- [ ] All LLM-derived episode titles pass through `sanitize_filename()` before filesystem/API use

### Error Handling
- [ ] Missing state file produces clear error with remedy
- [ ] Invalid `--episode N` (out of range) produces clear error
- [ ] Rate-limited generation detected and reported to user
- [ ] Corrupt state file produces clear error via `SyllabusStateError` (not a traceback)
- [ ] `syllabus.py` raises exceptions; `cli.py` catches and translates to `[red]` + `typer.Exit(1)`

### Testing
- [ ] Syllabus parsing: parametrized across clean, zero (fallback), edge cases
- [ ] Source mapping: parametrized across parseable, unparseable (fallback), empty
- [ ] State management: round-trip, atomic writes (verify .tmp cleanup), corruption
- [ ] CLI commands: all happy paths + key error paths via CliRunner (classes named `Test*Command`)
- [ ] Async functions: mocked notebooklm-py client with `chat.ask` and `artifacts.rename`
- [ ] Pure logic in `syllabus.py` tested without mocks (mock-free majority)

## Dependencies & Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| NotebookLM chat response format changes | Medium | High | Fixed-size fallback auto-activates. User can edit state JSON. |
| Rate limiting blocks sequential generation | High | Medium | Stateful stepping by design. User controls pacing. |
| `notebooklm-py` API changes | Low | High | Pin minimum version. Wrap API calls with try/except. |
| Prompt produces poor chapter groupings | Medium | Low | User can edit state file. `--force` allows re-running. |
| Path traversal via LLM episode titles | Medium | High | `sanitize_filename()` + path containment check. |
| State file corruption from Ctrl+C | Low | Medium | Atomic writes with fsync. |

## Sources & References

### Origin

- **Brainstorm document:** [docs/brainstorms/2026-03-10-chunked-audio-video-generation-brainstorm.md](docs/brainstorms/2026-03-10-chunked-audio-video-generation-brainstorm.md) -- Key decisions: auto-syllabus via chat, stateful next-chunk stepping, JSON state file, episode title naming in NotebookLM, audio/video only scope.

### Internal References

- CLI patterns: `src/pdf_by_chapters/cli.py` -- Typer conventions, async wrapping, lazy imports
- API integration: `src/pdf_by_chapters/notebooklm.py` -- client context manager, polling, `_request_chapter_artifact()`
- Module pattern: `src/pdf_by_chapters/splitter.py` -- pure logic module template
- Filename sanitization: `src/pdf_by_chapters/splitter.py:sanitize_filename()` -- MUST be used on all LLM output
- Test fixtures: `tests/conftest.py` -- `mock_notebooklm_client`, `patch_notebooklm`

### External References

- notebooklm-py Chat API: `client.chat.ask(notebook_id, question, source_ids=...)` returns `AskResult`
- notebooklm-py Artifacts API: `generate_audio()`, `generate_video()`, `rename()`, `poll_status()`
- notebooklm-py Types: `AskResult`, `GenerationStatus` (with `is_rate_limited`), `AudioFormat`, `VideoStyle`

### Commit Strategy

4 logical commits matching the phases:
1. `refactor: extract shared dataclasses to models.py` (Phase 0)
2. `feat: add syllabus state management module` (Phase 1 + tests)
3. `feat: add syllabus chat and chunk generation functions` (Phase 2 + tests)
4. `feat: add syllabus, generate-next, status CLI commands` (Phase 3 + tests)
5. `docs: add syllabus workflow documentation` (Phase 4)
