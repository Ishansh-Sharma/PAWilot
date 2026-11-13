# PAWilot

A native macOS kitten with a small adjacent chat bubble and local personal context. Build in **Cursor or VS Code**, using standalone Apple Command Line Tools. **Never use Xcode or its bundled toolchain.**

## Run locally

Apple Silicon Mac, macOS 14+, standalone Swift 5.10+, Python 3.12 and `uv` are required.

```sh
bash scripts/setup.sh
bash scripts/check.sh
bash scripts/build-app.sh
bash scripts/run.sh
```

Open `PAWilot.code-workspace` in Cursor/VS Code for equivalent editor tasks. `build/PAWilot.app` is a local development bundle using this checkout's `.venv`; it is not portable or notarized. SPM's known XCTest-path warning does not affect the standalone native check executable.

## Chat and settings

Launch shows only the kitten on the existing desktop. Clicking it opens a 350 × 400 bubble with **chat and settings only**. No dashboard, profile setup form, new Space or startup window. Escape, close or click-away dismisses the bubble. Roaming pauses during chat, hovering, dragging and quiet mode. The photorealistic frames are AI-generated, not footage; animation transitions remain an initial implementation.

To add the key: **click Paw → gear → Gemini API key → Save & enable Gemini → Test connection**. Saving enables Gemini automatically. `Test connection` also saves the visible settings and makes a small real generation request; it does not send the personal profile or create chat messages/tasks. A failed test is shown as an error, never as success. Return using the chat icon and ask about your goals.

The default model is `gemini-3.8-flash`; a different accessible Gemini model ID can be saved in settings. Keys live only in macOS Keychain (`app.pawilot.credentials`, account `gemini`), never SQLite, logs, source, request URLs or command arguments. Removing the key disables Gemini. Old OpenAI credentials are never read or sent to Google; legacy OpenAI model settings migrate to Gemini with AI/semantic search disabled.

Your reviewed context can be populated once using `scripts/load-personal-context.py PRIVATE_JSON DATA_DIRECTORY`. This validates records, backs up SQLite, imports atomically with source metadata and a stable batch ID, and avoids repeat imports or resurrecting deleted context. It never runs on app launch. Private context inputs belong in ignored `.local/`, not source or app resources. The user-approved October 29 profile was loaded into the normal database separately; no personal information is embedded in the distributed app code. The import is a dated snapshot, not continuous ChatGPT account access.

**Settings → Saved context** contains a read-only profile summary and saved goals, tasks, preferences, projects and memories. Individual records can be archived/restored/removed; tasks can be marked done. The profile summary can be removed separately. Action history is a collapsed settings section. Clear conversation removes chat and dismisses pending proposals, leaving records intact. Deleting a record does not erase its mention in older conversation or backups; deletion is logical, not forensic erasure.

Offline commands: `/profile`, `/goals`, `/tasks`, `/memories`, `/goal …`, `/task …`, `/remember …`, `/preference …`, `/project …`. “What do you know about me?” and “What are my goals?” retrieve saved context offline. Offline planning is deterministic, not Gemini reasoning.

## Gemini and memory

Requests use the fixed Google Gemini `generateContent` endpoint and an `x-goog-api-key` header. Personal context is untrusted user-role data, not system instructions. Requests include the saved profile, up to 12 recent messages, up to 12 active goals, 16 open tasks, 8 preferences and 10 matching/recent memories or projects, with provenance. Archived records are excluded. Gemini can search additional local records by keywords or propose local records/plans of up to eight goal-linked tasks. No shell, browser, external writes or scheduling tools are exposed.

Tool calls are validated locally, including goal existence and task effort/date bounds. Original Gemini content parts, thought signatures and call IDs are preserved across the tool exchange. Proposed changes are staged only when the entire exchange succeeds; each still requires the user's approval. Errors, blocked responses, truncated output and failed follow-ups cannot create partially accepted plans. Approval is idempotent and transactional.

Optional semantic search is off by default. It uses `gemini-embedding-001`, 768-dimensional vectors, document/query task types, locally cached vectors, at most 64 changed records per request, and local keyword fallback. Editing/deleting invalidates vectors. Both profile/context and optional embedding text go to Google only when those features are enabled. No provider retention guarantees are claimed.

The reviewed ZIP/JSON export importer remains available in the authenticated local backend for future import tooling. It uses active-branch user-text filtering, English personal-context cues, explicit selection, paging, deduplication and provenance. It never extracts archive paths or stores the full export. Its conservative heuristic does not establish whether a statement is current/true. The retired leaf/“Your world”/import pages are no longer in the native UI.

## Verification

```sh
bash scripts/check.sh
.venv/bin/python scripts/smoke-service.py
```

Current checks: **51 backend tests and 12 native checks pass**. The real socket smoke test checks auth, profile/import, approvals, restart persistence and shutdown. Native UI testing verified corrected context, task proposal/approval/completion and restart in a temporary database, followed by the real profile in the normal app.

**Live Gemini planning/recall and embedding quality remain unverified until a user key is supplied.** Controlled transport tests are not live model acceptance. After saving a key, run the separate usage-incurring acceptance check:

```sh
.venv/bin/python scripts/verify-live-gemini.py
```

It uses synthetic data in a temporary database, reads the saved Gemini key/model, requests a goal-linked plan, approves/rejects tasks, restarts and asks for recall. It never prints credentials. A missing key or failed request is an incomplete check. Review the synthetic response wording for grounding. See `docs/PROGRESS.md` for evidence and limitations.

## Local architecture

- SwiftUI chat/settings inside AppKit nonactivating transparent panels.
- Python FastAPI child on an OS-assigned `127.0.0.1` port. Per-launch bearer arrives over private stdin, not process arguments/disk; browser origins are rejected. Parent-pipe closure stops the child.
- SQLite at `~/Library/Application Support/PAWilot/pawilot.sqlite3`, owner-only permissions. `PAWILOT_DATA_DIR` isolates development tests. No encryption beyond OS/FileVault protection is claimed.
- Google account integrations, proactive reminders, expanded animation and portable signed distribution are later milestones.

## Provider references

- [Gemini function calling](https://ai.google.dev/gemini-api/docs/generate-content/function-calling)
- [Gemini models](https://ai.google.dev/gemini-api/docs/models)
- [Gemini embeddings API](https://ai.google.dev/api/embeddings)
