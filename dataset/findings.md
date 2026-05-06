# Jellycat Findings

## Existing Context From `Jellycat_ZH_context_20260506.md`

- Repo root: `/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train`
- Dataset cwd: `/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset`
- Jellycat output root: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat`
- Jellycat ZH language root: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/ZH`
- Jellycat manifest root: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH`
- Raw data root: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data`

## Current ZH Manifest Semantics

- `jellycat_ZH_segments.jsonl.gz` is utterance/segment-level, not whole-podcast.
- Accepted rows map to already cut `W`-level FLAC files.
- Important fields: `wav`, `duration`, `source_wav`, `source_start_time`, `source_end_time`.
- Path layout: `ZH/ZH_P000000/ZH_P000000_S00000/flac/ZH_P000000_S00000_W00000003.flac`.
- Podcast-level JSONLs are generated from the segment manifest and live beside podcast audio directories.
- Podcast JSONL `wav` is relative to the language root, e.g. `ZH_P000000/.../flac/...flac`.

## Current ZH Counts

- Accepted segments: `26,697,838`
- First-pass rejected: `1,234,459`
- Lhotse recordings: `26,697,838`
- Lhotse supervisions: `26,697,838`
- Total duration: about `111,230.13h`
- Podcast manifests: `8,995`
- Max records per podcast: `293,903`

## Existing Hard-Reject Context

- Existing rule: `duration > 60s and chars_per_sec < 1.0`
- Broad `duration > 60s`: `1,787`
- Strict hard reject: `1,112`
- Root cause: some source manifest intervals are very long even when text is short; not a post-processing cut bug.
- First-pass `jellycat_ZH_rejected.jsonl.gz` is preparation-time rejects only and must stay separate from later cleanup lists.

## Existing Scripts

- `Jellycat/prepare_data/prepare_jellycat_zh.py`: ZH prepare/cut script.
- `Jellycat/prepare_data/prepare_jellycat_en.py`: EN prepare/cut script to inspect.
- `Jellycat/prepare_data/run_prepare_jellycat_zh_shards.sh`: full ZH sharded prepare launcher.
- `Jellycat/prepare_data/write_jellycat_podcast_manifests.py`: per-podcast JSONL writer.
- `Jellycat/prepare_data/generate_jellycat_reject_list.py`: current ZH-specific reject candidate generator.
- `Jellycat/prepare_data/filter_jsonl_by_reject_list.py`: generic JSONL filtering by explicit reject path.
- `Jellycat/prepare_data/merge_jellycat_sharded_manifests.py`: shard merger.

## Worktree Notes

- There are many unrelated uncommitted/deleted files outside this task.
- `dataset/Jellycat/` appears untracked in `git status`.
- Avoid reverting or broad cleanup.

## User Confirmations 2026-05-06

- Generic multi-language code is required for future languages, but this run should cover only `ZH` and `EN`.
- Analysis outputs go under `dataset/analysis`; analysis scripts go under `dataset/analysis/recipe`.
- Plot format: PNG. Tables/reports: Markdown.
- Long-data impact reporting should cover all of:
  - dropping all `duration > 30s`
  - dropping only `duration > 60s`
  - dropping the final policy rejects after `>60s` direct reject plus 30-60s VAD splitting and post-VAD `>30s` drops
- VAD split policy for 30-60s utterances: split by natural speech spans.
- VAD tooling may need network installation.
- Cleanup outputs should be versioned first; promote only after validation.
- Stage7-before fbank path to inspect:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_zh_24k/data/fbank/zh`

## Remaining Clarifications

- Need environment check before choosing VAD tool; if network install is needed, request explicit install approval.

## EN Manifest Status

- EN has official merged manifests under `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN`.
- EN accepted segments: `25,066,601`.
- EN first-pass rejected: `1,358,103`.
- EN total accepted duration: `311,063,213.42s`.
- EN podcast manifests exist: `3,511`.
- EN max records per podcast: `617,255`.

## Stage7-Before ZH Fbank Surface

- Path inspected:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_zh_24k/data/fbank/zh`
- Files include:
  - `jellycat_zh_cuts_train_raw.jsonl.gz`
  - `jellycat_zh_supervisions_train_norm.jsonl.gz`
  - `jellycat_zh_supervisions_train_norm_fixed.jsonl.gz`
  - `train_split_1000/jellycat_zh_cuts_train_raw.0000.jsonl.gz` through split shards
- Sample `jellycat_zh_cuts_train_raw.jsonl.gz` row is a Lhotse `MonoCut`.
- MonoCut top-level fields include `id`, `start`, `duration`, `channel`, `supervisions`, `recording`, `type`.
- Nested supervision includes `id`, `recording_id`, `start`, `duration`, `channel`, `text`, `language`, `speaker`, and `custom`.
- Nested recording includes `id`, `sources[].source`, `sampling_rate`, `num_samples`, `duration`.
- If an original utterance is VAD-split into multiple children, updating stage7-before cuts is not a simple reject-only filter; one old MonoCut line may need to be replaced by multiple child MonoCut lines with updated `id`, nested supervision id/recording_id, recording source path, samples, duration, and custom metadata.

## Local VAD Dependency Check

- Installed: `torch`, `torchaudio`, `onnxruntime`, `soundfile`.
- Not installed: `silero_vad`, `webrtcvad`.
- If using Silero VAD, likely need network install or use Torch Hub/model files if already cached; do not assume availability.

## Split ID/Path Compatibility Notes

- Active zipformer/Jellycat prep code inspected so far treats ids as strings and checks uniqueness and recording/supervision consistency, not a strict `_W\d+` regex.
- Stage7-before `MonoCut` rows use top-level cut ids like `<recording_id>-0`, while nested `recording.id` and `supervision.recording_id` use the utterance id.
- If a split child recording id is `ZH_P..._W00000123_V0001`, the corresponding raw cut id should be updated consistently, likely `ZH_P..._W00000123_V0001-0` in the Lhotse raw-cut file.
- User confirmed `_V0001` naming is acceptable; just correct strict validation scripts and documentation examples.
- Strict path/id format checks exist in Jellycat sample validators:
  - `Jellycat/test_prepare/validate_jellycat_sample.py`
  - `Jellycat/test_prepare/validate_jellycat_en_sample.py`
- README examples and validation regexes need to be updated if `_V0001` child names are accepted.

## Prefix/Suffix Context Schema Confirmation

- User accepted the proposed prefix/suffix schema.
- Include `text` inside context objects.
- Proposed fields remain:
  - `prefix_context`
  - `prefix_far`
  - `suffix_context`
  - `suffix_far`
- Context object should include at least `id`, `wav`, `start_time`, `end_time`, `duration`, `speaker`, and `text`.
- No context: context is `null`; far is `null`.
- Context farther than 30 seconds: context is still recorded; far is `true`.

## Manifest-Only Duration60/VAD30 Outputs

- Active policy name for final post-VAD outputs: `duration60_vad30_manifest_only_v1`.
- Pre-VAD classify-only outputs are intentionally separated under:
  `duration60_vad30_manifest_only_v1_prevad_classify_only`
  so they are not mistaken for final post-VAD child reject/split outputs.
- ZH pre-VAD classify-only output root:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/duration60_vad30_manifest_only_v1_prevad_classify_only/`
- ZH summary counts:
  - records seen: `26,697,838`
  - `duration > 60s` parent rejects: `1,787`
  - `30s < duration <= 60s` VAD candidates: `3,132,739`
  - unchanged `duration <= 30s`: `23,563,312`
- EN pre-VAD classify-only output root:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/duration60_vad30_manifest_only_v1_prevad_classify_only/`
- EN summary counts:
  - records seen: `25,066,601`
  - `duration > 60s` parent rejects: `239`
  - `30s < duration <= 60s` VAD candidates: `3,307,843`
  - unchanged `duration <= 30s`: `21,758,519`
- These pre-VAD outputs do not read audio and do not produce post-VAD child rejects or split maps.
- Final post-VAD generation remains blocked on VAD backend choice: use current local energy VAD, install/use Silero, or another confirmed backend.
- VAD annotation JSONL schema for final outputs:
  - one VAD child per row
  - includes `source_jsonl_index` and `source_jsonl_line_number`
  - includes `source_text` from the parent source JSONL row
  - leaves child `text` and `annotation_text` empty for later ASR annotation
  - includes `post_vad_action` (`keep` or `reject`) and `reject_reason`

## Silero Deployment and VAD Semantics

- User approved Silero VAD for the final post-VAD split/reject generation.
- Direct package install was not viable in this environment:
  - internal PyPI did not provide `silero-vad`
  - GitHub package install reached build dependency resolution but `hatchling` was unavailable
- Operational workaround: use a source checkout under
  `Jellycat/prepare_data/external/silero-vad/`.
- Direct source import and JIT model loading were verified from that checkout.
- Final semantics:
  - run VAD on the existing W-level Jellycat FLAC to get offsets inside the parent segment
  - write child metadata with `vad_start_time` / `vad_end_time`
  - compute child source timeline as `parent.source_start_time + vad_offset`
  - cut child audio from `source_wav` / raw episode audio using `raw_cut_start_time` and `raw_cut_end_time`

## VibeVoice Integration

- VibeVoice root inspected read-only:
  `/inspire/hdd/project/embodied-multimodality/chenxie-25019/zhikang/codes/VibeVoice`
- Do not modify that repository.
- Existing `transcribe_batch.py` can scan files/directories and writes same-directory `.json` sidecars, but it does not accept an explicit audio-list file.
- Added dataset-side wrapper:
  `Jellycat/prepare_data/transcribe_jellycat_vad_audio_list_with_vibevoice.py`
- The wrapper reads an explicit child-audio list, calls the existing VibeVoice API helper, and writes VibeVoice-style sidecar JSON next to each child FLAC.
- The wrapper uses worker processes rather than threads so VibeVoice helper stdout redirection is process-local and does not corrupt global stdout across concurrent calls.
- The wrapper sets `sys.dont_write_bytecode = True` before importing the external helper so future calls do not create bytecode files inside the VibeVoice checkout.

## ASR Backfill Scripts

- `Jellycat/prepare_data/cut_jellycat_vad_annotation_audio.py`
  - reads flat VAD annotation JSONL
  - cuts kept child FLACs from raw `source_wav`
  - writes an audio-list file for VibeVoice
- `Jellycat/prepare_data/backfill_jellycat_vad_asr_results.py`
  - reads the original segment manifest, VAD split map, parent reject lists, and child sidecar ASR JSONs
  - drops rejected parents
  - replaces split parent rows with kept child rows
  - fills child `text` / `annotation_text` from VibeVoice sidecar segments
  - can write updated segment, recordings, and supervisions JSONL/JSONL.GZ outputs
  - preserves all non-standard segment metadata inside supervision `custom`, including raw-cut fields, VAD fields, ASR JSON path, and prefix/suffix context fields
- Important scaling note: current backfill loads the split map into memory; use shard-aligned split maps for full data.

## Stage7-Before Cut Rewrite

- Added `Jellycat/prepare_data/rewrite_jellycat_lhotse_cuts_vad_policy.py`.
- Inputs:
  - one or more `--reject-jsonl`
  - one or more `--split-map-jsonl`
  - optional one or more `--child-segment-jsonl` with ASR-backfilled child rows
  - one or more `--input-jsonl` Lhotse `MonoCut` JSONL/JSONL.GZ files
  - `--output-dir` for versioned outputs
- Behavior:
  - drops old cuts whose recording id is in parent-level rejects
  - replaces split parent cuts with child cuts
  - child cut id is `<child_id>-0`
  - nested recording/supervision ids become `<child_id>`
  - duration, sample rate, sample count, recording source path, text, and supervision custom metadata are updated from the child segment row
  - input files are never modified
- Smoke test:
  - first 6 rows of ZH `jellycat_zh_cuts_train_raw.jsonl.gz`
  - one parent split into 5 children
  - output rows: `10`
  - first child row had consistent cut id, nested ids, duration, source path, ASR text, and raw-cut/VAD metadata.

## Runtime Estimates

- ZH+EN pre-VAD candidates: `6,440,582`.
- Candidate audio duration: about `65,537.09h`.
- Silero smoke speed: about `0.31s` per candidate on one process, so roughly `23 days` single-process. Idealized wall time is about `9h` with 64 workers or `4-5h` with 128 workers before I/O overhead.
- Smoke kept-child ratio: `628 / 128 = 4.91` kept child files per VAD candidate, and kept child duration was about `86.5%` of candidate duration.
- Rough extrapolation: about `31.6M` kept child files and `56.7k h` of VibeVoice ASR audio for ZH+EN.
- Existing VibeVoice benchmark summaries imply a lower bound around `35-40h` with 8 services on large batches, but millions of short child files will add substantial request/file overhead. A 10k-100k child pilot is needed for a reliable production estimate.

## Analysis Plot Semantics

- `analysis/ZH_duration_distribution.png` and `analysis/EN_duration_distribution.png` originally plotted record counts per duration bin.
- User clarified the duration distribution y-axis should be total audio duration per bin.
- Updated `analysis/recipe/analyze_jellycat_language_stats.py` so duration distribution charts plot total hours per duration bin; bar percentages are duration percentages.
- Markdown duration distribution tables now retain counts while adding `Hours` and `Duration percent`.
