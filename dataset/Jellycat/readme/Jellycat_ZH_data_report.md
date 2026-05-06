# Jellycat ZH Data Preparation Report

## Overview

Jellycat ZH merges the source `zh` and `zh-cn` podcast segments under:

`/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data`

into a single target language directory:

`/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/ZH`

The source audio is already 24 kHz mono FLAC. The preparation step cuts utterance-level FLAC files from the existing segment manifests:

- `manifest_zh.jsonl`
- `manifest_zh-cn.jsonl`

## Target Layout

```text
Jellycat/
|-- ZH/
|   |-- ZH_P000000.jsonl
|   `-- ZH_P000000/
|       `-- ZH_P000000_S00000/
|           `-- flac/
|               |-- ZH_P000000_S00000_W00000000.flac
|               `-- ZH_P000000_S00000_W00000000_V0001.flac  # optional VAD child from the same W
`-- manifests/
    `-- ZH/
        |-- jellycat_ZH_segments.jsonl.gz
        |-- jellycat_ZH_rejected.jsonl.gz
        |-- jellycat_ZH_recordings.jsonl.gz
        |-- jellycat_ZH_supervisions.jsonl.gz
        |-- jellycat_ZH_segments.podcast_manifests.summary.json
        `-- jellycat_ZH_segments.summary.json
```

`P` is the numeric podcast id, `S` is the numeric episode-local speaker id under that podcast, and `W` is the numeric utterance id. Source hashes are kept in manifest metadata rather than in audio paths.

## Manifest Schema

The main segment manifest has one accepted speech utterance per line:

```json
{
  "id": "ZH_P000001_S00000_W00000001",
  "wav": "ZH/ZH_P000001/ZH_P000001_S00000/flac/ZH_P000001_S00000_W00000001.flac",
  "text": "想象出一个闪闪发光的人，然后让他带着你往自己喜欢的方向走下去。这个就是我想到这个话题的契机。",
  "duration": 10.43,
  "sampling_rate": 24000,
  "num_samples": 250320,
  "language": "ZH",
  "source_language": "zh-cn",
  "podcast": "ZH_P000001",
  "speaker": "ZH_P000001_S00000",
  "source_manifest_id": "zh-cn_9472bbb624f3_00_00001",
  "source_podcast_hash": "00108f4205f66a6489d4e8a102ad2ae8",
  "source_episode_hash": "9472bbb624f3fded7e9e47fb8ea4dbc1",
  "source_speaker": "spk_0",
  "source_wav": "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data/zh-cn/00108f4205f66a6489d4e8a102ad2ae8/audios/2025/9472bbb624f3fded7e9e47fb8ea4dbc1.flac",
  "source_start_time": 1.66,
  "source_end_time": 12.09,
  "source_duration": 10.43
}
```

VAD child rows use the same schema, with the original `W` stem retained and
`_V0001`, `_V0002`, ... appended to both `id` and `wav`, for example
`ZH_P000001_S00000_W00000001_V0001`.

Pure non-speech tags such as `[Music]` and `[Silence]` are not written as training audio. They are written to `jellycat_ZH_rejected.jsonl.gz` with a `reason` field for audit.

This first-pass `jellycat_ZH_rejected.jsonl.gz` is different from the later hard-reject list for abnormal long utterances. The first pass only records items rejected during initial preparation, such as pure tag-only non-speech, invalid timestamps, or cut failures.

Lhotse-compatible `RecordingSet` and `SupervisionSet` manifests are also written beside the segment manifest.

The final `duration` is derived from the written FLAC header as `num_samples / sampling_rate`, matching the Emilia 24k stage4 policy of correcting recording metadata from real audio frames and keeping supervision duration bounded by the real recording duration.

## Podcast-level Manifests

The official single-file segment manifest can be split into one JSONL file per podcast without re-cutting audio:

```bash
python dataset/Jellycat/prepare_data/write_jellycat_podcast_manifests.py \
  --segment-manifest /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz \
  --output-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat \
  --language ZH \
  --summary /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.summary.json \
  --summary-output /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.podcast_manifests.summary.json
```

Default output:

```text
ZH/
|-- ZH_P000000.jsonl
|-- ZH_P000000/
|   `-- ZH_P000000_S00000/
|       `-- flac/
`-- ...
```

Each `ZH_Pxxxxxx.jsonl` is the podcast-level equivalent of Emilia's batch-level JSONL layout. It sits beside the same-name audio directory, and each `wav` is relative to the `ZH/` language root, for example `ZH_P000000/ZH_P000000_S00000/flac/ZH_P000000_S00000_W00000000.flac`.

If a 30-60s utterance is split by VAD, child utterances keep the same original
`W` stem and add `_V0001`, `_V0002`, ... to both `id` and FLAC filename, for
example `ZH_P000000_S00000_W00000000_V0001.flac`.

## Hard Reject List For Stage7-After Cleanup

For the current cleanup pass, the chosen hard reject rule is:

- `duration > 60s and chars_per_sec < 1.0`

This rule is intentionally stored outside the first-pass rejected manifest so downstream stages can finish first and the actual deletion can happen later.

Generated files:

- First-pass rejected manifest from preparation:
  `jellycat_ZH_rejected.jsonl.gz`
- Second-pass hard reject candidates (`duration > 60s` broad list):
  `jellycat_ZH_reject_candidates.duration_gt_60s.jsonl`
- Second-pass hard reject list actually selected for cleanup:
  `jellycat_ZH_reject_candidates.duration_gt_60s.chars_per_sec_lt_1p0.jsonl`
- Summary:
  `jellycat_ZH_reject_candidates.summary.json`

Current paths:

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_rejected.jsonl.gz`
- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_reject_candidates.duration_gt_60s.jsonl`
- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_reject_candidates.duration_gt_60s.chars_per_sec_lt_1p0.jsonl`
- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_reject_candidates.summary.json`

To generate or regenerate the second-pass reject files:

```bash
python dataset/Jellycat/prepare_data/generate_jellycat_reject_list.py \
  --duration-threshold 60 \
  --chars-per-sec-threshold 1.0
```

To delete these ids after stage7 or any later step, pass the reject JSONL path explicitly:

```bash
python dataset/Jellycat/prepare_data/filter_jsonl_by_reject_list.py \
  --reject-jsonl /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_reject_candidates.duration_gt_60s.chars_per_sec_lt_1p0.jsonl \
  --input /path/to/input.jsonl.gz \
  --output /path/to/output.filtered.jsonl.gz
```

This parameterized form is intentional: the cleanup step should not hardcode one reject file, and different later passes may choose different reject lists.

## VAD Cleanup Policy

The next cleanup policy is language-generic:

- keep `duration <= 30s` unchanged
- run VAD on already cut utterance FLACs with `30s < duration <= 60s`
- directly reject `duration > 60s`
- reject any VAD child that remains `duration > 30s`
- name VAD children by appending `_V0001`, `_V0002`, ... to the original `W` stem
- write versioned outputs first, then promote only after validation
- never modify `raw_data`

## Commands

Small sample:

```bash
bash dataset/Jellycat/test_prepare/run_sample_prepare.sh
```

Full preparation:

```bash
bash dataset/Jellycat/prepare_data/run_prepare_jellycat_zh.sh
```

Sharded full preparation example:

```bash
NUM_SHARDS=100 SHARD_INDEX=0 bash dataset/Jellycat/prepare_data/run_prepare_jellycat_zh.sh
```

When `NUM_SHARDS>1`, output manifest files automatically receive a shard suffix such as `jellycat_ZH_segments.shard00000-of-00100.jsonl.gz`.

## Validation

The sample validation checks:

- each manifest entry points to an existing FLAC file
- audio is 24 kHz mono
- FLAC frame count exactly matches `num_samples`
- segment, Lhotse recording, and Lhotse supervision durations all equal `num_samples / sampling_rate`
- `wav` uses `ZH/ZH_Pxxxxxx/ZH_Pxxxxxx_Sxxxxx/flac/ZH_Pxxxxxx_Sxxxxx_Wxxxxxxxx.flac`
  for original utterances and may use `_V0001`, `_V0002`, ... child suffixes after VAD splitting
- source podcast / episode / speaker identifiers remain available in manifest metadata
- pure non-speech tags are excluded from the speech manifest
- Lhotse recordings and supervisions match the segment count

Sample results are written to:

`dataset/Jellycat/sample/manifests/ZH/validation_summary.json`

## Sample Run Results

Command:

```bash
bash dataset/Jellycat/test_prepare/run_sample_prepare.sh
```

Result:

| Metric | Value |
|---|---:|
| Accepted speech utterances | 16 |
| Source `zh` utterances | 8 |
| Source `zh-cn` utterances | 8 |
| Rejected non-speech tag segments | 2 |
| Total accepted duration | 308.37 sec |

The sample passed validation. The sample output is under:

`dataset/Jellycat/sample`

## Numeric ID Bound Check

A read-only full scan of `manifest_zh.jsonl` and `manifest_zh-cn.jsonl` confirmed the current numeric widths are sufficient:

| ID level | Format | Max observed | Limit | Status |
|---|---:|---:|---:|---|
| Podcast | `ZH_P%06d` | 8,994 | 999,999 | pass |
| Speaker per podcast | `S%05d` | 4,581 | 99,999 | pass |
| Utterance | `W%08d` | 98,000,115 | 99,999,999 | pass |

Accepted utterances scanned: 26,704,531. No accepted source IDs required the CRC fallback path.
