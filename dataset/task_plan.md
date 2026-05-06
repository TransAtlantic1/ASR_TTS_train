# Jellycat Multi-Language Cleanup Plan

Created: 2026-05-06 UTC

## Goal

Plan and implement a multi-language Jellycat workflow for:

- language-level duration/statistics tables and plots under `analysis/`
- generic reject/split rules around long utterances
- VAD splitting for 30-60s utterances, direct reject for >60s utterances
- manifest/audio updates before downstream stage7 inputs without touching `raw_data`
- generic multi-language preparation code replacing separate ZH/EN prepare scripts
- README documentation for screening, VAD, reject, split, and context-audio fields
- prefix/suffix annotated-audio context fields in total manifests and podcast manifests

## Current Active Goal Status

Closed as deferred on 2026-05-06 after the user redirected the work to dataset
workspace cleanup, commit, and push. The latest Jellycat production policy was
implemented and dry-run, but production application was not executed because it
requires explicit destructive-action approval before replacing manifests or
deleting FLAC files.

## Current Phase

Closed

## Constraints

- Do not modify `raw_data`.
- Avoid full re-cut of all audio. Only operate on already cut Jellycat outputs and manifests.
- Keep scripts multi-language: language should be a parameter, not hardcoded ZH/EN.
- Prefer parameterized input lists: reject JSONL plus one or more JSONL/JSONL.GZ files to update.
- Preserve unrelated user/git worktree changes.
- Put analysis outputs under `analysis/`; put runnable analysis recipes under `analysis/recipe/`.
- If a requirement is ambiguous or needs product/data-owner confirmation, ask the user directly before deciding.

## Original Phases

| Phase | Status | Deliverable |
|---|---|---|
| 1. Repository/workflow discovery | complete | ZH/EN manifests, EN summary, stage7 pre-input cut schema, and local VAD dependencies inspected |
| 2. Analysis design | complete | Multi-language stats script and full ZH/EN Markdown/PNG outputs under `analysis/` |
| 3. Reject/VAD design | complete | Concrete rule design for >60s reject and 30-60s VAD split/drop |
| 4. Manifest mutation design | complete | Added versioned segment/recording/supervision backfill, raw-source child audio cutting, VibeVoice audio-list transcription, and stage7 `MonoCut` rewrite scripts |
| 5. Multi-language preparation refactor plan | complete | Added generic `prepare_jellycat.py`; EN/ZH entrypoints are wrappers; tiny ZH/EN smoke outputs validated |
| 6. Context-audio fields design | complete | Prefix/suffix nearby annotated-audio fields and far/null semantics |
| 7. README/update plan | complete | Documentation locations and exact content to add |
| 8. Validation plan | complete | Smoke tests, line-count checks, audio checks, Lhotse consistency checks, and final py_compile completed for current scripts |

## Active Duration>=45s Production Phases

### Phase 1: Align Active Requirements

- [x] Record latest user direction: no VAD, no ASR relabeling, do not touch stage0-6.
- [x] Preserve reject rule: direct reject for `duration >= 45s`.
- [x] Preserve context rule: nearest prefix/suffix only; if nearest neighbor is rejected, context is `null`.
- **Status:** complete

### Phase 2: Implement And Dry-Run Duration>=45s Tooling

- [x] Add a generic ZH/EN script for reject/context application.
- [x] Syntax-check the script.
- [x] Run small ZH dry-run to verify reject-aware context nulling.
- [x] Run full ZH/EN dry-runs and record counts.
- **Status:** complete

### Phase 3: Production Apply Decision Deferred

- [x] Recognize production apply requires explicit user approval before replacing manifests or deleting FLACs.
- [x] Do not choose between manifest-only apply and `--delete-audio` without a new direct user instruction.
- [x] Leave target path confirmation for a future production-apply task.
- **Status:** complete

### Phase 4: Production Apply And Verification Deferred

- [x] Do not run ZH/EN apply commands in this cleanup/commit task.
- [x] Do not replace production manifests in this cleanup/commit task.
- [x] Do not delete FLAC files in this cleanup/commit task.
- [x] Document that verification remains part of a future production-apply task.
- **Status:** complete

### Phase 5: Handoff

- [x] Update `progress.md` with the deferred production-apply decision.
- [x] Report that destructive actions were skipped and require explicit future approval.
- **Status:** complete

## Initial Decisions

- Treat `jellycat_<LANG>_segments.jsonl.gz` as the source of truth for accepted already-cut utterances.
- Treat first-pass `jellycat_<LANG>_rejected.jsonl.gz` separately from second-pass hard reject lists.
- For cleanup, prefer producing new versioned manifests/audio dirs first, then atomically promote after validation.
- Do not delete or overwrite original manifests until counts and downstream compatibility are verified.
- Latest policy supersedes the earlier VAD/ASR production path unless the user
  explicitly reactivates it.

## Open Questions

- Deferred: Should the duration>=45s policy be applied with manifest rewrites
  only first, or with `--delete-audio` in the same run?
- Deferred: Confirm production target paths/backups for ZH and EN before
  replacing JSONLs or deleting FLACs.

## Confirmed User Answers

- Scripts should support arbitrary future languages; this task should only run ZH and EN.
- `analysis/` belongs at `/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/analysis`.
- Plots should be PNG; tables/reports should be Markdown.
- Impact summaries should include all three cases: dropping all `duration > 30s`, dropping only `duration > 60s`, and dropping the final post-policy reject set.
- VAD 30-60s should split by natural speech spans, not merge to a target max length.
- VAD dependencies may require network installation.
- Cleanup should first produce versioned outputs, then promote only after validation.
- Stage7-before path to inspect: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_zh_24k/data/fbank/zh`.
- Prefix/suffix context schema is accepted, and `text` should be included in each context object.
- VAD split child naming with `_V0001`, `_V0002`, ... is acceptable. Only strict validation scripts and documentation examples need to be corrected for this naming; do not treat it as a training-chain blocker.
- Immediate scope narrowed by user: stop further implementation for now; only keep the strict validator and documentation-example correction for `_V0001` child names.
- Immediate `_V0001` validator/docs correction is complete and validated on ZH/EN sample validators.
- Current active policy request: generate manifest-only `duration60_vad30_manifest_only_v1` outputs with `>60s` parent rejects, `30-60s` VAD split maps, post-VAD `>30s` child rejects, and flat annotation JSONL rows that preserve source JSONL index and source text while leaving child text empty.
- Completed non-final pre-VAD classify-only outputs for ZH/EN under `duration60_vad30_manifest_only_v1_prevad_classify_only`; these contain `>60s` parent rejects and `30-60s` VAD candidates only, and are intentionally named so they do not collide with first-pass rejected manifests or old `reject_candidates` files.
- User confirmed Silero VAD for the final post-VAD generation.
- User clarified final child-audio materialization semantics: VAD produces timestamps, and the child FLACs must be cut from raw source episode audio via `source_wav` plus shifted source timestamps, not from the already cut W-level FLAC.
- Added dataset-side scripts for raw-source child cutting, VibeVoice audio-list transcription, and ASR sidecar backfill. The VibeVoice repository is only read/called and is not modified.

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| Sandbox bwrap failed on repository mount | Initial read commands | Used approved escalation for read-only commands |
| `file` command unavailable | Verify generated PNGs | Used Pillow `Image.verify()` instead |
| VAD policy smoke test started full scan | Forgot `--max-records` support in new script | Killed the process, added `--max-records`, reran capped smoke test |
| `pip install silero-vad` unavailable / GitHub package install missing `hatchling` | Tried package install path | Used a local Silero source checkout under `Jellycat/prepare_data/external/silero-vad/` and direct source import |
| Looked up a stale `/tmp` Silero smoke summary name | Read wrong smoke summary path | Found the actual `*_silero_smoke_v2.summary.json` path and used that |
| Backfill-generated supervision `custom` was too narrow | Adversarial review of metadata preservation | Changed `make_supervision()` to preserve all non-standard segment metadata, then re-ran backfill smoke |
