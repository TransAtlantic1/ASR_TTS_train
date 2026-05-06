#!/usr/bin/env python3

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterator, Tuple

import soundfile as sf


DEFAULT_JELLYCAT_ROOT = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat"
)
SAMPLE_RATE = 24000


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            "Cut VAD child FLACs from raw_data source audio using flat "
            "Jellycat VAD annotation JSONL rows. This does not call ASR and "
            "does not modify raw_data."
        ),
    )
    parser.add_argument("--annotation-jsonl", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_JELLYCAT_ROOT,
        help="Jellycat root used to resolve child `wav` paths.",
    )
    parser.add_argument(
        "--audio-list-output",
        type=Path,
        default=None,
        help="Optional newline-delimited absolute child FLAC list for VibeVoice.",
    )
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-records", type=int, default=-1)
    parser.add_argument("--progress-interval", type=int, default=100000)
    return parser.parse_args()


def iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def cut_flac(
    *,
    source_path: Path,
    target_path: Path,
    start_time: float,
    end_time: float,
) -> Tuple[int, int, float]:
    duration = end_time - start_time
    if duration <= 0:
        raise ValueError(f"invalid cut duration: start={start_time}, end={end_time}")
    info = sf.info(source_path)
    if info.samplerate != SAMPLE_RATE:
        raise ValueError(f"{source_path} sample_rate={info.samplerate}, expected {SAMPLE_RATE}")
    start_frame = max(0, int(round(start_time * SAMPLE_RATE)))
    num_frames = max(1, int(round(duration * SAMPLE_RATE)))
    data, sample_rate = sf.read(
        source_path,
        start=start_frame,
        frames=num_frames,
        dtype="float32",
        always_2d=True,
    )
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f"{source_path} sample_rate={sample_rate}, expected {SAMPLE_RATE}")
    if data.shape[1] != 1:
        data = data[:, :1]
    target_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(target_path, data, sample_rate, format="FLAC", subtype="PCM_16")
    out_info = sf.info(target_path)
    return int(out_info.samplerate), int(out_info.frames), out_info.frames / out_info.samplerate


def main() -> None:
    args = get_args()
    summary_output = args.summary_output or args.annotation_jsonl.with_suffix(
        args.annotation_jsonl.suffix + ".cut_audio_summary.json"
    )
    audio_list_output = args.audio_list_output
    stats = Counter()
    examples = []

    audio_list_handle = None
    if audio_list_output is not None:
        audio_list_output.parent.mkdir(parents=True, exist_ok=True)
        audio_list_handle = audio_list_output.open("w", encoding="utf-8")

    try:
        for record in iter_jsonl(args.annotation_jsonl):
            if args.max_records > 0 and stats["records_seen"] >= args.max_records:
                break
            stats["records_seen"] += 1
            if record.get("post_vad_action") != "keep":
                stats["skipped_non_keep"] += 1
                continue

            source_wav = Path(
                record.get("raw_cut_source_wav")
                or record.get("source_wav")
                or ""
            )
            child_wav = args.output_root / str(record["wav"])
            start_time = float(
                record.get("raw_cut_start_time")
                if record.get("raw_cut_start_time") is not None
                else record["source_start_time"]
            )
            end_time = float(
                record.get("raw_cut_end_time")
                if record.get("raw_cut_end_time") is not None
                else record["source_end_time"]
            )

            if not source_wav.is_file():
                stats["missing_source_wav"] += 1
                if len(examples) < 10:
                    examples.append({"id": record["id"], "error": "missing_source_wav", "source_wav": str(source_wav)})
                continue
            if child_wav.exists() and not args.overwrite:
                stats["audio_exists"] += 1
            else:
                try:
                    sample_rate, num_samples, duration = cut_flac(
                        source_path=source_wav,
                        target_path=child_wav,
                        start_time=start_time,
                        end_time=end_time,
                    )
                except Exception as exc:
                    stats["cut_error"] += 1
                    if len(examples) < 10:
                        examples.append({"id": record["id"], "error": repr(exc)})
                    continue
                stats["audio_written"] += 1
                stats["samples_written"] += num_samples
                if sample_rate != SAMPLE_RATE:
                    stats["unexpected_sample_rate"] += 1
                if duration > 30.0:
                    stats["written_duration_gt_30s"] += 1

            if audio_list_handle is not None:
                audio_list_handle.write(str(child_wav) + "\n")
            stats["audio_listed_for_asr"] += 1

            if args.progress_interval > 0 and stats["records_seen"] % args.progress_interval == 0:
                print(
                    f"records_seen={stats['records_seen']:,} "
                    f"audio_written={stats['audio_written']:,} "
                    f"audio_exists={stats['audio_exists']:,} "
                    f"cut_error={stats['cut_error']:,}",
                    flush=True,
                )
    finally:
        if audio_list_handle is not None:
            audio_list_handle.close()

    summary = {
        "annotation_jsonl": str(args.annotation_jsonl),
        "output_root": str(args.output_root),
        "audio_list_output": str(audio_list_output) if audio_list_output else None,
        "stats": {key: int(value) for key, value in sorted(stats.items())},
        "examples": examples,
    }
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
