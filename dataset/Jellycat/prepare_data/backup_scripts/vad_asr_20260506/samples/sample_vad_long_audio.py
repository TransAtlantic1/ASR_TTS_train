#!/usr/bin/env python3
"""Sample Jellycat long utterances that need VAD and copy their FLACs."""

from __future__ import annotations

import json
import random
import shutil
from pathlib import Path
from typing import Iterable


SEED = 20260506
PER_LANGUAGE = 5
OVERSAMPLE_PER_LANGUAGE = 2000

SAMPLE_ROOT = Path(__file__).resolve().parent
TARGET_DIR = SAMPLE_ROOT / "long_audio"
JELLYCAT_ROOT = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat"
)

SUMMARIES = {
    "ZH": Path(
        "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/"
        "Jellycat/manifests/ZH/duration60_vad30_manifest_only_v1_prevad_classify_only/"
        "jellycat_ZH_duration60_vad30_manifest_only_v1_prevad_classify_only.summary.json"
    ),
    "EN": Path(
        "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/"
        "Jellycat/manifests/EN/duration60_vad30_manifest_only_v1_prevad_classify_only/"
        "jellycat_EN_duration60_vad30_manifest_only_v1_prevad_classify_only.summary.json"
    ),
}


def load_summary(language: str) -> dict:
    with SUMMARIES[language].open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_audio_path(wav: str, language: str) -> Path:
    wav_path = Path(wav)
    if wav_path.is_absolute():
        return wav_path

    candidates = [JELLYCAT_ROOT / wav_path]
    parts = wav_path.parts
    if parts and parts[0] == language:
        candidates.append(JELLYCAT_ROOT / Path(*parts[1:]))
    else:
        candidates.append(JELLYCAT_ROOT / language / wav_path)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def selected_jsonl_rows(path: Path, line_numbers: Iterable[int]) -> list[tuple[int, dict]]:
    wanted = sorted(set(line_numbers))
    rows: list[tuple[int, dict]] = []
    if not wanted:
        return rows

    wanted_index = 0
    next_line = wanted[wanted_index]
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if line_no < next_line:
                continue
            if line_no == next_line:
                rows.append((line_no, json.loads(line)))
                wanted_index += 1
                if wanted_index >= len(wanted):
                    break
                next_line = wanted[wanted_index]
    return rows


def sample_language(language: str, rng: random.Random) -> tuple[list[dict], dict]:
    summary = load_summary(language)
    candidate_path = Path(summary["outputs"]["vad_candidates"])
    candidate_count = int(summary["stats"]["vad_candidates"])
    sample_size = min(candidate_count, OVERSAMPLE_PER_LANGUAGE)
    line_numbers = rng.sample(range(1, candidate_count + 1), sample_size)
    rows = selected_jsonl_rows(candidate_path, line_numbers)
    rng.shuffle(rows)

    selected: list[dict] = []
    used_podcasts: set[str] = set()
    missing_audio = 0
    skipped_duplicate_podcast = 0
    skipped_wrong_duration = 0

    for line_no, row in rows:
        duration = float(row.get("duration_sec", row.get("duration", 0.0)) or 0.0)
        if not (30.0 < duration <= 60.0):
            skipped_wrong_duration += 1
            continue
        podcast = row.get("podcast") or row.get("id", "").split("_S", 1)[0]
        if podcast in used_podcasts:
            skipped_duplicate_podcast += 1
            continue
        src = resolve_audio_path(str(row.get("wav", "")), language)
        if not src.is_file():
            missing_audio += 1
            continue
        selected.append(
            {
                "language": language,
                "source_manifest_line": line_no,
                "source_audio_path": str(src),
                "row": row,
            }
        )
        used_podcasts.add(podcast)
        if len(selected) >= PER_LANGUAGE:
            break

    if len(selected) < PER_LANGUAGE:
        raise RuntimeError(
            f"{language}: selected {len(selected)} files, expected {PER_LANGUAGE}; "
            f"increase OVERSAMPLE_PER_LANGUAGE"
        )

    return selected, {
        "language": language,
        "candidate_manifest": str(candidate_path),
        "candidate_count": candidate_count,
        "random_line_numbers_drawn": sample_size,
        "random_rows_loaded": len(rows),
        "selected": len(selected),
        "missing_audio_among_loaded_rows": missing_audio,
        "skipped_duplicate_podcast": skipped_duplicate_podcast,
        "skipped_wrong_duration": skipped_wrong_duration,
    }


def audio_info(path: Path) -> dict:
    try:
        import soundfile as sf

        info = sf.info(str(path))
        return {
            "samplerate": info.samplerate,
            "channels": info.channels,
            "frames": info.frames,
            "duration": info.duration,
        }
    except Exception as exc:  # pragma: no cover - diagnostic only.
        return {"error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    rng = random.Random(SEED)
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    selected_items: list[dict] = []
    summaries: list[dict] = []
    for language in ("ZH", "EN"):
        selected, summary = sample_language(language, rng)
        selected_items.extend(selected)
        summaries.append(summary)

    records: list[dict] = []
    for sample_index, item in enumerate(selected_items, 1):
        row = item["row"]
        src = Path(item["source_audio_path"])
        podcast = row.get("podcast") or row.get("id", "").split("_S", 1)[0]
        dst = TARGET_DIR / f"{sample_index:02d}_{item['language']}_{podcast}_{row['id']}{src.suffix}"
        shutil.copy2(src, dst)

        record = {
            "sample_index": sample_index,
            "language": item["language"],
            "id": row.get("id"),
            "podcast": podcast,
            "speaker": row.get("speaker"),
            "duration_sec": row.get("duration_sec"),
            "chars_per_sec": row.get("chars_per_sec"),
            "source_manifest_line": item["source_manifest_line"],
            "source_wav_field": row.get("wav"),
            "source_audio_path": str(src),
            "copied_audio_path": str(dst),
            "copied_audio_info": audio_info(dst),
            "text": row.get("text"),
            "selection_seed": SEED,
        }
        records.append(record)

    manifest_path = TARGET_DIR / "selected_vad_long_audio_10.jsonl"
    with manifest_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary_path = TARGET_DIR / "selected_vad_long_audio_10.summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "seed": SEED,
                "target_dir": str(TARGET_DIR),
                "selected_count": len(records),
                "unique_podcasts": len({record["podcast"] for record in records}),
                "language_summaries": summaries,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")

    md_path = TARGET_DIR / "selected_vad_long_audio_10.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write("# Selected Jellycat VAD Long Audio Samples\n\n")
        f.write(f"Seed: `{SEED}`\n\n")
        f.write("| # | Lang | Podcast | ID | Duration | File |\n")
        f.write("|---|---|---|---|---:|---|\n")
        for record in records:
            copied = Path(record["copied_audio_path"]).name
            f.write(
                f"| {record['sample_index']} | {record['language']} | "
                f"{record['podcast']} | {record['id']} | "
                f"{record['duration_sec']} | `{copied}` |\n"
            )

    print(
        json.dumps(
            {
                "selected_count": len(records),
                "unique_podcasts": len({record["podcast"] for record in records}),
                "target_dir": str(TARGET_DIR),
                "manifest": str(manifest_path),
                "summary": str(summary_path),
                "markdown": str(md_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
