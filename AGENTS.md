# Project development rules

- Preserve the existing `src/zotero_file_explorer` package and Qt Widgets architecture.
  `core` contains domain/classification; `api` is read-only Zotero integration;
  `services` handles synchronization/paths; `storage` owns only this app's metadata;
  `platform` implements native file/Windows operations; `ui` owns views and motion.
- Python uses snake_case modules/functions, PascalCase classes, Ruff and Python 3.11–3.14.
  If QML is introduced after validation, use PascalCase components; do not add an unused QML tree.
- Use `ui/motion.py` tokens and policy for feedback. Respect Windows animation preferences.
  No per-row animation objects, continuous decoration, geometry changes to drag hit areas,
  blocking exit animation, or Web animation runtime. New animations must settle when disabled.
- Keep network, filesystem validation and index queries on workers. Update Qt objects only
  on the GUI thread; coalesce stale searches. Preserve identity across instance/library/item.
- Never write Zotero databases, move/delete originals, or duplicate a user's attachment library.
  Runtime settings/index/logs belong under LOCALAPPDATA, or an explicit test data directory.
- Preserve QDrag/QMimeData local file URLs, CF_HDROP and CopyAction-only semantics.
  UI previews are decorative. Test actual MIME and selection behavior after view changes.
- Keep dependencies minimal and align pyproject with the development lock. Runtime assets
  must load both from source and the installer. Keep third-party notices/source obligations.
- Tests: `.venv/Scripts/python.exe -m ruff check src tests scripts`, then
  `.venv/Scripts/python.exe -m pytest -q`. Native Shell tests require an interactive Windows
  session; record failures separately, never remove tests to obtain a passing release.
- Use synthetic 500/5,000/20,000-paper libraries for performance work. Distinguish model
  population, paint duration, event-loop timing and compositor/display FPS in reports.
- Source, fixtures, assets, installer definitions and docs are versioned; build/dist/backups
  are local outputs. Unknown files and previous deliveries are retained unless verified.
  Before recursive cleanup validate absolute boundaries/reparse points and save a manifest.
- Use scoped Git checkpoints before structural changes. Do not overwrite existing user edits.

- Follow the [development handbook](docs/development/README.md) and
  [coding standards](docs/development/coding-standards.md). Keep the existing useful
  GitHub/Python tree; do not create empty template directories. Track source, assets,
  fixtures, installer definitions and docs; ignore local environments, caches, build,
  dist, work, backups and release binaries. Preserve .venv; remove superseded deliveries only when explicitly requested or verified, with a manifest.
- Use MAJOR.MINOR.PATCH; user-visible changes go in CHANGELOG Unreleased. Each release
  has docs/releases/vX.Y.Z.md with factual dates, changes, validation and known limits.
  Do not invent releases/tags or bump versions for routine maintenance. Follow
  [release workflow](releases/README.md); archive verified releases separately from dist.
- Documentation flows README -> docs/README -> docs/development/README -> topic pages.
  Maintain one authoritative page per topic, relative Markdown links and return links.
  Update affected docs with code and check links with scripts/check_docs.py.
- At the end of EVERY development/fix/optimization/documentation task, perform the
  [maintenance checklist](docs/development/maintenance.md): run scripts/clean.ps1
  (default preview), then -Apply for verified bytecode; delete other proven task-generated waste using a separately validated manifest, inspect Git status
  and ignored tracked files. Unknown/untracked user files are not deletion candidates.
  Never use broad cleanup of build/dist/releases or delete source/QML/user/Zotero data.
- Follow [testing](docs/development/testing.md); final reports must distinguish passed,
  failed and unexecuted checks and state cleanup deletions/retentions and manifest paths.

- The current first baseline is v1.0.0. Follow [version evolution](docs/development/versioning.md);
  every future version must explain its changes, extension points, validation and remaining limits.
  Keep one master development handbook and mutually linked topic branches; do not recreate obsolete version pages.
