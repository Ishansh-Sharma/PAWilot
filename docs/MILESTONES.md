# Milestones

## 1 · Runnable local companion

- Native transparent overlay, dragging, interaction and replaceable temporary renderer.
- Compact on-demand anchored chat bubble and inline settings. No dashboard or startup window.
- Authenticated loopback service and private local persistence.
- Goal → retrieved priorities → proposed task → explicit approval → restart persistence.
- Real build and automated checks with standalone Swift; visual UI acceptance.

## 2 · Personal intelligence — local acceptance passed; live Gemini pending

- User-approved profile and 20 sourced context records imported once into the normal local database; corrected CAT 2027 / top Indian B-school direction. Old demos archived; data retained.
- Chat and settings only. No manual profile onboarding or separate world/import page. Saved context and completion/archive/removal controls are within settings.
- Gemini chat/planning/key settings replace OpenAI. Keychain storage, connection check, bounded context, local search and optional Gemini embeddings.
- Up to eight validated goal-linked task proposals, atomic staging, separate approvals and visible failures.
- 51 backend and 12 native checks pass. Actual native corrected-context → offline proposal → approval → completion → restart tested in isolation. Actual personal context inclusion in Gemini payload verified with controlled transport.
- **Gate still open:** user key not yet supplied. Live Gemini reasoning/recall and embedding quality are not verified. `scripts/verify-live-gemini.py` provides synthetic-data live acceptance after the key is saved.

## 3 · Authorized integrations

- After milestone 1, implement Google desktop OAuth with state, PKCE, refresh and revocation.
- Separate Calendar event read and Gmail message read permissions; source-linked previews.
- Real account testing requires a user-supplied Google Cloud Desktop OAuth client and consent.
- Slack follows Google validation. Any future send/draft/event-write tool must use an immutable reviewable action payload and explicit approval, with idempotency and provider-result logging.
- WhatsApp: explicitly shared/imported content only until a supported access method is chosen.

## 4 · Final character

- Photorealistic alpha sprite sheet now replaces the vector placeholder. Improve pose-to-pose transitions and expand the frame library.
- Consistent photorealistic character identity, sleep/walk/groom loops, motion bounds, multi-monitor and accessibility review.
- Current walk moves the kitten across its desktop row and reverses at screen edges. Vertical climbing/window perching remain future work.

## 5 · Proactive workflows

- Done 2026-11-13: local foreground app/window-title awareness, activity in chat context, and goal-drift check-in bubble (heuristic, optional Gemini wording). On-screen bubble and window-title permission flow still need manual verification.

- Implement a durable job table, timezone-aware scheduling and recovery after sleep/restart.
- Briefing/goal-review jobs must deduplicate by local calendar date and record source timestamps.
- Quiet hours, focus controls, explicit notification authorization and meaningful-change-only delivery.
- Deadlines must retain evidence and confidence; uncertain dates require review.
- No notification or scheduling claim until delivery is tested on a real Mac.

## Distribution gate

- Bundle a relocatable Python runtime, migrate data across versions, test offline startup and upgrades.
- Developer signing/notarization, permission review and supported OS matrix.
- Large data paging, full conversation navigation, import previews, export/backups and retrieval quality evaluation.

