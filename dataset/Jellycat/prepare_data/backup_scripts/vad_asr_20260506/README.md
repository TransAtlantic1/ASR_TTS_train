# Archived VAD/ASR Scripts

This directory stores the superseded Jellycat VAD/ASR workflow scripts from
2026-05-06. They are retained for reference only.

The current active production cleanup path is the direct duration policy in:

`Jellycat/prepare_data/apply_jellycat_duration45_reject_context.py`

Archived scripts:

- `generate_jellycat_vad_policy_lists.py`
- `generate_jellycat_manifest_vad_policy.py`
- `cut_jellycat_vad_annotation_audio.py`
- `backfill_jellycat_vad_asr_results.py`
- `transcribe_jellycat_vad_audio_list_with_vibevoice.py`
- `rewrite_jellycat_lhotse_cuts_vad_policy.py`
- `rewrite_jsonl_by_reject_and_split_map.py`

Archived workflow notes are under `docs/`.

The local Silero checkout used during exploration is intentionally ignored via
`dataset/.gitignore` and is not part of this archive.
