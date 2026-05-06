# Jellycat VAD Cleanup Plan

Date: 2026-05-06 UTC

## Confirmed Scope

- Scripts should be language-generic.
- This task should run against current official `ZH` and `EN` only.
- Do not modify `raw_data`.
- Do not full re-cut all Jellycat audio.
- Operate on versioned Jellycat manifests and new child FLACs only. VAD runs on
  already cut W-level FLACs, but VAD child FLACs are materialized from the
  raw source episode using `source_wav` and shifted source timestamps.
- Produce versioned outputs first; promote only after validation.
- Detailed ASR/backfill flow:
  `analysis/jellycat_vad_asr_backfill_workflow.md`.

## Current Inputs

Official Jellycat manifests:

- `ZH`: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz`
- `EN`: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz`

Official language roots:

- `ZH`: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/ZH`
- `EN`: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/EN`

Stage7-before ZH raw cuts path:

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_zh_24k/data/fbank/zh`

## Policy

For each accepted utterance:

- `duration <= 30s`: keep unchanged.
- `30s < duration <= 60s`: run VAD on the already cut utterance FLAC and split by natural speech spans.
- `duration > 60s`: reject directly.
- After VAD splitting, if any child span is still `>30s`, reject that child.

The final post-policy impact should be reported separately from simple threshold simulations:

- dropping all `duration > 30s`
- dropping all `duration > 60s`
- dropping final post-policy rejects after VAD

## Split Naming

VAD child ids and filenames keep the original `W` stem and add a child suffix:

```text
ZH_P000000_S00000_W00000123_V0001
ZH_P000000_S00000_W00000123_V0002
```

Example files:

```text
ZH/ZH_P000000/ZH_P000000_S00000/flac/ZH_P000000_S00000_W00000123_V0001.flac
ZH/ZH_P000000/ZH_P000000_S00000/flac/ZH_P000000_S00000_W00000123_V0002.flac
```

Add split metadata to child manifest rows:

```json
{
  "parent_id": "ZH_P000000_S00000_W00000123",
  "vad_split_index": 1,
  "vad_split_count": 2,
  "vad_start_time": 0.42,
  "vad_end_time": 12.73
}
```

`source_start_time` and `source_end_time` should be shifted to the original
episode timeline:

```text
child.source_start_time = parent.source_start_time + vad_start_time
child.source_end_time = parent.source_start_time + vad_end_time
```

## Versioned Output Layout

Recommended version suffix:

```text
vadclean_v1
```

Recommended manifest outputs:

```text
manifests/<LANG>/vadclean_v1/jellycat_<LANG>_segments.vadclean_v1.jsonl.gz
manifests/<LANG>/vadclean_v1/jellycat_<LANG>_recordings.vadclean_v1.jsonl.gz
manifests/<LANG>/vadclean_v1/jellycat_<LANG>_supervisions.vadclean_v1.jsonl.gz
manifests/<LANG>/vadclean_v1/jellycat_<LANG>_vad_rejected.vadclean_v1.jsonl
manifests/<LANG>/vadclean_v1/jellycat_<LANG>_vad_split_map.vadclean_v1.jsonl
manifests/<LANG>/vadclean_v1/jellycat_<LANG>_vadclean_v1.summary.json
```

Recommended audio policy:

- Keep original `<=30s` audio paths unchanged.
- Write only VAD child FLAC files as new files beside the original parent FLAC.
- Cut VAD child FLACs from `source_wav` using
  `parent.source_start_time + vad_start_time` and
  `parent.source_start_time + vad_end_time`, not from the already cut W FLAC.
- Do not delete original parent FLAC files during the versioned run.
- Directly rejected `>60s` parent FLAC files remain on disk until a later promote/cleanup step.

## VAD Tooling

Preferred production backend:

- Silero VAD, because it is language-independent and operationally simple for podcast speech spans.
- A source checkout is available at
  `Jellycat/prepare_data/external/silero-vad/`.

Current local fallback:

- The current script also has an energy-based fallback for smoke/debug use.

Implementation should expose:

```text
--vad-backend silero|energy
```

Do not silently install dependencies. If Silero is selected and unavailable,
fail with an install instruction unless the user has explicitly approved a
network install.

## Manifest Rewrite Surfaces

Primary Jellycat outputs to rewrite:

- segment manifest
- Lhotse recordings manifest
- Lhotse supervisions manifest
- podcast-level JSONLs

Stage7-before raw cut outputs to rewrite:

- merged raw cuts: `jellycat_zh_cuts_train_raw.jsonl.gz`
- split raw cuts: `train_split_1000/jellycat_zh_cuts_train_raw.####.jsonl.gz`

For Lhotse `MonoCut` stage7 rows, one old line can become multiple child lines.
Each child line must update:

- top-level `id`
- top-level `duration`
- nested `supervisions[0].id`
- nested `supervisions[0].recording_id`
- nested `supervisions[0].duration`
- nested `supervisions[0].custom`
- nested `recording.id`
- nested `recording.sources[0].source`
- nested `recording.num_samples`
- nested `recording.duration`

## Rewrite Inputs

Use explicit parameterized inputs:

```text
--reject-jsonl /path/to/reject.jsonl
--split-map-jsonl /path/to/split_map.jsonl
--child-segment-jsonl /path/to/asr_backfilled_segments.jsonl.gz
--input /path/to/input1.jsonl.gz
--input /path/to/input2.jsonl.gz
--output-dir /path/to/versioned_output
```

`reject-jsonl` removes old ids.

`split-map-jsonl` maps one parent id to one or more child manifest/cut rows.

Stage7-before Lhotse raw cuts are handled by:

```text
Jellycat/prepare_data/rewrite_jellycat_lhotse_cuts_vad_policy.py
```

This script accepts one or more `--input-jsonl` `MonoCut` files and writes
versioned outputs. Parent rejects are dropped; split parent cuts become one
child `MonoCut` per kept VAD child. If `--child-segment-jsonl` is provided,
ASR-backfilled child segment rows override the split-map child payloads so
stage7 cuts receive the final child `text` and metadata.

## Prefix/Suffix Context Fields

Add context fields to total segment manifests and podcast-level manifests:

```json
{
  "prefix_context": {
    "id": "...",
    "wav": "...",
    "start_time": 12.3,
    "end_time": 18.9,
    "duration": 6.6,
    "speaker": "...",
    "text": "..."
  },
  "prefix_far": true,
  "suffix_context": null,
  "suffix_far": null
}
```

Semantics:

- Context means nearest annotated accepted utterance in the same source episode.
- No context: context field is `null`, far field is `null`.
- Far threshold: 30 seconds.
- If context exists and gap is `>30s`, keep the context object and set `*_far` to `true`.
- If context exists and gap is `<=30s`, set `*_far` to `false`.

Use `source_wav` as the primary episode grouping key, with
`source_episode_hash` as a useful metadata fallback/check.

## Validation

Minimum checks before promotion:

- line count reconciliation:
  `new_count = old_count - direct_rejected_parent_count - dropped_child_count + kept_child_count - split_parent_count`
- no duplicate ids
- all `wav` paths exist
- all FLAC headers match `sampling_rate`, `num_samples`, and `duration`
- all Lhotse recordings and supervisions have matching ids and durations
- all stage7 raw cuts have matching nested recording/supervision ids
- no post-policy item has `duration > 30s`
- context fields are present on every segment and podcast row
- context far/null semantics match the 30s threshold
