# planning-with-files prompts for icefall

These prompts are meant for Codex with the `planning-with-files` skill enabled.

Usage:

1. Start Codex with the shared `CODEX_HOME`.
2. Open the `icefall` repository root.
3. Copy one of the prompts below into Codex.
4. Replace the task placeholder with your actual task.

Prompt files:

- `01-general.md`: Standard multi-step task prompt
- `02-general-short.md`: Shorter general-purpose prompt
- `03-bug-investigation.md`: Bug investigation and fix prompt
- `04-large-refactor.md`: Large refactor prompt

All prompts assume the current repository is `icefall`, so they reference:

- `icefall/` for shared library code
- `egs/<dataset>/<task>/...` for recipe-specific changes
- `test/` for repo-level tests
- `docs/` for documentation updates
