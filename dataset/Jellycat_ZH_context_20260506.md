# Jellycat ZH Context Notes

Date: 2026-05-06 UTC

This document records the current Jellycat-ZH manifest work, generated
podcast-level JSONLs, duration checks, and hard-reject cleanup plan.

## Dataset Roots

- Repo root: `/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train`
- Jellycat output root:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat`
- Jellycat ZH language root:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/ZH`
- Jellycat ZH manifest root:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH`
- Raw data root:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data`

## Manifest Semantics

`jellycat_ZH_segments.jsonl.gz` is an utterance/segment-level manifest, not a
whole-podcast or whole-episode manifest.

Each accepted row maps to a cut `W`-level FLAC:

```text
ZH_P000000_S00000_W00000003.flac
```

ID levels:

- `P`: numeric podcast id
- `S`: episode-local speaker id under that podcast
- `W`: utterance id

Important fields:

- `wav`: target utterance FLAC path
- `duration`: target utterance duration
- `source_wav`: original source audio path
- `source_start_time` / `source_end_time`: source interval used for cutting

## Existing Official Manifests

Main manifest files:

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz`
- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_rejected.jsonl.gz`
- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_recordings.jsonl.gz`
- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_supervisions.jsonl.gz`
- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.summary.json`

Merged line counts from the summary:

```text
jellycat_ZH_segments      26,697,838
jellycat_ZH_rejected       1,234,459
jellycat_ZH_recordings    26,697,838
jellycat_ZH_supervisions  26,697,838
```

The first-pass rejected manifest is produced during preparation. It contains
items such as pure tag-only non-speech, invalid timestamps, and cut failures.
It is separate from the later hard-reject cleanup list described below.

## Podcast-Level JSONLs

Podcast-level JSONLs have been generated from the official segment manifest.

Output:

```text
/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/ZH/ZH_P000000.jsonl
/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/ZH/ZH_P000001.jsonl
...
```

Summary:

`/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.podcast_manifests.summary.json`

Generation result:

- Podcast JSONL files: `8,995`
- Total records: `26,697,838`
- Minimum records per podcast: `1`
- Maximum records per podcast: `293,903`

The main summary has also been updated with a `podcast_manifests` field.

Podcast-level JSONL path policy:

- File pattern: `ZH/ZH_P000000.jsonl`
- `wav` is relative to the `ZH/` language root, Emilia-style.
- Example `wav`:
  `ZH_P000000/ZH_P000000_S00000/flac/ZH_P000000_S00000_W00000003.flac`

Generation command:

```bash
python dataset/Jellycat/prepare_data/write_jellycat_podcast_manifests.py \
  --segment-manifest /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz \
  --output-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat \
  --language ZH \
  --summary /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.summary.json \
  --summary-output /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.podcast_manifests.summary.json \
  --progress-path dataset/Jellycat/logs/full_prepare_podcast_manifests.progress.json \
  --overwrite
```

Final progress file:

`dataset/Jellycat/logs/full_prepare_podcast_manifests.progress.json`

Final progress showed:

```text
phase          done
lines_seen     26,697,838
expected_lines 26,697,838
podcasts       8,995
percent        100.0
```

## Duration Distribution

The utterance duration distribution was computed from the generated
podcast-level JSONLs.

Result file:

`/tmp/jellycat_ZH_utterance_duration_distribution_from_podcasts.json`

Overall:

- Count: `26,697,838`
- Min duration: `0.01s`
- Max duration: `3281.43s`
- Mean duration: `14.998535s`
- Total duration: `111,230.13h`

Distribution:

| Duration | Count | Percent |
|---|---:|---:|
| `[0,1)` | 250,553 | 0.9385 |
| `[1,2)` | 1,711,939 | 6.4123 |
| `[2,3)` | 1,607,571 | 6.0214 |
| `[3,5)` | 2,493,964 | 9.3414 |
| `[5,10)` | 5,072,597 | 19.0000 |
| `[10,15)` | 5,680,283 | 21.2762 |
| `[15,20)` | 2,055,453 | 7.6989 |
| `[20,30)` | 4,681,270 | 17.5343 |
| `[30,45)` | 3,141,228 | 11.7659 |
| `[45,60)` | 1,193 | 0.0045 |
| `[60,90)` | 790 | 0.0030 |
| `[90,120)` | 338 | 0.0013 |
| `[120,+inf)` | 659 | 0.0025 |

Counts above 60 seconds:

```text
duration > 60s: 1,787
```

## Text-Length Over Time

Metric definitions:

- `text_len`: `len(text)`, Unicode codepoints
- `chars_per_sec`: `text_len / duration`

Full result:

`/tmp/jellycat_ZH_textlen_over_time_distribution.json`

Overall:

- Count: `26,697,838`
- Mean text length: `79.7441`
- Mean duration: `14.9985s`
- Mean chars/sec: `5.4279`
- Global chars/sec: `5.3168`

For `duration > 40s`:

- Count: `268,447`
- Mean text length: `204.0763`
- Mean duration: `41.9447s`
- Mean chars/sec: `5.0194`
- Global chars/sec: `4.8654`

For `duration > 60s`:

Result file:

`/tmp/jellycat_ZH_textlen_over_time_duration_gt60_distribution.json`

Summary:

- Count: `1,787`
- Mean text length: `313.3593`
- Mean duration: `275.3415s`
- Mean chars/sec: `1.8510`
- Global chars/sec: `1.1381`
- Min text length: `1`
- Max text length: `9,492`
- Min duration: `60.01s`
- Max duration: `3281.43s`

For `duration > 60s`, chars/sec distribution:

| chars/sec | Count | Percent |
|---|---:|---:|
| `[0,0.5)` | 940 | 52.6021 |
| `[0.5,1.0)` | 172 | 9.6251 |
| `[1.0,1.5)` | 101 | 5.6519 |
| `[1.5,2.0)` | 54 | 3.0218 |
| `[2.0,2.5)` | 47 | 2.6301 |
| `[2.5,3.0)` | 52 | 2.9099 |
| `[3.0,4.0)` | 68 | 3.8053 |
| `[4.0,5.0)` | 91 | 5.0923 |
| `[5.0,7.5)` | 218 | 12.1992 |
| `[7.5,10.0)` | 18 | 1.0073 |
| `[10.0,+inf)` | 26 | 1.4550 |

Observation:

Most `duration > 60s` items have low text density. `chars_per_sec < 1.0`
contains `1,112` rows, which is about `62.23%` of the `duration > 60s`
subset.

Examples of low-density abnormal rows:

```text
424.92s   text="行"
885.59s   text="好，那"
1364.13s  text="嗯，对，那。"
1001.62s  text="今天就到这。"
2497.62s  text="所以这个跟孩子能力有关系啊，嗯。"
```

## Long-Utterance Root Cause

Pure tag-only text such as `[Music]` and `[Silence]` is already handled by the
first-pass rejected manifest. The long-tail issue is different: some source
segments contain normal-looking text but their original `start_time` and
`end_time` span a long musical or program interval.

Example from raw source manifest:

```text
id: zh_e9a7e36e4672_00_00006
start_time: 124.4
end_time: 3405.83
duration: 3281.43
text: 我們就來欣賞第一樂章
```

This is not a post-processing cut bug. The source manifest itself assigns a
very long interval to a short prompt-like text.

## Hard-Reject Cleanup

Chosen hard reject rule:

```text
duration > 60s and chars_per_sec < 1.0
```

Generated files:

- Broad candidates:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_reject_candidates.duration_gt_60s.jsonl`
- Current hard reject list:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_reject_candidates.duration_gt_60s.chars_per_sec_lt_1p0.jsonl`
- Summary:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_reject_candidates.summary.json`

Counts:

- Broad `duration > 60s`: `1,787`
- Strict hard reject `duration > 60s and chars_per_sec < 1.0`: `1,112`

The hard reject list is intentionally separate from
`jellycat_ZH_rejected.jsonl.gz`.

Generate or regenerate:

```bash
python dataset/Jellycat/prepare_data/generate_jellycat_reject_list.py \
  --duration-threshold 60 \
  --chars-per-sec-threshold 1.0
```

Delete rows later by passing the reject JSONL explicitly:

```bash
python dataset/Jellycat/prepare_data/filter_jsonl_by_reject_list.py \
  --reject-jsonl /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_reject_candidates.duration_gt_60s.chars_per_sec_lt_1p0.jsonl \
  --input /path/to/input.jsonl.gz \
  --output /path/to/output.filtered.jsonl.gz
```

The parameterized `--reject-jsonl` path is intentional. It allows later cleanup
passes to choose a different reject list without changing the script.

## Scripts Added Or Updated

Podcast-level manifest generation:

- `dataset/Jellycat/prepare_data/write_jellycat_podcast_manifests.py`

Hard-reject list generation:

- `dataset/Jellycat/prepare_data/generate_jellycat_reject_list.py`

Parameterized JSONL filtering:

- `dataset/Jellycat/prepare_data/filter_jsonl_by_reject_list.py`

README/report files updated:

- `dataset/Jellycat/readme/Jellycat_ZH_data_report.md`
- `dataset/Jellycat/readme/Jellycat_ZH_full_dataset_readme.md`
