# Dataset Cleanup Findings

## Workspace State

- Repository root: `/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train`.
- Dataset root: `/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset`.
- `dataset/` had no tracked files before this cleanup; `git status --short -- .`
  reported `?? ./`.
- The wider repository has many unrelated modified/deleted paths outside
  `dataset/`; those are treated as user work and excluded from this commit.

## Cleanup Scope

- Active production script kept in the main prepare-data script folder:
  `Jellycat/prepare_data/apply_jellycat_duration45_reject_context.py`.
- Superseded VAD/ASR scripts are archived under:
  `Jellycat/prepare_data/backup_scripts/vad_asr_20260506/`.
- Previous Jellycat planning files are left in their original locations; user
  clarified they should not be archived.
- Current cleanup planning files live under:
  `clean/`.

## Excluded Runtime Artifacts

- `Jellycat/logs/` is a runtime log directory.
- `Jellycat/prepare_data/external/` contains a local Silero checkout from the
  superseded VAD path.
- Python bytecode and notebook checkpoints are ignored.
