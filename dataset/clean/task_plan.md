# Task Plan: Dataset Workspace Cleanup

## Goal

Clean and organize the dataset workspace, archive superseded VAD/ASR scripts,
place this cleanup task's planning files under `dataset/clean`, commit only
task-owned dataset changes, and push the commit to the remote branch.

## Current Phase

Phase 5

## Phases

### Phase 1: Inspect Workspace

- [x] Check git status before making changes.
- [x] Identify dataset-owned untracked files.
- [x] Identify runtime/generated files to ignore.
- **Status:** complete

### Phase 2: Organize Files

- [x] Leave old planning files in their original locations.
- [x] Create current planning files under `clean/`.
- [x] Move superseded VAD/ASR scripts and docs under `backup_scripts/`.
- [x] Add ignore rules for caches, logs, and local external checkouts.
- **Status:** complete

### Phase 3: Verify Cleanup

- [x] Run syntax checks for active scripts.
- [x] Inspect dataset-only git status.
- [x] Review staged file list before commit.
- **Status:** complete

### Phase 4: Commit And Push

- [x] Stage only task-owned dataset paths explicitly.
- [x] Commit with a short imperative subject.
- [x] Push the current branch to `origin`.
- **Status:** complete

### Phase 5: Handoff

- [x] Record final commit hash and push result.
- [x] Report files changed, checks run, and skipped or excluded paths.
- **Status:** complete

## Key Questions

1. Which paths should be excluded from the dataset commit?
   Answer: runtime caches, Jellycat logs, and local external dependency
   checkouts are excluded by `.gitignore`.
2. Should unrelated repository changes outside `dataset/` be included?
   Answer: no; stage only explicit dataset paths.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Put current cleanup planning files directly under `clean/` | Matches the requested planning location for this work. |
| Do not archive old planning files | User clarified old planning files should not be archived; preserve them in place instead. |
| Move superseded VAD/ASR scripts to `Jellycat/prepare_data/backup_scripts/vad_asr_20260506/` | Keeps the old work available without presenting it as the active production path. |
| Ignore `Jellycat/logs/` and `Jellycat/prepare_data/external/` | They are runtime/local dependency artifacts and should not be committed. |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| Sandbox bwrap failed on local reads | 1 | Used approved escalation for read-only filesystem and git commands. |
