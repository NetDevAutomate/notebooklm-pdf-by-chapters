---
title: "feat: Interactive Study Review Interfaces"
type: feat
status: planned
date: 2026-03-13
---

# feat: Interactive Study Review Interfaces

## Overview

Two complementary interfaces for reviewing NotebookLM-generated flashcards, quizzes, and audio: a Textual TUI tab in studyctl for terminal-based desk study, and a local web app for rich mobile-friendly review with audio playback.

## Problem Statement

The `pdf-by-chapters review` CLI command provides basic interactive review, but:
- No persistent progress tracking across sessions
- No audio playback integration
- No Markdown/diagram rendering in card content
- No mobile access for commute study
- No visual progress indicators

## Phase 1: Textual TUI — StudyCards Tab

### What

Add a `StudyCards` tab to the existing `studyctl tui` Textual app that loads flashcard and quiz JSON from a configurable directory and presents them with keyboard-driven interaction.

### Architecture

```
studyctl tui
├── Overview tab (existing)
├── Sessions tab (existing)
└── StudyCards tab (NEW)
    ├── Course selector (dropdown of discovered directories)
    ├── Mode toggle: Flashcards | Quiz | Mixed
    ├── Card display panel (front → flip → back)
    ├── Score buttons: Know / Don't Know / Skip
    ├── Progress bar (N/total, % correct)
    └── Session summary on completion
```

### Implementation

**File:** `packages/studyctl/src/studyctl/tui/study_cards.py`

```python
from textual.widgets import Static, Button, ProgressBar
from textual.containers import Horizontal, Vertical
from textual.screen import Screen

from pdf_by_chapters.review import (
    load_flashcards, load_quizzes, discover_content,
    Flashcard, QuizQuestion, ReviewResult
)

class StudyCardsTab(Static):
    """Interactive flashcard and quiz review tab."""

    BINDINGS = [
        ("space", "flip", "Flip card"),
        ("y", "mark_correct", "Correct"),
        ("n", "mark_incorrect", "Incorrect"),
        ("s", "skip", "Skip"),
        ("h", "hint", "Hint (quiz)"),
    ]
```

**Key widgets:**
- `CardPanel` — displays front/back with flip animation (CSS transition)
- `ScoreBar` — horizontal buttons: Know (green), Don't Know (red), Skip (dim)
- `ProgressIndicator` — fraction + progress bar + current score %
- `CoursePicker` — dropdown listing discovered download directories

**Data flow:**
1. User selects course directory (or configured default)
2. `discover_content()` finds flashcard/quiz subdirs
3. Cards loaded and shuffled via `pdf_by_chapters.review`
4. Each card displayed → user scores → next card
5. Summary shown at end
6. Results written to sessions.db via `tutor-checkpoint`

**Config integration:**
```yaml
# ~/.config/studyctl/config.yaml
review:
  downloads_dir: ~/Desktop/ZTM-DE/downloads
  default_mode: flashcards  # flashcards | quiz | mixed
  shuffle: true
```

### Dependencies

- `textual` (already an optional dep in studyctl)
- `pdf_by_chapters.review` (cross-package import — needs to be installed)

### Acceptance Criteria

- [ ] StudyCards tab appears in `studyctl tui`
- [ ] Course directory auto-discovered from config
- [ ] Flashcard mode: front → space to flip → y/n/s to score
- [ ] Quiz mode: a/b/c/d selection, hint support, rationale display
- [ ] Progress bar updates after each card
- [ ] Session summary with score and grade
- [ ] Keyboard-only navigation (no mouse required)
- [ ] Ctrl+C exits cleanly without data loss

---

## Phase 2: Local Web App — `studyctl serve`

### What

A local web server serving flashcards, quizzes, and audio from the downloads directory. Mobile-friendly, rich content rendering, audio playback.

### Architecture

```
studyctl serve [--port 8080] [--dir ~/Desktop/ZTM-DE/downloads]
     │
     ├── GET /                      → Dashboard: courses, progress, quick stats
     ├── GET /course/:name          → Course overview: sections, progress per section
     ├── GET /flashcards/:name      → Swipeable card UI (front/back flip)
     ├── GET /quiz/:name            → Multiple choice with instant feedback
     ├── GET /audio/:name           → Audio player with episode list
     ├── POST /api/score            → Record score for a card/question
     ├── GET /api/progress/:name    → Progress data for a course
     └── Static: /audio/*.mp3       → Served directly from downloads/audio/
```

### Tech Stack

| Component | Choice | Rationale |
|---|---|---|
| Server | FastAPI | Already in Python ecosystem, async, lightweight |
| Templates | Jinja2 | Server-rendered, no JS build step |
| Interactivity | HTMX | Minimal JS, server-driven updates |
| CSS | Pico CSS | Classless, responsive, dark mode, tiny |
| Audio | Native `<audio>` | No JS library needed |
| Storage | sessions.db | Reuse existing SQLite infrastructure |

### Key Design Decisions

1. **No React/Vue/build step.** HTMX + Jinja2 is enough. Cards flip via CSS transitions, quiz answers submit via HTMX POST, audio plays natively.

2. **Serve from existing downloads directory.** No copying or importing — point `studyctl serve` at any downloads dir and it discovers content.

3. **Mobile-first responsive layout.** Pico CSS handles this. Cards are full-width on mobile, grid on desktop.

4. **Audio integration.** Each course page has an embedded player for its audio files. Can listen while reviewing flashcards.

5. **Progress persisted to sessions.db.** Each review session creates a record with score, duration, cards reviewed. Feeds into spaced repetition.

### Page Designs

#### Dashboard (`/`)
```
┌────────────────────────────────────┐
│ Study Review                       │
├────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐         │
│ │ ZTM-DE   │ │ Python   │  ...    │
│ │ 8 cards  │ │ 12 cards │         │
│ │ 75% done │ │ new      │         │
│ └──────────┘ └──────────┘         │
├────────────────────────────────────┤
│ Recent: ZTM-DE quiz — 8/10 (80%)  │
│ Due for review: Python flashcards  │
└────────────────────────────────────┘
```

#### Flashcard (`/flashcards/:name`)
```
┌────────────────────────────────────┐
│ Card 3/24          ZTM-DE          │
├────────────────────────────────────┤
│                                    │
│  What is a data pipeline?          │
│                                    │
│  ┌──────────────────────────────┐  │
│  │     [ Tap to reveal ]        │  │
│  └──────────────────────────────┘  │
│                                    │
│  [Know]  [Don't Know]  [Skip]      │
├────────────────────────────────────┤
│ ████████░░░░░░░░░░░  3/24  75%     │
└────────────────────────────────────┘
```

#### Quiz (`/quiz/:name`)
```
┌────────────────────────────────────┐
│ Question 2/10      ZTM-DE          │
├────────────────────────────────────┤
│                                    │
│  Which term best describes the     │
│  core value proposition of data    │
│  engineering?                      │
│                                    │
│  ○ a) Generation of raw data       │
│  ○ b) Statistical models           │
│  ● c) Transforming raw data into   │
│       structured assets            │
│  ○ d) Manual log inspection        │
│                                    │
│  [Hint]  [Submit]  [Skip]          │
├────────────────────────────────────┤
│  ✓ Correct!                        │
│  Data engineering acts as the      │
│  refinement layer...               │
└────────────────────────────────────┘
```

### File Structure

```
packages/studyctl/src/studyctl/
├── serve.py              # FastAPI app + routes
├── templates/
│   ├── base.html         # Layout with nav + Pico CSS
│   ├── dashboard.html    # Course listing
│   ├── flashcards.html   # Card review UI
│   ├── quiz.html         # Quiz UI
│   └── audio.html        # Audio player
└── cli.py                # Add 'serve' command
```

### Dependencies

New optional dependency group in studyctl:
```toml
[project.optional-dependencies]
serve = [
    "fastapi>=0.115",
    "uvicorn>=0.34",
    "jinja2>=3.1",
]
```

### API Endpoints

```python
# Score recording
POST /api/score
{
    "course": "ZTM-DE",
    "type": "flashcard",  # or "quiz"
    "card_index": 3,
    "correct": true,
    "duration_seconds": 12
}

# Progress retrieval
GET /api/progress/ZTM-DE
{
    "flashcards": {"total": 48, "reviewed": 24, "correct": 20},
    "quizzes": {"total": 80, "reviewed": 40, "correct": 32},
    "last_reviewed": "2026-03-13T14:30:00Z"
}
```

### Acceptance Criteria

- [ ] `studyctl serve` starts a local web server
- [ ] Dashboard lists discovered courses with progress
- [ ] Flashcard page: tap/click to flip, score buttons work
- [ ] Quiz page: select answer, submit, see rationale
- [ ] Audio page: play/pause episodes, show titles
- [ ] Mobile responsive (tested on iPhone Safari)
- [ ] Scores persisted to sessions.db
- [ ] Works over local network (access from phone on same wifi)
- [ ] `--dir` flag to point at any downloads directory
- [ ] `--port` flag (default 8080)

---

## Implementation Order

1. **Phase 1: Textual TUI** — faster to build, immediate value at the desk
2. **Phase 2: Web app** — richer experience, mobile access, audio integration
3. **Phase 3 (optional): Obsidian export** — `pdf-by-chapters export-obsidian` converting JSON to Obsidian flashcard format

## Risks

| Risk | Mitigation |
|---|---|
| Cross-package import (`pdf_by_chapters.review` from `studyctl`) | Both installed as tools; review.py has zero external deps |
| FastAPI adds dependency weight | Optional extra, only installed if `studyctl[serve]` |
| Mobile browser quirks | Test on Safari iOS early; Pico CSS handles most issues |
| Audio files are large (50MB+) | Serve directly from filesystem, no copying |
