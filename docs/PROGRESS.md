# Progress log

## 2026-10-29

- Started from an empty workspace.
- User requires Cursor/VS Code and forbids Xcode. Project and scripts use only standalone Apple Command Line Tools, Swift 5.10, macOS 14.4 SDK. No Xcode project was created.
- Implemented local storage, authenticated FastAPI endpoints, approval transactions, Responses function calling and deterministic offline workflow.
- Implemented native overlay and conversation/personal-record/settings UI. Native build verification in progress.
- Backend checks: **18 passed** after fixing an SQL insert placeholder mismatch. Includes goal/task persistence across service recreation, concurrent/idempotent approvals, origin/host/auth protection, invalid input, retrieval bounds and mocked Responses behavior.
- Live OpenAI access is unverified; no user API key supplied. Mocked tests are not live provider validation.
- Correction: Google connectors are not implemented. Later sections record only checks actually performed.


## 2026-10-29 · Desktop-only correction

- User rejected the dashboard and cartoon. Removed the dashboard implementation and all auto-open/activate behavior. AppKit now launches only a transparent nonactivating kitten overlay; no dashboard, fullscreen window, or desktop Space is created.
- Added original AI-generated photorealistic silver-tabby kitten frames (16-frame alpha sheet: walk, sit/blink, sleep). This is synthesized imagery, not real-animal footage. Runtime aligns feet by alpha bounds and mirrors walking direction.
- Implemented autonomous horizontal desktop roaming, screen-edge reversals, elapsed-time cap after sleep, pause on chat/hover/drag/quiet mode, alpha-based click-through, and screen-clamped dragging.
- Clicking Paw opens a 350 × 400 borderless bubble beside it. Conversation, records, approvals, action history and settings stay within that bubble. Escape/click-away dismisses it. Data from the earlier build is preserved.
- Referenced https://github.com/andyy-yang/desktop-cat for real-video alpha animation, silhouette interaction and locomotion architecture. Inspected CatX as well; its realistic asset rights are explicitly unspecified, so no CatX assets were reused. No third-party source or cat assets were copied.
- Validation: 18 backend tests passed; 12 standalone Swift behavior/geometry checks passed; release .app built and ad-hoc signed with standalone Command Line Tools only.
- Live UI verified: kitten-only startup, photorealistic rendering, kitten accessibility click opens compact bubble, chat retrieves saved goal/task, Escape closes bubble, settings stay inline, quiet mode switches to sleeping. Quiet mode restored to off.
- Direct coordinate automation of the transparent overlay returned native accessibility/hit-test errors; silhouette alpha sampling was checked against source pixels, but end-to-end physical-pointer click-through and drag remain a manual verification item. Accessibility-based kitten activation and bubble controls were exercised successfully.
- Animation limitations: generated finite frames can have pose discontinuities; horizontal roaming only, no 3D rig/window climbing. Live OpenAI and Google account integrations remain unverified/unconfigured.

## 2026-10-29 · Phase 2 implementation and acceptance audit

Status: implementation and local acceptance complete; **Phase 2 is not fully verified** until live GPT acceptance succeeds. The user explicitly said they do not have an API key yet and do not know the location of a ChatGPT export. No account access or real export import is implied.

Implemented:
- Inline editable profile (name, background, preferences, constraints, IANA time zone), validated and persisted. GPT receives the saved profile each conversation.
- Native create/edit/search/archive/delete for goals, tasks, preferences, memories and projects. Goals have success criteria, dates and priority. Tasks have validated goal links, estimated minutes, priority, dates and completion. Goal cards count linked completed tasks.
- Local ZIP/JSON ChatGPT import with active-branch user-message filtering, personal-cue candidate selection, editable per-passage review, paging, atomic selected saves, deduplication and source identifiers. No assistant-generated facts or attachments are automatically remembered. No archive files are extracted. Explicit size/count limits and skipped counts are visible. Import accepts a dropped file or pasted path inside the bubble; no new dashboard or file-picker window.
- Schema migration preserves previous data, backfills missing search entries, and adds goal links/provenance/vector tables. Record deletion removes provenance and embeddings; editing invalidates vectors.
- GPT request context reserves goals, tasks and preferences, adds matching/recent memories and source metadata, and supports bounded read-only searches. Optional semantic embeddings are off by default and disclose sending stored text. Incremental indexing, edited-text invalidation, deletion and visible keyword fallback are implemented.
- Strict `propose_plan` tool validates 1–8 tasks linked to existing active goals. Proposals are staged only after a successful full model exchange, with separate user approval and idempotent decisions. Entire exchanges have a bounded timeout. Missing key, invalid provider output, bad links and provider failures never masquerade as completed GPT work.
- Added standard native editing/quit menu responders after the UI test exposed broken Cmd+A behavior. Verified replacement text and Cmd+Q afterward.

Executed verification:
- `bash scripts/check.sh`: **37 backend tests passed + 12 native behavior/geometry checks passed**. Tests include complete profile → import → controlled GPT plan → approve/reject → edit/complete → restart flow, malicious/invalid exports, transactional rollback, provenance, repeat imports, paging/Unicode, archive handling, migration, missing-key behavior, bounded retrieval, explicit-goal priority, controlled semantic ranking/cache invalidation/fallback, and failed-follow-up atomicity.
- `bash scripts/build-app.sh`: release app built and ad-hoc signed using standalone Swift Command Line Tools only. SPM emits its known XCTest-path/user-cache warnings; checks use the standalone executable harness and pass.
- `scripts/smoke-service.py`: **passed against real localhost child processes** with temporary data. Auth, profile editing, reviewed import, deduplication, offline goal → approved linked task, process restart and parent-pipe shutdown checked. No OpenAI calls.
- Native UI tested via accessibility in an isolated `PAWILOT_DATA_DIR=/private/tmp/pawilot-phase2-ui-check`: create/edit/save profile; import the synthetic JSON fixture by path; edit imported goal title; select and save goal/preference/memory; inspect source labels; edit goal details/date; ask priorities; inspect profile-aware **offline** response; approve task; complete it; see goal progress; manually create/edit a dated 20-minute task linked to the goal. A full app quit/restart preserved profile, imported records, task links/completion and conversation. Screenshots confirmed forms remain inside the existing 350×400 bubble. File-drop gesture itself was not exercised; the path-based import was.
- All sample UI data stayed in the isolated temporary database. The sample export is checked in at `fixtures/sample-chatgpt-export.json`; it is never seeded into the user's normal database.

Remaining acceptance gate:
- **No live GPT or embedding request was made:** the user has no API key yet. Controlled transports validate integration behavior, not live model reasoning/recall quality.
- `scripts/verify-live-gpt.py` is provided (syntax checked) for the live acceptance run after a key is saved in Paw. It uses synthetic profile/import data in a temporary database, the user's selected model, real Responses/embedding calls, task approvals, restart and recall; it prints synthetic responses for grounding review, never credentials. It incurs API usage and is not recorded as passed.
- No real personal export was supplied. Actual user-specific profile/goals must be entered or reviewed/imported; Paw does not inherit Codex/ChatGPT memory automatically.
- Phase 1/4 pointer dragging/click-through and animation polish, and Phase 3 Google/Slack work, remain separate from this Phase 2 audit.
- Final handoff: reopened the rebuilt app on the normal Application Support database. Native UI showed the original demo conversation and an empty personal profile, confirming sample test information was not copied over. Closed the bubble; only Paw remains visible on the existing desktop.

## 2026-10-29 · Corrected profile, Gemini, chat/settings revision

This section supersedes the earlier OpenAI/leaf/profile-form workflow above.

- Replaced the OpenAI Responses and embedding transport with Gemini generateContent and batchEmbedContents. Fixed Google endpoints, header-only key, bounded rounds, original thought signatures/call IDs, local validation and separate approvals retained. Default model `gemini-3.8-flash` follows the current official model documentation. Optional text embeddings use `gemini-embedding-001`, dimensions 768.
- Gemini Keychain account, Save & enable Gemini, model setting, connection test, removal/disable. No OpenAI key reuse. Legacy settings do not silently activate the new provider. Connection testing uses a small generic prompt without profile or chat data; HTTP failures are surfaced safely.
- Removed leaf/world/activity navigation and both retired personal-world/export UI source files. The header has chat, settings and close. Saved context and action history are collapsed inside settings. No manual biography form; context remains inspectable/removable, tasks completable, records archivable/restorable.
- Added explicit, one-time transactional context loader with pre-import SQLite backup, provenance and stable import marker. Input stays in ignored private `.local/`, never the app bundle. Repeated loading does not overwrite subsequent user changes or resurrect deleted records.
- Loaded the user-approved corrected summary and **20 records into the normal Application Support database**. Exact profile equality checked; imported text has no Stanford or NTRO entry. CAT 2027 and Indian B-school goal present. Archived the two identified older demonstration goal/task records; retained their data and conversations. The real database therefore has 20 imported active records plus two archived demos.
- Normal database backup created before import: `before-context-20261028T201358202802.sqlite3` in Paw's Application Support folder (UTC filename; local date October 29).

Executed:
- `bash scripts/check.sh`: **51 backend tests + 12 standalone native behavior/geometry checks passed**. Includes Gemini request/auth/schema/signature/call-result behavior, bad/blocked/truncated provider output, quota errors, no partial proposals, corrected context planning, importer transactions/idempotency, preservation of existing records, and no resurrection after deletion.
- `bash scripts/build-app.sh`: release app built and signed using standalone Command Line Tools only.
- Real socket smoke test passed outside the filesystem/network sandbox after the first sandboxed bind correctly failed with PermissionError. Profile/import/dedup, offline goal-linked approval, restart, auth and parent-pipe shutdown verified.
- Exact private corrected profile passed through actual Agent context-building and controlled Gemini transport: CAT goal and preferences in request, excluded topics absent, goal-linked proposal → approval → reopened database verified. No live API call in this check.
- Native UI on `/private/tmp/pawilot-gemini-ui-check`: kitten-only startup; only chat/settings navigation; “What are my goals?” returns corrected CAT/ISB/IIMs context; populated About you and 20 saved records; offline goal-linked proposal → Approve & save → Mark done. Full quit/relaunch preserved conversation, profile and completed task. Settings screenshot confirmed Gemini key controls stay in the same compact bubble. No real or fake key was written during UI testing.
- Reopened normal Application Support app. Actual native chat now returns the corrected goal. Test task remains only in the isolated test database. Existing demo history remains visible as history, not active goals.
- `scripts/verify-live-gemini.py` updated and syntax checked. **Not recorded as passed:** no user Gemini key exists yet. The app's live connection check and actual model planning/recall still require the user's key. Controlled tests do not prove live model quality.

Remaining separate limitations: direct physical-pointer click-through/drag and animation polish from prior audit; Google/Slack integrations, reminders and distribution remain later work. No live provider or proactive scheduling completion claimed.

## 2026-11-13 · Screen-activity awareness, goal check-ins, kitten liveliness

User restated the product: a realistic kitten companion that sees what they are doing, knows their goals, guides them when they drift, and connects to Slack and email.

Implemented:
- **Activity awareness.** The native app samples the frontmost app every 10 s (`ActivityMonitor`) and posts it to a new authenticated `POST /activity`. Window titles are read through the Accessibility API only after the user grants it from an explicit "Allow window titles…" button in Settings; nothing prompts at launch. Password-manager titles are never read. Nothing is sampled while the display sleeps or the screen is locked. This is observation only: no screenshots, no control of other apps, no new model tool.
- **Local, inspectable, removable.** Samples merge into sessions in a new `activity` table (created in place; existing data untouched), pruned after 7 days. Settings shows "Recent activity" with a Clear button (`DELETE /activity`), plus toggles "Notice what I'm working on" and "Check in when I drift from my goals" (both default on).
- **Chat grounding.** A bounded two-hour summary is added to Gemini chat context as untrusted data when awareness is on, and omitted when off. Offline, "What have I been doing?" / `/activity` answers from the local log.
- **Drift check-ins.** When the current window is a known distraction (YouTube, Netflix, Instagram, X, Reddit…) for 15+ of the last 30 minutes, an active goal exists, and quiet mode is off, Paw shows a small non-activating speech bubble naming the activity, the top goal and the next task, at most once per 40 minutes. Titles that match goal words or study hints (lecture, mock, prep…) do not count. With Gemini enabled, Gemini may reword or veto the check-in (no tools in that request); any failure falls back to the local wording. The check-in is also saved to the conversation.
- **Kitten liveliness.** Same photographic frames, now with a soft contact shadow, breathing while sitting/sleeping (anchored at the feet), and eased blending between poses instead of hard cuts. Inspection showed the sprite's alpha matte is clean; the remaining unrealism is the 8-frame generated walk, which is not a true gait cycle.

Executed:
- `bash scripts/check.sh`: **60 backend tests + 17 native checks passed** (9 new activity tests: session merging, retention, distraction rules, threshold/cooldown, quiet/disabled/no-goal cases, API validation and clearing, Gemini wording/veto with hostile window title kept out of system instructions, Gemini failure fallback, context inclusion only when enabled).
- `bash scripts/build-app.sh`: release app built and ad-hoc signed with standalone Command Line Tools.
- Live run of the built app on `PAWILOT_DATA_DIR=/private/tmp/pawilot-activity-check`: after 40 s the `activity` table held one merged session for the real frontmost app (title empty, as Accessibility was not granted); no messages created; backend exited with the app.
- Offscreen render of `KittenSurface` (sit, walk both directions, sleep) confirmed shadow placement and mirrored walking.

Not verified / limitations:
- The check-in bubble, Settings toggles and the Accessibility grant flow were **not exercised on screen**: this session could not capture windows. Window-title capture is therefore untested live; only app-name capture is.
- Because the app is ad-hoc signed, macOS may ask for the Accessibility grant again after each rebuild.
- Private/incognito browser windows are not detected; their titles are recorded like any other. Distraction detection is a keyword heuristic.
- No live Gemini call was made (still no key). Gemini check-in behaviour is verified with a controlled transport only.
- Slack, Gmail/Calendar and WhatsApp remain unimplemented. A convincingly real walking kitten needs real or generated video frames, which were not available in this session.

## 2026-11-13 · Live Gemini check-ins, model fallback, in-character permission ask

- A Gemini key is now saved in Keychain and Gemini is enabled in the user's settings, so live calls were possible for the first time. All live calls below used **synthetic data in a temporary database**; no personal records or real activity were sent by these checks.
- Live result: `gemini-3.8-flash` (the configured model) returned 503 UNAVAILABLE repeatedly; `gemini-3.6-flash` answered. Added `_generate`, which moves to `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-flash-latest` on 429/500/503/timeout only (auth and bad-request errors are not retried) and stays on the answering model for the rest of a tool exchange.
- With a key, keywords now only *trigger* the question and Gemini judges relevance (goal-word/study-hint exemptions apply only offline, or when Gemini is unreachable). Gemini also reviews un-flagged activity every 20 minutes once 15+ minutes with window titles have been observed; app names alone are never sent for review.
- Goal words must be 4+ letters, after the live run showed "CAT" (exam) exempting a "funniest cat fails" video.
- Once per install, when titles are not readable, Paw's own bubble asks to read window titles; the macOS Accessibility prompt opens only if the user presses Allow.
- `bash scripts/check.sh`: **62 backend tests + 17 native checks passed**. `bash scripts/build-app.sh`: built and signed.
- Live Gemini (synthetic): connection OK; chat answered "what am I doing, is it helping my goal" from observed activity with the correct goal and task; check-in nudged for a 20-minute "funniest cat fails" YouTube title and stayed silent for a "CAT 2027 DILR lecture" YouTube title.
- Limitations: the key is on a free-tier quota and returned 429 RESOURCE_EXHAUSTED on some models after a handful of calls, so check-ins may fall back to local wording. The check-in bubble, the permission bubble and real window-title capture are still unverified on screen. Slack, Gmail/Calendar, WhatsApp and screenshots remain unimplemented.

## Gmail and Slack read-only connections

Paw Settings now offers Connected accounts. Google Desktop OAuth requires the Gmail API, a Desktop client ID/secret and gmail.readonly consent. For Slack create an app from docs/slack-app.json in the target workspace and use its Client ID. Both flows return to short-lived loopback listeners, verify state and S256 PKCE, and store registrations and rotating credentials in macOS Keychain. Use /gmail or /slack with search terms in chat. Up to five previews and source links are saved in conversation history and available to a subsequent Gemini chat. Disconnect revokes the provider credential. Calendar and provider write actions remain outside this change.

Verification: 64 backend tests and 17 native checks passed; release app built and signed using standalone CLT. Real loopback callback checks for both services rejected the wrong state and completed the valid exchange with simulated providers. API tests exercised refresh, source previews and disconnect with a fake vault. Fixed an existing time-window mismatch in activity check-ins discovered by the suite. Actual user consent, workspace policies, account search results and provider revocation still require live registrations and grants.
