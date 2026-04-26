# Repository Guidelines

## Shared Baseline

The reusable baseline for agent behavior lives in
`../vibecoding_init/AGENTS.md`.
This file keeps the `icefall`-specific delta: repo structure, workflow
boundaries, validation paths, and active operational context.

If a child directory has its own `AGENTS.md`, treat it as a local delta.
Keep the root rules unless the child file explicitly narrows or overrides
them.

Use `prompts/planning-with-files/` for task planning prompts and
`prompts/review/adversarial-review.md` for final adversarial review.

## Highest Priority Constraint

This repository uses subagents selectively rather than by default:

- The main agent should directly handle short, localized tasks when the scope
  is clear: targeted reads, small edits, quick checks, or narrow command
  execution.
- Prefer the minimum viable number of subagents. Do not delegate simple tasks
  just to maintain a coordinator / worker split.
- Large-scale exploration of datasets or the codebase should be delegated to a
  subagent.
- Long-running verification, training/evaluation runs, or broad
  implementation work with a clean ownership boundary should be delegated to a
  subagent.
- When a subagent is created, ensure `subagent.md` exists in the current
  working directory. Create it if missing; otherwise append one record per
  subagent.
- Each `subagent.md` record should include the address or reference for the
  subagent session, the assigned task, and a brief completion summary or
  current status.
- Each delegated subagent should receive one complete, feedback-bearing task
  chain, not a vague partial instruction.
- Delegation prompts must spell out the goal, owned files or surfaces, commands
  or validations to run, expected deliverable, and the exact reply shape
  needed for acceptance.
- Choose the subagent model by difficulty: use `gpt-5.3-codex` for bounded
  lower-risk tasks when it is enough, and use a stronger/latest model only
  when the task complexity justifies it.
- After a subagent reaches `completed` or `failed`, the main agent must
  reclaim it and handle review, cleanup, and acceptance.
- The main agent owns discussion, planning, coordination, review, and final
  acceptance of subagent work.

## Project Structure

`icefall` is a Python speech-research repository with shared library code and
many dataset recipes.

- `icefall/`: reusable core modules.
- `egs/<dataset>/<task>/`: recipe code for data prep, training, decoding, and
  export.
- `test/`: repo-level unit tests and validation helpers.
- `docs/`: Sphinx documentation sources and build instructions.
- `asr_op/<domain>/`: watcher helpers and archived operational scripts.
- `prompts/`: reusable prompt files for planning and review flows.

Keep shared logic in `icefall/`. Keep recipe-specific logic under the relevant
`egs/...` tree.

## Build, Test, and Development Commands

- `python -m pip install -r requirements.txt`
- `python -m pip install -e .`
- `pre-commit install`
- `pre-commit run -a`
- `pytest -v -s ./test`
- `cd egs/<recipe> && pytest -v -s`
- `cd docs && make html`

Use the smallest relevant check first, then widen only as needed.

## Testing and Output Placement

- Put shared tests in `test/`. Put recipe-local tests near the code they
  exercise when that is the established pattern.
- Store validation scripts, logs, and result summaries under `test/`,
  `test/recipes/...`, or `../experiments/main_flow_validation/...`.
- Do not leave runtime outputs, watcher logs, caches, or temporary validation
  artifacts in recipe source trees.
- For recipe changes, record the command used and the key metric output, such
  as WER or CER.

## Current Workflow Notes

This repository is organized around a smaller stable mainline and an
experiment-only validation path.

Current cleanup path:

1. Review uncommitted changes first and leave unrelated user edits untouched.
2. Keep mainline docs short. `README.md` and `RUNBOOK.md` should describe only
   the current stable prep/train/decode/export path.
3. Move historical smoke scripts, watcher helpers, and one-off operational
   steps out of recipe mainlines.
4. Back up removed or heavily simplified docs/scripts before replacing them.
5. Put minimal real-data validation under
   `../experiments/main_flow_validation/...`, not under recipe `data/`,
   `download/`, or public artifact roots.
6. Keep watcher scripts under `asr_op/.../watcher` and validation scripts
   under `test/recipes/...`.

Current moved-script locations:

- GigaSpeech watcher scripts: `asr_op/giagspeech/watcher/`
- Emilia watcher scripts: `asr_op/emilia/watcher/`
- GigaSpeech historical docs and removed helpers:
  `asr_op/giagspeech/backup/`
- Emilia historical docs and removed helpers: `asr_op/emilia/backup/`
- Minimal validation recipes:
  `test/recipes/giga16k/`, `test/recipes/giga24k/`,
  `test/recipes/emilia24k/`

If you are looking for a removed middle-step script, search in this order:

1. `asr_op/<domain>/watcher/`
2. `test/recipes/<recipe>/`
3. `asr_op/<domain>/backup/`

Current experiment-only validation roots:

- `../experiments/main_flow_validation/giga16k/`
- `../experiments/main_flow_validation/giga24k/`
- `../experiments/main_flow_validation/emilia24k/`

Recent validated command chains:

- `giga16k`:
  `prepare_minimal_real_data.sh -> run_smoke_train.sh -> run_decode_export.sh -> validate_outputs.py`
- `giga24k`:
  `prepare_minimal_real_data.sh -> run_smoke_train.sh -> run_decode_export.sh -> validate_outputs.py`
- `emilia24k`:
  `prepare_minimal_real_data.sh -> run_smoke_train.sh -> run_decode_export.sh -> validate_outputs.py`

## Commit and Review Notes

- Target `master` unless a maintainer says otherwise.
- Follow the shared baseline for git hygiene, ignore rules, and adversarial
  review.
- Root-level agent guidance is now tracked in git. Keep recipe-level
  `AGENTS.md` files focused on local deltas rather than re-stating global
  rules.
- When a change affects prep/train/decode/export behavior, run the project
  review prompt in `prompts/review/adversarial-review.md` before handoff.

## Emilia 24k Public Cutover

`egs/emilia_24k_multilang/emilia_24k_{ZH,EN}/ASR/emilia24k_ops/` contains the
temporary cutover helpers for the public Emilia 24k artifact.

Current storage layout:

- Active public entry:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/emilia/fc71e07/icefall_emilia_zh_24k`
- Old real data:
  `/inspire/hdd/project/embodied-multimodality/public/emilia/fc71e07/icefall_emilia_zh_24k`
- New flat real data:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/icefall_emilia_zh_24k`

Cutover phases:

1. `activate_qbilm_public_symlink_mode.sh`
2. `sync_qbilm_real_root_from_old.sh`
3. `run_public_stage7_when_ready.sh` or `run_public_stage7_shard_list.sh`
4. Final symlink flip after stage7 is idle, audio-cache validation passes, and
   required non-audio files are ready.

Notes:

- Follow minimal edits. Do not refactor whole code paths unless the task
  requires it.
- After large logic changes, update interfaces, data storage paths, and
  filenames so they still match the code.
- `rewrite_public_artifact_paths.py` is legacy and is not part of the current
  audio-cache-only migration flow.
- Current migration helpers should move only `audio_cache/`. Metadata,
  manifests, `.lca`, `logs`, and `locks` stay outside this flow.
- `run_public_stage7_shard_list_when_audio_ready.sh` uses
  `verify_public_stage7_audio_ready.py` to gate shard-list launches on cached
  audio presence.
- `clean_public_stage7_manifests.py` is the temporary repair tool for removing
  `_sp0.9` / `_sp1.1` cuts and bad cuts with
  `supervision_end > cut_duration`.

Current dual-line data status:

- The old HDD root is the temporary salvage line. Keep its existing `.lca`
  files only for transitional reuse while cleaning old manifests and rerunning
  failed shards.
- On the old HDD root, `cuts_train.*.jsonl.gz` must be cleaned to remove
  `_sp0.9` / `_sp1.1` cuts and bad cuts with
  `supervision_end > cut_duration`. For unfinished shards, clean
  `cuts_train_raw.*.jsonl.gz` first and rerun only those shards.
- The new qb-ilm real root is the clean rerun line. Copy only `audio_cache/`;
  any required non-audio files must be generated or staged separately.
- Do not treat old-root `.lca` and new-root `.lca` as interchangeable. The
  new-root rerun is the only line intended to become the final clean training
  set.
- The old copy-first and metadata-migration scripts are intentionally removed
  once the audio-cache-only symlink flow is in place.
