# Jellycat VAD ASR Backfill Workflow

Date: 2026-05-06

## Current Policy

- `duration > 60s`: reject the parent utterance directly.
- `30s < duration <= 60s`: run Silero VAD on the existing W-level FLAC and keep natural speech spans.
- Post-VAD child `duration > 30s`: reject that child.
- Child text is not split from parent text. Kept child rows have empty `text` until ASR/annotation fills it.
- VAD timestamps are offsets inside the parent W segment. When materializing child audio, cut from the raw episode audio with:
  `raw_cut_source_wav = source_wav`,
  `raw_cut_start_time = parent.source_start_time + vad_start_time`,
  `raw_cut_end_time = parent.source_start_time + vad_end_time`.

## Artifact Meanings

`parent_reject.jsonl`

Parent-level rows to drop. This includes direct `duration_gt_60s` rejects and parents whose VAD children all got rejected.

`child_reject.post_vad_duration_gt_30s.jsonl`

Child-level VAD spans that were produced by VAD but still exceed 30 seconds. These are audit/reject rows, not rows to train on.

`all_reject.jsonl`

Union of parent rejects and child rejects. Keep it separate from the original first-pass `jellycat_<LANG>_rejected.jsonl.gz`.

`vad_split_map.jsonl`

One row per split parent with kept children. This is the replacement map used by backfill: drop the parent row and write all kept child segment rows instead. It also records rejected children for audit.

`vad_annotation_segments.jsonl`

Flat row-per-VAD-child file for downstream cutting and ASR. It includes `source_jsonl_index`, `source_text`, `parent_text`, `vad_start_time`, `vad_end_time`, raw-cut fields, and `post_vad_action`. Kept rows are the input to child-audio cutting and VibeVoice ASR.

## Scripts

Silero source checkout:

`Jellycat/prepare_data/external/silero-vad/`

Policy generation:

```bash
python3 Jellycat/prepare_data/generate_jellycat_manifest_vad_policy.py \
  --language ZH \
  --segment-manifest /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz \
  --vad-backend silero \
  --output-dir /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/duration60_vad30_manifest_only_v1 \
  --write-vad-candidates \
  --write-manifest-preview
```

For full runs, use `--num-shards` and `--shard-index`; do not run the full 6.44M VAD candidates as one unsharded process.

Cut kept child audio from raw source episodes:

```bash
python3 Jellycat/prepare_data/cut_jellycat_vad_annotation_audio.py \
  --annotation-jsonl <vad_annotation_segments.jsonl> \
  --output-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat \
  --audio-list-output <vad_child_audio_list.txt>
```

Run VibeVoice ASR without modifying the VibeVoice repository:

```bash
python3 Jellycat/prepare_data/transcribe_jellycat_vad_audio_list_with_vibevoice.py \
  --audio-list <vad_child_audio_list.txt> \
  --vibevoice-root /inspire/hdd/project/embodied-multimodality/chenxie-25019/zhikang/codes/VibeVoice \
  --url http://localhost:8000 \
  --workers-per-url 32 \
  --skip-existing
```

The wrapper writes sidecar JSON next to each child FLAC:

`.../ZH_P000000_S00002_W00000027_V0001.flac -> .../ZH_P000000_S00002_W00000027_V0001.json`

Backfill ASR text into manifests:

```bash
python3 Jellycat/prepare_data/backfill_jellycat_vad_asr_results.py \
  --language ZH \
  --segment-manifest /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz \
  --split-map-jsonl <vad_split_map.jsonl> \
  --parent-reject-jsonl <parent_reject.jsonl> \
  --output-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat \
  --segment-output <jellycat_ZH_segments.duration60_vad30_asr.jsonl.gz> \
  --recordings-output <jellycat_ZH_recordings.duration60_vad30_asr.jsonl.gz> \
  --supervisions-output <jellycat_ZH_supervisions.duration60_vad30_asr.jsonl.gz>
```

For full data, keep VAD generation, child cutting, ASR, and backfill shard-aligned. The current backfill script loads the split map into memory, so full unsharded split maps should be avoided.

When `--supervisions-output` is used, the script stores all non-standard segment metadata in supervision `custom`, including VAD offsets, raw-cut fields, ASR sidecar path, and prefix/suffix context fields.

Rewrite stage7-before Lhotse `MonoCut` files:

```bash
python3 Jellycat/prepare_data/rewrite_jellycat_lhotse_cuts_vad_policy.py \
  --reject-jsonl <parent_reject.jsonl> \
  --split-map-jsonl <vad_split_map.jsonl> \
  --child-segment-jsonl <jellycat_ZH_segments.duration60_vad30_asr.jsonl.gz> \
  --input-jsonl /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_zh_24k/data/fbank/zh/jellycat_zh_cuts_train_raw.jsonl.gz \
  --output-dir <versioned_stage7_output_dir> \
  --audio-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat \
  --require-audio-exists
```

The same command can take multiple `--input-jsonl` files, for example the merged raw cut file and the `train_split_1000/*.jsonl.gz` shards. It writes versioned copies into `--output-dir`; it never modifies the input cut files. For a split parent cut, the script writes child cut ids as `<child_id>-0` and updates the nested recording and supervision ids, durations, recording source path, text, and supervision `custom` metadata.

## Runtime Estimates

Pre-VAD candidate counts:

- ZH: 3,132,739 candidates, 32,186.04 hours.
- EN: 3,307,843 candidates, 33,351.05 hours.
- Total: 6,440,582 candidates, 65,537.09 hours.

Silero smoke on 1,000 ZH source rows processed 128 VAD candidates in about 39-40 seconds, roughly 0.31 seconds per candidate on one process. That extrapolates to about 23 days single-process. Ideal wall time is about 9 hours at 64 workers or 4-5 hours at 128 workers, but storage and raw FLAC decode overhead will likely push this higher.

The same smoke kept 628 child spans from 128 candidates, with kept child duration about 86.5% of candidate duration. A rough extrapolation is about 31.6M kept child files and 56.7k hours of ASR audio across ZH+EN. Existing VibeVoice benchmark files show an audio-duration lower bound around 35-40 hours with 8 services on large batches, but millions of short child files will add request/file overhead. A 10k-100k child pilot is needed before treating the full ASR estimate as reliable; practical full ASR time may be several days.

## Validated Smoke

- Silero backend import/model load works from `Jellycat/prepare_data/external/silero-vad`.
- VAD policy smoke on 1,000 ZH rows produced 628 kept children and 12 post-VAD child rejects.
- Raw-source cutting smoke wrote 10 child FLACs from `source_wav` using raw-cut timestamps; first checked child was 24 kHz mono and 4.5 seconds.
- Backfill smoke with fake VibeVoice sidecars replaced one split parent with 5 child rows and filled child `text` from sidecar JSON.
- Empty audio-list VibeVoice wrapper smoke imported the external VibeVoice helper; the wrapper now disables bytecode writes before import so future runs do not create Python cache files under that checkout.
- Stage7 raw-cut rewrite smoke on the first 6 ZH `MonoCut` rows replaced one split parent with 5 child cuts, yielding 10 output cuts. The first child cut had consistent cut id, nested recording/supervision ids, duration, child FLAC source, ASR text, and raw-cut/VAD metadata in supervision `custom`.
