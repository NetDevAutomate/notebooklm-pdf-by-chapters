---
title: "feat: Interactive Study Review Interfaces"
type: feat
status: planned
date: 2026-03-13
updated: 2026-03-13
---

# feat: Interactive Study Review Interfaces

## Overview

Progressive build path from CLI → TUI → PWA → native apps for reviewing NotebookLM-generated flashcards, quizzes, and audio. Each phase adds capability while validating UX patterns before investing in the next layer.

## Problem Statement

The `pdf-by-chapters review` CLI command provides basic interactive review, but:
- No persistent progress tracking across sessions
- No audio playback integration
- No voice output (study-speak) integration
- No Markdown/diagram rendering in card content
- No mobile access for commute study
- No spaced repetition for wrong answers
- No offline access when away from home network
- No way to review only mistakes

## Build Path

```
Phase 1: Textual TUI          → Desk study, keyboard-driven
Phase 2: Local Web App (PWA)   → Mobile study, audio, offline
Phase 3: Native iOS + macOS    → App Store, push notifications, AWS sync
```

Each phase validates UX before the next. Don't build native until PWA proves the patterns.

---

## Phase 1: Textual TUI — StudyCards Tab

### What

Add a `StudyCards` tab to the existing `studyctl tui` Textual app with keyboard-driven flashcard/quiz review, voice toggle, and spaced repetition tracking.

### Architecture

```
studyctl tui
├── Overview tab (existing)
├── Sessions tab (existing)
└── StudyCards tab (NEW)
    ├── Course selector (dropdown — discovers all configured directories)
    ├── Mode toggle: Flashcards | Quiz | Mixed | Wrong Answers
    ├── Card display panel (front → flip → back)
    ├── Score buttons: Know / Don't Know / Skip
    ├── Progress bar (N/total, % correct)
    ├── Voice toggle (v key — reads question/answer via study-speak)
    └── Session summary on completion
```

### Key Bindings

| Key | Action |
|-----|--------|
| Space | Flip card (flashcard) / Submit answer (quiz) |
| y | Mark correct |
| n | Mark incorrect |
| s | Skip |
| h | Show hint (quiz only) |
| v | Toggle voice on/off |
| r | Review wrong answers from this session |
| q | Quit with summary |

### Voice Integration

```python
# Toggle voice in TUI
async def action_toggle_voice(self) -> None:
    self.voice_enabled = not self.voice_enabled
    if self.voice_enabled:
        # Import speak function from agent-session-tools
        from agent_session_tools.speak import _speak_kokoro, _get_tts_config
        cfg = _get_tts_config()
        self._voice = cfg.get("voice", "am_michael")
        self._speed = cfg.get("speed", 1.0)

# Speak current card when voice is on
async def _speak_card(self, text: str) -> None:
    if self.voice_enabled:
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, _speak_kokoro, text,
            {"voice": self._voice, "speed": self._speed}
        )
```

Voice is **optional** — works without kokoro installed, gracefully degrades to no voice.

### Spaced Repetition Tracking

Per-card results stored in sessions.db for SM-2 scheduling:

```sql
CREATE TABLE IF NOT EXISTS card_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course TEXT NOT NULL,
    card_type TEXT NOT NULL,      -- 'flashcard' or 'quiz'
    card_hash TEXT NOT NULL,      -- SHA256 of question text (stable ID)
    correct BOOLEAN NOT NULL,
    reviewed_at TEXT NOT NULL,    -- ISO 8601
    ease_factor REAL DEFAULT 2.5, -- SM-2 ease factor
    interval_days INTEGER DEFAULT 1,
    next_review TEXT              -- ISO 8601 date
);

CREATE INDEX IF NOT EXISTS idx_card_reviews_next ON card_reviews(course, next_review);
```

### Wrong Answers Review Mode

After completing a session, press `r` to review only cards you got wrong. Also available as:
```bash
pdf-by-chapters review ~/Desktop/ZTM-DE/downloads --retry-wrong
```

The `--retry-wrong` flag loads the last session's wrong answers from card_reviews.

### Multiple Download Directories

```yaml
# ~/.config/studyctl/config.yaml
review:
  directories:
    - ~/Desktop/ZTM-DE/downloads
    - ~/Desktop/Python-Course/downloads
    - ~/Obsidian/Personal/2-Areas/Courses
  default_mode: flashcards
  shuffle: true
  voice_enabled: false
```

Course selector auto-discovers all directories. New directories appear automatically.

### Cross-Package Dependency Solution

**Don't import `pdf_by_chapters.review` from studyctl.** Instead, copy the data loading code (~60 lines of dataclasses + JSON parsing) into `studyctl/review_loader.py`. Zero coupling between packages. The JSON format is the contract, not the Python code.

```python
# packages/studyctl/src/studyctl/review_loader.py
# Self-contained flashcard/quiz loader — no cross-package imports
# Reads the same JSON format as pdf_by_chapters generates
```

### Dependencies

- `textual` (already optional dep in studyctl)
- `study-speak` for voice (optional — graceful fallback to no voice)

### Acceptance Criteria

- [ ] StudyCards tab appears in `studyctl tui`
- [ ] Multiple course directories auto-discovered from config
- [ ] Flashcard mode: space to flip → y/n/s to score
- [ ] Quiz mode: a/b/c/d selection, hint support, rationale display
- [ ] Voice toggle (v key) reads cards aloud via kokoro
- [ ] Progress bar updates after each card
- [ ] Per-card results saved to card_reviews table
- [ ] Wrong answers review mode (r key / --retry-wrong)
- [ ] Session summary with score, grade, and "due for review" count
- [ ] Keyboard-only navigation
- [ ] Graceful fallback when kokoro not installed

---

## Phase 2: Local Web App (PWA) — `studyctl serve`

### What

A local web server + Progressive Web App for mobile study with offline capability, audio playback, and voice output. Installable on iPhone/iPad home screen.

### What is a PWA?

A **Progressive Web App** is a website that can be installed on your phone's home screen like a native app. It:
- Works offline (caches data via Service Worker)
- Has its own app icon and splash screen
- Runs full-screen (no browser chrome)
- Can send push notifications (optional)
- No App Store submission required

Your `studyctl serve` + a `manifest.json` + a service worker = a study app on your phone.

### Architecture

```
studyctl serve [--port 8080] [--dir ~/Desktop/ZTM-DE/downloads]
     │
     ├── GET /                      → Dashboard: courses, progress, due reviews
     ├── GET /course/:name          → Course overview: sections, progress
     ├── GET /flashcards/:name      → Swipeable card UI (front/back flip)
     ├── GET /quiz/:name            → Multiple choice with instant feedback
     ├── GET /audio/:name           → Audio player with episode list
     ├── GET /wrong/:name           → Review wrong answers only
     ├── POST /api/score            → Record per-card score
     ├── GET /api/progress/:name    → Progress + spaced repetition data
     ├── POST /api/speak            → TTS via study-speak (optional)
     ├── Static: /audio/*.mp3       → Served from downloads/audio/
     ├── GET /manifest.json         → PWA manifest
     └── GET /sw.js                 → Service worker for offline
```

### Tech Stack

| Component | Choice | Rationale |
|---|---|---|
| Server | FastAPI | Python ecosystem, async, lightweight |
| Templates | Jinja2 | Server-rendered, no build step |
| Interactivity | HTMX | Minimal JS, server-driven updates |
| CSS | Pico CSS | Classless, responsive, dark mode |
| Audio | Native `<audio>` | No JS library needed |
| Voice | `/api/speak` endpoint | Calls study-speak on server, streams audio back |
| Offline | Service Worker | Caches cards/quizzes for offline use |
| Storage | sessions.db | Reuse existing SQLite + card_reviews table |

### PWA Manifest

```json
{
  "name": "Study Review",
  "short_name": "StudyReview",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0d1117",
  "theme_color": "#58a6ff",
  "icons": [
    {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
  ]
}
```

### Service Worker (Offline Strategy)

```javascript
// sw.js — cache flashcard/quiz JSON for offline study
const CACHE_NAME = 'study-review-v1';

self.addEventListener('fetch', event => {
  // Cache API responses for cards and quizzes
  if (event.request.url.includes('/api/')) {
    event.respondWith(
      caches.open(CACHE_NAME).then(cache =>
        fetch(event.request)
          .then(response => {
            cache.put(event.request, response.clone());
            return response;
          })
          .catch(() => cache.match(event.request))
      )
    );
  }
});
```

**Offline flow:** First load caches all card data. Subsequent loads work without network. Scores queue locally and sync when online.

### Voice in Web App

Two options (configurable):

1. **Server-side TTS** — `POST /api/speak` sends text to server, server runs study-speak, streams WAV/MP3 back. Works with kokoro quality but requires server connection.

2. **Browser SpeechSynthesis** — `speechSynthesis.speak(new SpeechSynthesisUtterance(text))`. Works offline, lower quality, no kokoro voices. Good fallback.

```javascript
// Voice toggle in web UI
function speakText(text) {
  if (voiceMode === 'server') {
    fetch('/api/speak', {method: 'POST', body: JSON.stringify({text})})
      .then(r => r.blob())
      .then(b => new Audio(URL.createObjectURL(b)).play());
  } else if (voiceMode === 'browser') {
    speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }
}
```

### Spaced Repetition Dashboard

The dashboard shows:
- **Due today:** Cards where `next_review <= today` (orange highlight)
- **Overdue:** Cards past their review date (red)
- **Mastered:** Cards with interval > 30 days (green)
- **New:** Cards never reviewed

### Progress Schema

```sql
-- Per-card tracking for spaced repetition
CREATE TABLE IF NOT EXISTS card_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course TEXT NOT NULL,
    card_type TEXT NOT NULL,
    card_hash TEXT NOT NULL,
    correct BOOLEAN NOT NULL,
    reviewed_at TEXT NOT NULL,
    ease_factor REAL DEFAULT 2.5,
    interval_days INTEGER DEFAULT 1,
    next_review TEXT,
    response_time_ms INTEGER  -- how long they took to answer
);

-- Session-level summaries
CREATE TABLE IF NOT EXISTS review_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course TEXT NOT NULL,
    mode TEXT NOT NULL,          -- 'flashcards', 'quiz', 'wrong_answers'
    total INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    duration_seconds INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
```

### API Endpoints

```python
# Per-card score recording
POST /api/score
{
    "course": "ZTM-DE",
    "card_type": "flashcard",
    "card_hash": "abc123...",
    "correct": true,
    "response_time_ms": 3400
}

# Course progress with spaced repetition
GET /api/progress/ZTM-DE
{
    "flashcards": {"total": 48, "reviewed": 24, "correct": 20, "due_today": 8},
    "quizzes": {"total": 80, "reviewed": 40, "correct": 32, "due_today": 3},
    "last_reviewed": "2026-03-13T14:30:00Z",
    "mastered": 15,
    "struggling": 5
}

# Wrong answers for retry
GET /api/wrong/ZTM-DE?type=flashcard
{
    "cards": [...],  // cards where last review was incorrect
    "count": 5
}
```

### Acceptance Criteria

- [ ] `studyctl serve` starts local web server
- [ ] Dashboard lists courses with progress + due reviews
- [ ] Flashcard page: tap to flip, swipe/button to score
- [ ] Quiz page: select answer, submit, see rationale
- [ ] Audio page: play/pause episodes
- [ ] Wrong answers mode: review only mistakes
- [ ] Voice toggle: server TTS or browser SpeechSynthesis
- [ ] PWA installable on iPhone home screen
- [ ] Offline mode: cached cards work without network
- [ ] Scores persisted to card_reviews table
- [ ] Spaced repetition: due/overdue/mastered tracking
- [ ] Mobile responsive (tested on iPhone Safari)
- [ ] Works over local network
- [ ] `--dir` and `--port` flags

---

## Phase 3: Native Apps + Cloud Sync (Future)

### Why Wait

PWA validates the UX first. Native apps are 10x the effort. Build native only when:
1. PWA proves the study patterns work
2. You need push notifications for review reminders
3. You want App Store distribution
4. You need Apple Watch complication for due-card count

### iOS App (SwiftUI)

```
StudyReview.app
├── Dashboard       → Course list, due counts, streaks
├── Flashcards      → Card flip with haptic feedback
├── Quiz            → Multiple choice with animations
├── Audio Player    → Background audio, lock screen controls
├── Progress        → Charts, mastery tracking, streak calendar
└── Settings        → Voice, sync, notifications
```

**Tech:** SwiftUI + Swift Data (local) + AWS sync (cloud). Universal app (iPhone + iPad + Mac Catalyst).

**Key native advantages over PWA:**
- Push notifications ("5 cards due for review")
- Apple Watch complication (due count)
- Background audio with lock screen controls
- Haptic feedback on correct/incorrect
- Widget for home screen (next card preview)
- Siri Shortcuts ("Hey Siri, quiz me on Data Engineering")

### macOS App

Mac Catalyst from the iOS app, or standalone SwiftUI. Menu bar status item showing due-card count (similar to studyctl-status.sh).

### Cloud Sync (AWS)

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ iPhone App  │────→│ API Gateway  │────→│ DynamoDB    │
│ iPad App    │     │ + Lambda     │     │ per-user    │
│ macOS App   │←────│ + Cognito    │←────│ partitioned │
│ PWA         │     └──────────────┘     └─────────────┘
└─────────────┘
```

| Component | Service | Purpose |
|---|---|---|
| Auth | Cognito | User pools, social login (Apple ID, Google) |
| API | API Gateway + Lambda | REST API for sync |
| Storage | DynamoDB | Card reviews, progress, per-user partition key |
| Notifications | SNS + APNS | Push notifications for due reviews |
| Content | S3 | Flashcard/quiz JSON, audio files |

**DynamoDB schema:**

```
PK: USER#<user_id>
SK: CARD#<course>#<card_hash>
Attributes: ease_factor, interval_days, next_review, last_correct, review_count

PK: USER#<user_id>
SK: SESSION#<timestamp>
Attributes: course, mode, total, correct, duration

GSI: next_review-index
PK: USER#<user_id>
SK: next_review
Purpose: Query all cards due for review efficiently
```

**Sync strategy:** Offline-first with conflict resolution. Local SQLite is source of truth. Sync merges by `reviewed_at` timestamp (latest wins). DynamoDB Streams for real-time sync between devices.

### Cost Estimate (AWS)

For a single user (your usage):
- DynamoDB on-demand: ~$0.00/month (well within free tier)
- Lambda: ~$0.00/month (free tier)
- API Gateway: ~$0.00/month (free tier)
- S3: ~$0.50/month (audio files)
- Cognito: free for <50k MAU
- **Total: ~$0.50/month**

For multi-user (if you release it):
- DynamoDB: ~$5-10/month per 1000 active users
- Per-user partition key prevents noisy neighbours

---

## Implementation Order

1. **Phase 1: Textual TUI** — 1-2 sessions. Immediate value.
2. **Phase 2: PWA web app** — 2-3 sessions. Mobile study unlocked.
3. **Phase 2.5: Obsidian export** — 1 session. `pdf-by-chapters export-obsidian` for Spaced Repetition plugin users.
4. **Phase 3: Native iOS** — Multi-week project. Only after PWA validates UX.
5. **Phase 3.5: AWS sync** — After native app. Enables multi-device.

## Risks

| Risk | Mitigation |
|---|---|
| Cross-package import breaks | Copy loader code into studyctl (60 lines, zero coupling) |
| FastAPI adds dependency weight | Optional extra `studyctl[serve]` |
| Mobile browser quirks | Test Safari iOS early; Pico CSS handles most |
| Audio files large (50MB+) | Serve from filesystem, cache in service worker |
| SM-2 algorithm complexity | Start simple (double interval on correct, reset on wrong) |
| PWA offline cache stale | Version cache, prompt user to refresh |
| Native app maintenance burden | Don't build until PWA proves the patterns |
| AWS costs at scale | DynamoDB on-demand, per-user partition, free tier covers personal use |
| SwiftUI learning curve | You have iOS dev experience? If not, consider React Native |
