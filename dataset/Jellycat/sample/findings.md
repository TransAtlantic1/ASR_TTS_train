# Jellycat VAD Long-Audio Sample Findings

## Candidate Sources

- ZH VAD candidates:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/duration60_vad30_manifest_only_v1_prevad_classify_only/jellycat_ZH_duration60_vad30_manifest_only_v1_prevad_classify_only.vad_candidates.duration_gt_30s_le_60s.jsonl`
- EN VAD candidates:
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/duration60_vad30_manifest_only_v1_prevad_classify_only/jellycat_EN_duration60_vad30_manifest_only_v1_prevad_classify_only.vad_candidates.duration_gt_30s_le_60s.jsonl`

## Definition

- `needs VAD` means `30.0 < duration <= 60.0` from the pre-VAD classify-only manifests.

## Errors

- The local AGENTS note references `skill/planning.md`, but that file is not present in the dataset directory.
- A first streaming sampler checked source audio existence for every candidate row and was too slow; it was stopped before copying. The final sampler uses random candidate line numbers first, then validates only selected source files.

## Final Sample

- Output directory: `Jellycat/sample/long_audio`
- Selection metadata:
  - `selected_vad_long_audio_10.jsonl`
  - `selected_vad_long_audio_10.md`
  - `selected_vad_long_audio_10.summary.json`
- Selected count: 10
- Unique podcasts: 10
- Language split: 5 ZH, 5 EN
- Duration range from metadata: 32.03s to 40.32s
