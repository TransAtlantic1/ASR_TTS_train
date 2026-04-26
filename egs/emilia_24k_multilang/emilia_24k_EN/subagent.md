# Subagent Records

## 2026-04-24 - bootstrap worker / current session

- Session reference: bootstrap worker / current session.
- Assigned task: planning/bootstrap for Emilia EN stage-7 repair context; run planning catchup, ensure planning files and subagent log exist, record user conclusions, establish stage plan, and log git risks.
- Current status: completed.
- Completion summary: ran `planning-with-files` session catchup successfully with no stdout, updated `task_plan.md`, `findings.md`, and `progress.md` without overwriting existing useful content, created this `subagent.md`, recorded the stage-7/stage-9 conclusions and dirty-worktree risks, and made no business-code or data changes.

## 2026-04-24 - task C bad shard scan / current session

- Session reference: main agent current session.
- Assigned task: read-only scan of Emilia EN processed stage-7 shards under the public train_split_1000 directory; write only validation reports listing shards missing `features` or `num_frames`.
- Current status: completed.
- Completion summary: scanned 821 matching `emilia_en_cuts_train.[0-9][0-9][0-9][0-9].jsonl.gz` shards with streaming gzip/json parsing, wrote TSV and bad-shard index list under `../experiments/main_flow_validation/emilia24k/`, found 821 bad shards and no gzip/json errors; `0122` matched the expected missing `num_frames` pattern, while `0000` was absent from the target directory and therefore not scanned.

## 2026-04-24 - task D features-aware bad shard scan / current session

- Session reference: main agent current session.
- Assigned task: correct Task C shard-scan criterion by validating `features` and `features.num_frames` only; write reports and planning records without changing business code or data shards.
- Current status: completed.
- Completion summary: Task D corrected scan: 821 matched processed shards, 0 bad shards by features-aware rule, 0 read/json errors. Report `../experiments/main_flow_validation/emilia24k/bad_shards_en_stage7_scan_features.tsv`; list `../experiments/main_flow_validation/emilia24k/bad_shards_en_stage7_scan_features.txt`. Bad idx first: (none); last: (none); 0000 present: no. Task D sanity: 0000=absent; 0122=total_cuts=18137, missing_features=0, non_dict_features=0, missing_features_num_frames=0, missing_either=0, error=none; 0023=total_cuts=18137, missing_features=0, non_dict_features=0, missing_features_num_frames=0, missing_either=0, error=none. If 0000 is absent, prior user evidence for 0000 was not reused.

## Task E - compute_and_store_features_batch None analysis
- Status: in_progress
- Scope: read-only log/code analysis for stage7 feature compute failures; no business-code edits, no data mutation, no stage7/stage9 execution.
- Started: 2026-04-24 19:03:58 UTC
- Status: completed
- Completion summary: read-only analysis found the most likely `None` path: shard `0000` is entirely 32 kHz; F5TTS features use a 24 kHz frame shift; Lhotse validates feature manifests with `sampling_rate=32000` in an unobserved background save future, leaving the in-memory writer empty and returning `None`. Details appended to `findings.md` and `progress.md`.

## 2026-04-24 - Task F1 planning status update / current session

- Session reference: main agent current session.
- Assigned task: update planning-with-files state only; append this subagent record and update `progress.md`, `findings.md`, and `task_plan.md` with the latest shard-status and `None`-path conclusions.
- Current status: completed.
- Completion summary: planning files only were updated. Recorded that 821 existing processed shards are currently good under the corrected `features` / `features.num_frames` rule, 179 processed shards are missing relative to 1000 raw shards, the old Task C 821-bad-shard conclusion was a top-level `num_frames` false positive and must not be used for deletion, the likely `None` path is hidden Lhotse background save-worker `validate_features` failure with an empty in-memory writer, and data deletion/rerun phases remain blocked pending code fix plus explicit authorization.

## 2026-04-24 - Task G local background stage7 repair / current session

- Session reference: main agent current session.
- Assigned task: generate a shard-list for the 179 missing Emilia EN processed train shards, launch local background stage7 repair, and let the wrapper rebuild the merged manifest via stage9 only after stage7 succeeds.
- PID/status: `1660703`, alive at launch check.
- Run dir: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/emilia/fc71e07/icefall_emilia_en_24k/orchestration/stage4_10/en/repair_missing_stage7_20260424T194521Z`.
- Log paths: main log `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/emilia/fc71e07/icefall_emilia_en_24k/orchestration/stage4_10/en/repair_missing_stage7_20260424T194521Z/repair_missing_stage7.log`; verification summary `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/emilia/fc71e07/icefall_emilia_en_24k/orchestration/stage4_10/en/repair_missing_stage7_20260424T194521Z/verification_summary.txt`.
- Current status: launched; do not wait for stage7 completion in this task.
- Completion summary: diffed 1000 raw shard ids against 821 processed shard ids, verified 179 missing processed shards, wrote `missing_processed_shards.txt`, created wrapper `run_repair_missing_stage7.sh`, launched it with `nohup`, wrote PID to the run dir, and confirmed the process was alive immediately after launch.

## 2026-04-24 - Task G2 local GPU missing-shard repair / current session

- Session reference: main agent current session.
- Assigned task: after confirming no existing `run_data_pipeline.sh`, `compute_emilia_features.py`, or `repair_missing_stage7` process, generate the 179-missing-shard list, launch local GPU stage7 repair with `--feature-device cuda`, and let the wrapper rebuild the merged manifest via stage9 only after stage7 succeeds.
- PID/status: `1793015`, alive at immediate launch check and still alive after the launch shell exited.
- Run dir: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/emilia/fc71e07/icefall_emilia_en_24k/orchestration/stage4_10/en/repair_missing_stage7_gpu_20260424T195224Z`.
- Missing list: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/emilia/fc71e07/icefall_emilia_en_24k/orchestration/stage4_10/en/repair_missing_stage7_gpu_20260424T195224Z/missing_processed_shards.txt`, count `179`.
- Wrapper/log: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/emilia/fc71e07/icefall_emilia_en_24k/orchestration/stage4_10/en/repair_missing_stage7_gpu_20260424T195224Z/run_repair_missing_stage7_gpu.sh`; `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/emilia/fc71e07/icefall_emilia_en_24k/orchestration/stage4_10/en/repair_missing_stage7_gpu_20260424T195224Z/repair_missing_stage7_gpu.log`.
- Current status: launched and running; do not wait for stage7 completion in this task.
- Completion summary: prelaunch `pgrep` found no matching existing process, raw/processed/missing counts were `1000/821/179`, wrapper records environment and runs `bash ASR/run_data_pipeline.sh --language en --stage 7 --stop-stage 7 --feature-num-splits 1000 --feature-shard-list <missing list> --feature-device cuda`, then moves the merged manifest only after stage7 success and runs stage9, then writes `verification_summary.txt`. The first launch PID `1748347` exited during the environment probe with no traceback; the wrapper verification Python quoting was corrected and the same run dir was relaunched via `nohup setsid`.
