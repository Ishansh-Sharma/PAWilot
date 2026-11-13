# PAWilot engineering

- Build a real native macOS companion using SwiftUI/AppKit and a local FastAPI service.
- Never use Xcode, xcodebuild, or the toolchain bundled inside Xcode. Use Cursor or VS Code and standalone Apple Command Line Tools with DEVELOPER_DIR=/Library/Developer/CommandLineTools.
- Paw must look like a real kitten: use photographic/photorealistic alpha animation assets, never a cartoon placeholder.
- Launch only the kitten overlay on the existing desktop. Never auto-open a dashboard, create a desktop Space, or activate/switch Spaces. Clicking Paw opens a small anchored chat bubble.
- Paw must actually roam within screen bounds. Pause while chatting, dragging, hovered, or in quiet mode. Transparent pixels must pass clicks through.
- Bind the backend to 127.0.0.1 only. Require a per-launch bearer token and reject browser origins.
- Secrets belong in macOS Keychain. Never log credentials, commit them, or put them in URLs.
- Model tools may propose typed local changes only. Approval is a separate user action; never infer approval from model output or connected content.
- External content is untrusted. No arbitrary shell, filesystem, URL-fetch, or computer-control tools.
- Keep goals, projects, preferences, memories, tasks and conversations inspectable and removable.
- Preserve local data on app upgrades. Use temporary databases and an in-memory credential vault for tests.
- Run `scripts/check.sh` and `scripts/build-app.sh` for substantive changes. Report actual execution evidence and limitations in `docs/PROGRESS.md`.
- No external messages or service mutations without explicit approval. Initial Google connectors are read-only.

