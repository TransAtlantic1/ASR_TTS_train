# Jellycat Data Cleaning Report

## Summary Table

`UNKNOWN` means the value was not computed in this pass or cannot be inferred without running a later stage. No full ASR was run and no `/inspire/qb-ilm/project/...` data was modified.

| stage_name | language_normalized | language_aliases | input_manifest_or_root | output_manifest_or_root | num_utts_before | hours_before | num_utts_after | hours_after | delta_hours | retained_ratio | script_entry | notes |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| raw_to_utterance | zh | `ZH`, `zh`, `zh-cn`, `zh-CN`, `zh-ch`, `zh-hans`, `zh-tw`, `zh-yue`, `zh-yue-hk` | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data/manifest_{zh,zh-cn}.jsonl` | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz` | 27,932,297 | 115,101.10 | 26,697,838 | 111,230.13 | -3,870.97 | 0.9664 | `data_cleaning/raw_to_utterance/run_prepare_jellycat_zh_shards.sh` | Before values come from historical raw reports; after values come from `jellycat_ZH_segments.summary.json`. |
| raw_to_utterance | en | `EN`, `en`, `en-us`, `en-US` | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data/manifest_en-us.jsonl` | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz` | 26,424,704 | 90,780.10 | 25,066,601 | 86,406.45 | -4,373.65 | 0.9518 | `data_cleaning/raw_to_utterance/run_prepare_jellycat_en_shards.sh` | Before values come from historical raw reports; after values come from `jellycat_EN_segments.summary.json`. |
| manifest_policy_filter | zh | `ZH`, `zh`, `zh-cn`, `zh-CN`, `zh-ch`, `zh-hans`, `zh-tw`, `zh-yue`, `zh-yue-hk` | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz` | `data_cleaning/manifest_policy_filter/outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.reject.jsonl` pending merge sidecar; source manifest unchanged | 26,694,858 | 111,076.45 | 26,304,883 | 110,026.23 | -1,050.22 | 0.9905 | `data_cleaning/manifest_policy_filter/build_jellycat_policy_rejects.py` | Candidate result if pending reject is merged: `<0.5s` 2,042 / 0.24h; `>45s` 0 / 0.00h; bracket-after-duration 387,933 / 1,049.98h. |
| manifest_policy_filter | en | `EN`, `en`, `en-us`, `en-US` | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz` | `data_cleaning/manifest_policy_filter/outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.reject.jsonl` pending merge sidecar; source manifest unchanged | 25,066,305 | 86,364.06 | 24,852,552 | 86,128.85 | -235.21 | 0.9973 | `data_cleaning/manifest_policy_filter/build_jellycat_policy_rejects.py` | Candidate result if pending reject is merged: `<0.5s` 78,083 / 9.83h; `>45s` 0 / 0.00h; bracket-after-duration 135,670 / 225.38h. |
| ASR_second | zh | `ZH`, `zh`, `zh-cn`, `zh-CN`, `zh-ch`, `zh-hans`, `zh-tw`, `zh-yue`, `zh-yue-hk` | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz` | smoke: `data_cleaning/ASR_second/smoke_outputs`; full template: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/asr_hyp/qwen3_asr_1p7b` | 26,694,858 | 111,076.45 | 3 smoke records | UNKNOWN | UNKNOWN | UNKNOWN | `data_cleaning/ASR_second/verify_edit_data.py` | Current manifest count/hours confirmed by the 2026-05-27 read-only policy scan. This task did not modify the manifest or start a full ASR run. 4090 smoke completed earlier: 3/3 ZH records succeeded, mean pinyin-tone3 WER `0.21523493118177503`, mean CER `0.23206555349412492`. |
| ASR_second | en | `EN`, `en`, `en-us`, `en-US` | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz` | smoke: `data_cleaning/ASR_second/smoke_outputs`; full template: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/asr_hyp/qwen3_asr_1p7b` | 25,066,305 | 86,364.06 | 3 smoke records | UNKNOWN | UNKNOWN | UNKNOWN | `data_cleaning/ASR_second/verify_edit_data.py` | Current manifest count/hours confirmed by the 2026-05-27 read-only policy scan. This task did not modify the manifest or start a full ASR run. 4090 smoke completed earlier: 3/3 EN records succeeded, mean WER `0.04062229904926534`. |

## Scope And Data Roots

Fixed Jellycat workspace:

```text
/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat
```

Fixed data-cleaning root:

```text
/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat/data_cleaning
```

Do not use the dataset root-level `data_cleaning` directory. Analysis is separate from data-cleaning stages and will live under:

```text
/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat/analysis
```

Read-only data roots:

```text
/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data
/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat
```

## raw_to_utterance

Purpose: cut raw long-form podcast audio and raw manifests into utterance FLAC files, segment manifests, Lhotse manifests, and per-podcast manifests. Content policy filtering now belongs to `manifest_policy_filter`; raw-to-utterance only rejects records that cannot be sliced or whose audio cut fails.

Current scripts:

```text
data_cleaning/raw_to_utterance/prepare_jellycat.py
data_cleaning/raw_to_utterance/prepare_jellycat_zh.py
data_cleaning/raw_to_utterance/prepare_jellycat_en.py
data_cleaning/raw_to_utterance/run_prepare_jellycat_zh.sh
data_cleaning/raw_to_utterance/run_prepare_jellycat_en.sh
data_cleaning/raw_to_utterance/run_prepare_jellycat_zh_shards.sh
data_cleaning/raw_to_utterance/run_prepare_jellycat_en_shards.sh
data_cleaning/raw_to_utterance/finalize_jellycat_en_outputs.sh
data_cleaning/raw_to_utterance/merge_jellycat_sharded_manifests.py
data_cleaning/raw_to_utterance/write_jellycat_podcast_manifests.py
data_cleaning/raw_to_utterance/show_jellycat_progress.py
data_cleaning/raw_to_utterance/tests/
```

Validation scripts are under `data_cleaning/raw_to_utterance/tests`. Sample runners write to the local workspace sample directories only when explicitly run.

Legacy scripts are preserved under `data_cleaning/raw_to_utterance/legacy` pending output-equivalence confirmation. They were not deleted in this turn.

## manifest_policy_filter

Purpose: generate standalone policy reject sidecars, filter JSONL by explicit reject ids, recompute context fields after reject filtering, merge reject JSONLs manually, and generate language/full-readme summaries.

Current scripts:

```text
data_cleaning/manifest_policy_filter/build_jellycat_policy_rejects.py
data_cleaning/manifest_policy_filter/merge_reject_jsonl.py
data_cleaning/manifest_policy_filter/generate_jellycat_reject_list.py
data_cleaning/manifest_policy_filter/filter_jsonl_by_reject_list.py
data_cleaning/manifest_policy_filter/add_jellycat_context_fields.py
data_cleaning/manifest_policy_filter/apply_jellycat_duration45_reject_context.py
data_cleaning/manifest_policy_filter/write_jellycat_full_readme.py
```

Current pending policy reject sidecar generated on 2026-05-27 UTC:

```text
data_cleaning/manifest_policy_filter/outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.reject.jsonl
data_cleaning/manifest_policy_filter/outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.summary.json
```

This is a standalone pending-merge reject list. It did not overwrite or rewrite the current EN/ZH `segments` manifests used by `ASR_second/test/h200_run_full_serial_nohup.sh`.

`merge_reject_jsonl.py` can now also synchronize podcast-level manifests when called with `--language`, `--podcast-root`, and `--output-podcast-root`; it writes filtered podcast JSONLs with recomputed context and can optionally write a matching merged segment manifest with `--segment-output`. It can also filter Lhotse CutSet JSONL.GZ files with paired `--cut-input` / `--cut-output` arguments; cuts are rejected when `cut.id`, `recording.id`, or any `supervisions[].id/recording_id` matches the merged reject ids.

| Language | Input records | Input hours | `<0.5s` records/hours | `>45s` records/hours | Bracket-after-duration records/hours | Pending reject records/hours | Candidate kept records/hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EN | 25,066,305 | 86,364.06 | 78,083 / 9.83h | 0 / 0.00h | 135,670 / 225.38h | 213,753 / 235.21h | 24,852,552 / 86,128.85h |
| ZH | 26,694,858 | 111,076.45 | 2,042 / 0.24h | 0 / 0.00h | 387,933 / 1,049.98h | 389,975 / 1,050.22h | 26,304,883 / 110,026.23h |
| Total | 51,761,163 | 197,440.51 | 80,125 / 10.07h | 0 / 0.00h | 523,603 / 1,275.36h | 603,728 / 1,285.43h | 51,157,435 / 196,155.08h |

Previous exploratory duration sidecars:

| Language | Broad sidecar | Broad count | Strict sidecar | Strict count |
| --- | --- | ---: | --- | ---: |
| ZH | `jellycat_ZH_reject_candidates.duration_gt_60s.jsonl` | 1,787 | `jellycat_ZH_reject_candidates.duration_gt_60s.chars_per_sec_lt_1p0.jsonl` | 1,112 |
| EN | `jellycat_EN_reject_candidates.duration_gt_60s.jsonl` | 239 | `jellycat_EN_reject_candidates.duration_gt_60s.chars_per_sec_lt_1p0.jsonl` | 80 |

## ASR_second

Purpose: Qwen3-ASR service deployment, ASR hyp generation, WER/CER scoring, and verification output.

Directory and script names are intentionally preserved:

```text
data_cleaning/ASR_second/launch_qwen3_asr.sh
data_cleaning/ASR_second/example_qwen3_asr_vllm.py
data_cleaning/ASR_second/verify_edit_data.py
```

Confirmed inputs:

```text
ASR_INPUT_MANIFEST_ZH=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz
ASR_INPUT_MANIFEST_EN=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz
```

Field mapping:

| Meaning | Field |
| --- | --- |
| id | `id` |
| wav | `wav` |
| reference text | `text` |
| language | `language` |
| duration | `duration` |

Read-only sampling confirmed `wav` is relative in both ZH and EN manifests. `verify_edit_data.py` now supports `--audio_root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat` and resolves relative paths as `audio_root / record["wav"]`; absolute `wav` values are used as-is.

Output boundary:

| Run type | Output |
| --- | --- |
| smoke | `data_cleaning/ASR_second/smoke_outputs` |
| full | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/asr_hyp/qwen3_asr_1p7b` |

Full ASR annotation is not allowed in this turn.

4090 smoke completed on 2026-05-15 after installing the missing runtime/scoring dependencies into `meanaudio2`.

| Item | Value |
| --- | --- |
| service command | `qwen-asr-serve` |
| actual GPU / port | `CUDA_VISIBLE_DEVICES=0`, `PORTS=8000` |
| launch settings | `GPU_MEMORY_UTILIZATION=0.85`, `TENSOR_PARALLEL_SIZE=1`, `MAX_MODEL_LEN=4096` |
| sidecar output | `data_cleaning/ASR_second/smoke_outputs/qwen3_asr_1p7b_smoke.jsonl` |
| failed output | `data_cleaning/ASR_second/smoke_outputs/failed.jsonl` |
| total result | 6 records succeeded, 0 failed |
| ZH result | 3 records, mean pinyin-tone3 WER `0.21523493118177503`, mean CER `0.23206555349412492` |
| EN result | 3 records, mean WER `0.04062229904926534` |

The smoke service was stopped after completion. No full hyp output was written under `/inspire/qb-ilm/project/...`.

## analysis Directory

`analysis` is not a `data_cleaning` stage. The old dataset-level analysis directory has been moved to:

```text
dataset/Jellycat/analysis/manifest_policy_filter
```

Current structure:

```text
analysis/manifest_policy_filter/analyze_jellycat_language_stats.py
analysis/manifest_policy_filter/jellycat_language_stats.md
analysis/manifest_policy_filter/figures/
```

Future WER figures and scripts should go to:

```text
dataset/Jellycat/analysis/ASR_second
```

Allowed analysis subdirectories are only `raw_to_utterance`, `manifest_policy_filter`, and `ASR_second`.

## Blockers / Questions

- `readme/` has been removed after explicit user confirmation. The useful old markdown content is covered by the consolidated top-level `README.md`.
- Qwen3-ASR model files were downloaded to `model/Qwen3-ASR-1.7B`; `.gitignore` excludes `model/`.
- `verify_edit_data.py` now supports `.jsonl` / `.jsonl.gz` manifest input, `--audio_root`, `--dry-run`, `--limit`, `--timeout`, `--max-retries`, `--ports`, `--workers-per-port`, sidecar `--output`, and `--failed-output`.
- The first Prompt 3 pass incorrectly read like the smoke was complete; it had only completed preflight and found missing dependencies. After the explicit install request, the real 4090 smoke completed successfully.
- `qwen-asr[vllm]` installation changed `meanaudio2` by upgrading key packages including `torch==2.9.1+cu128`, `transformers==4.57.6`, and `vllm==0.14.0`; keep this in mind before using that environment for unrelated runs.
- The provided ASR input paths are named `segments`. The 2026-05-27 pending policy scan found `0` records with `duration >45s`, `80,125` records / `10.07h` with `duration <0.5s`, and `523,603` records / `1,275.36h` with bracket spans after duration filtering. The scan generated only a pending reject sidecar; it did not modify the current ASR manifests.

## Reproducibility Commands

Static validation for this reorganization:

```bash
python -m py_compile data_cleaning/raw_to_utterance/*.py data_cleaning/raw_to_utterance/legacy/*.py data_cleaning/raw_to_utterance/tests/*.py data_cleaning/manifest_policy_filter/*.py data_cleaning/ASR_second/*.py
bash -n data_cleaning/raw_to_utterance/*.sh data_cleaning/raw_to_utterance/tests/*.sh data_cleaning/ASR_second/*.sh
python data_cleaning/ASR_second/verify_edit_data.py --help
DRY_RUN=1 CUDA_VISIBLE_DEVICES=0 PORTS=8000 ASR_ENV=meanaudio2 MAX_MODEL_LEN=4096 bash data_cleaning/ASR_second/launch_qwen3_asr.sh
git diff --check
```

Raw-to-utterance examples:

```bash
bash dataset/Jellycat/data_cleaning/raw_to_utterance/tests/run_sample_prepare.sh
bash dataset/Jellycat/data_cleaning/raw_to_utterance/tests/run_sample_prepare_en.sh
bash dataset/Jellycat/data_cleaning/raw_to_utterance/run_prepare_jellycat_zh_shards.sh
bash dataset/Jellycat/data_cleaning/raw_to_utterance/run_prepare_jellycat_en_shards.sh
```

Manifest policy examples:

```bash
python dataset/Jellycat/data_cleaning/manifest_policy_filter/generate_jellycat_reject_list.py --language ZH --podcast-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/ZH --output-dir /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH --duration-threshold 60 --chars-per-sec-threshold 1.0
python dataset/Jellycat/data_cleaning/manifest_policy_filter/filter_jsonl_by_reject_list.py --reject-jsonl /path/to/reject.jsonl --input /path/to/input.jsonl.gz --output /path/to/output.filtered.jsonl.gz
```

H200 full-ASR service command template only; do not execute in this turn:

```bash
conda activate meanaudio2
export CUDA_VISIBLE_DEVICES=<H200_GPU_ID>

MODEL_PATH=/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat/model/Qwen3-ASR-1.7B
PORT=8000
GPU_MEMORY_UTILIZATION=0.85
TENSOR_PARALLEL_SIZE=1
RUN_ID=$(date -u '+%Y%m%d-%H%M%S')
LOG_DIR=/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat/data_cleaning/ASR_second/logs/h200_${RUN_ID}
mkdir -p "$LOG_DIR"
qwen-asr-serve "$MODEL_PATH" --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" --host 0.0.0.0 --port "$PORT" --tensor-parallel-size "$TENSOR_PARALLEL_SIZE" > "$LOG_DIR/h200_port${PORT}.log" 2>&1 &
echo "pid=$!"
```
