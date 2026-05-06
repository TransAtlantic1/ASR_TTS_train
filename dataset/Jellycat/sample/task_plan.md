# Jellycat VAD Long-Audio Sample Plan

Created: 2026-05-06 UTC

## Goal

Copy 10 audio files that need VAD into `Jellycat/sample/long_audio` for manual listening.

## Scope

- Use VAD candidates defined as `30s < duration <= 60s`.
- Prefer random sampling.
- Do not select two files from the same podcast.
- Write task planning/progress files under `Jellycat/sample/`, not the dataset root.

## Phases

| Phase | Status | Deliverable |
|---|---|---|
| 1. Locate candidate manifests | complete | ZH/EN pre-VAD candidate JSONLs found |
| 2. Sample unique podcasts | complete | 10 selected records with source paths |
| 3. Copy audio and metadata | complete | 10 FLACs plus selection manifest under `long_audio` |
| 4. Verify outputs | complete | File count, source existence, copied durations/sizes checked |

## Notes

- Existing `dataset/task_plan.md`, `dataset/findings.md`, and `dataset/progress.md` are from earlier work and should not be updated for this task.
- Sampling seed: `20260506`.
- Final selection is balanced across current analysis languages: 5 ZH and 5 EN.
