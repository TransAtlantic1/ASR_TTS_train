#!/usr/bin/env python3

import argparse
import gzip
import json
import logging
import re
import time
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple

import soundfile as sf


DEFAULT_RAW_ROOT = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat"
)
SAMPLE_RATE = 24000
TARGET_LANGUAGE = "ZH"
MAX_PODCAST_ID = 999999
MAX_SPEAKER_ID = 99999
MAX_UTTERANCE_ID = 99999999
DEFAULT_SOURCE_LANGUAGES = {
    "ZH": ["zh", "zh-cn"],
    "EN": ["en-us"],
}
KNOWN_SOURCE_LINE_COUNTS = {
    "zh": 10293979,
    "zh-cn": 17638318,
    "en-us": 26424704,
}


def get_args(
    default_target_language: Optional[str] = None,
    default_languages: Optional[list[str]] = None,
) -> argparse.Namespace:
    default_target = (default_target_language or TARGET_LANGUAGE).upper()
    default_source_languages = default_languages or DEFAULT_SOURCE_LANGUAGES.get(
        default_target,
        [],
    )
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Cut Jellycat podcast segments into utterance FLAC files.",
    )
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--target-language",
        default=default_target,
        help="Target Jellycat language id, e.g. ZH or EN.",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=default_source_languages,
        help="Source language manifests to process and merge into target language.",
    )
    parser.add_argument(
        "--manifest-stem",
        default=None,
        help="Base name for output segment manifest.",
    )
    parser.add_argument(
        "--max-utterances-per-language",
        type=int,
        default=-1,
        help="Stop after this many accepted speech utterances per source language.",
    )
    parser.add_argument(
        "--max-lines-per-language",
        type=int,
        default=-1,
        help="Optional safety cap on source manifest lines read per source language.",
    )
    parser.add_argument(
        "--num-shards",
        type=int,
        default=1,
        help="Total number of hash shards for full preparation.",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        default=0,
        help="Current hash shard index in [0, num_shards).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Rewrite existing utterance FLAC files.",
    )
    parser.add_argument(
        "--skip-lhotse",
        action="store_true",
        help="Do not write Lhotse RecordingSet/SupervisionSet manifests.",
    )
    parser.add_argument(
        "--progress-path",
        type=Path,
        default=None,
        help="Optional JSON progress file updated during ID-map scan and cutting.",
    )
    parser.add_argument(
        "--progress-interval-lines",
        type=int,
        default=100000,
        help="Update progress JSON/log every N source manifest lines.",
    )
    args = parser.parse_args()
    args.target_language = args.target_language.upper()
    if not args.languages:
        args.languages = DEFAULT_SOURCE_LANGUAGES.get(args.target_language, [])
    if not args.languages:
        raise ValueError(
            "No source languages specified; pass --languages for this target language."
        )
    if args.manifest_stem is None:
        args.manifest_stem = f"jellycat_{args.target_language}_segments"
    return args


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def open_jsonl_writer(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    return gzip.open(path, "wt", encoding="utf-8")


def sanitize_component(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = value.strip("._-")
    return value or "unknown"


def source_manifest_path(raw_root: Path, language: str) -> Path:
    return raw_root / f"manifest_{language}.jsonl"


def expected_language_lines(args: argparse.Namespace, language: str) -> Optional[int]:
    if args.max_lines_per_language > 0:
        return args.max_lines_per_language
    return KNOWN_SOURCE_LINE_COUNTS.get(language)


def expected_total_lines(args: argparse.Namespace) -> Optional[int]:
    total = 0
    for language in args.languages:
        expected = expected_language_lines(args, language)
        if expected is None:
            return None
        total += expected
    return total


def progress_bar(percent: Optional[float], width: int = 40) -> str:
    if percent is None:
        return "[" + ("?" * width) + "]"
    percent = max(0.0, min(100.0, percent))
    filled = int(round((percent / 100.0) * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + f"] {percent:6.2f}%"


def write_progress(args: argparse.Namespace, payload: Dict) -> None:
    if args.progress_path is None:
        return
    payload = dict(payload)
    payload["updated_at_unix"] = time.time()
    payload["bar"] = progress_bar(payload.get("percent"))
    args.progress_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = args.progress_path.with_suffix(args.progress_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(args.progress_path)


def source_speaker(entry: Dict) -> str:
    return sanitize_component(str(entry.get("speaker") or "spk_unknown"))


def iter_manifest_entries(path: Path) -> Iterator[Tuple[int, Dict]]:
    with open_text(path) as f:
        for line_index, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_index, json.loads(line)
            except json.JSONDecodeError as exc:
                logging.warning("Skipping malformed JSON at %s:%d: %s", path, line_index + 1, exc)


def shard_accepts(entry_id: str, num_shards: int, shard_index: int) -> bool:
    if num_shards == 1:
        return True
    return zlib.crc32(entry_id.encode("utf-8")) % num_shards == shard_index


def parse_source_utterance_index(entry_id: str) -> int:
    match = re.search(r"_(\d+)_(\d+)$", entry_id)
    if match is None:
        return zlib.crc32(entry_id.encode("utf-8")) % 100000000
    return int(match.group(1)) * 1000000 + int(match.group(2))


def build_id_maps(args: argparse.Namespace) -> Dict[str, Dict[str, int]]:
    podcast_ids: Dict[str, int] = {}
    speaker_ids: Dict[str, int] = {}
    next_speaker_by_podcast: Dict[str, int] = defaultdict(int)
    total_expected = expected_total_lines(args)
    total_seen = 0
    write_progress(
        args,
        {
            "phase": "id_map_scan",
            "language": None,
            "language_lines_seen": 0,
            "total_lines_seen": 0,
            "total_expected_lines": total_expected,
            "percent": 0.0 if total_expected else None,
            "accepted_so_far": 0,
            "podcasts_so_far": 0,
            "speakers_so_far": 0,
        },
    )

    for language in args.languages:
        manifest_path = source_manifest_path(args.raw_root, language)
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Missing source manifest: {manifest_path}")

        stats = Counter()
        for _, entry in iter_manifest_entries(manifest_path):
            if args.max_lines_per_language > 0 and stats["lines_seen"] >= args.max_lines_per_language:
                break
            stats["lines_seen"] += 1
            total_seen += 1
            should_report = (
                args.progress_interval_lines > 0
                and stats["lines_seen"] % args.progress_interval_lines == 0
            )
            if should_report:
                percent = (
                    (total_seen / total_expected) * 100.0
                    if total_expected
                    else None
                )
                logging.info(
                    "ID map scan %s: lines_seen=%d accepted=%d podcasts=%d speakers=%d %s",
                    language,
                    stats["lines_seen"],
                    stats["accepted"],
                    len(podcast_ids),
                    len(speaker_ids),
                    progress_bar(percent),
                )
                write_progress(
                    args,
                    {
                        "phase": "id_map_scan",
                        "language": language,
                        "language_lines_seen": stats["lines_seen"],
                        "total_lines_seen": total_seen,
                        "total_expected_lines": total_expected,
                        "percent": percent,
                        "accepted_so_far": stats["accepted"],
                        "podcasts_so_far": len(podcast_ids),
                        "speakers_so_far": len(speaker_ids),
                    },
                )

            reason, _ = validate_entry(entry, language, args.raw_root)
            if reason is not None:
                continue

            podcast_hash = str(entry["podcast_hash"])
            if podcast_hash not in podcast_ids:
                podcast_ids[podcast_hash] = len(podcast_ids)

            speaker_key = "|".join(
                [podcast_hash, str(entry["episode_hash"]), source_speaker(entry)]
            )
            if speaker_key not in speaker_ids:
                speaker_ids[speaker_key] = next_speaker_by_podcast[podcast_hash]
                next_speaker_by_podcast[podcast_hash] += 1

            stats["accepted"] += 1
            if args.max_utterances_per_language > 0 and stats["accepted"] >= args.max_utterances_per_language:
                break

    write_progress(
        args,
        {
            "phase": "id_map_scan_done",
            "language": None,
            "language_lines_seen": None,
            "total_lines_seen": total_seen,
            "total_expected_lines": total_expected,
            "percent": 100.0 if total_expected else None,
            "accepted_so_far": None,
            "podcasts_so_far": len(podcast_ids),
            "speakers_so_far": len(speaker_ids),
        },
    )
    return {"podcasts": podcast_ids, "speakers": speaker_ids}


def reject_entry(entry: Dict, reason: str, source_language: str, source_wav: Optional[Path]) -> Dict:
    return {
        "id": entry.get("id"),
        "reason": reason,
        "text": entry.get("text", ""),
        "language": TARGET_LANGUAGE,
        "source_language": source_language,
        "source_wav": str(source_wav) if source_wav is not None else None,
        "source_start_time": entry.get("start_time"),
        "source_end_time": entry.get("end_time"),
        "duration": entry.get("duration"),
        "podcast_hash": entry.get("podcast_hash"),
        "episode_hash": entry.get("episode_hash"),
        "source_manifest_id": entry.get("id"),
    }


def target_paths(
    output_root: Path,
    entry: Dict,
    id_maps: Dict[str, Dict[str, int]],
) -> Tuple[Path, str, str, str, str]:
    podcast_hash = str(entry["podcast_hash"])
    speaker_key = "|".join(
        [podcast_hash, str(entry["episode_hash"]), source_speaker(entry)]
    )
    podcast_num = id_maps["podcasts"][podcast_hash]
    speaker_num = id_maps["speakers"][speaker_key]
    utterance_num = parse_source_utterance_index(str(entry["id"]))
    if podcast_num > MAX_PODCAST_ID:
        raise ValueError(f"Podcast id overflow: {podcast_num} > {MAX_PODCAST_ID}")
    if speaker_num > MAX_SPEAKER_ID:
        raise ValueError(f"Speaker id overflow: {speaker_num} > {MAX_SPEAKER_ID}")
    if utterance_num > MAX_UTTERANCE_ID:
        raise ValueError(f"Utterance id overflow: {utterance_num} > {MAX_UTTERANCE_ID}")

    podcast_id = f"{TARGET_LANGUAGE}_P{podcast_num:06d}"
    speaker_id = f"{podcast_id}_S{speaker_num:05d}"
    utterance_id = f"{speaker_id}_W{utterance_num:08d}"
    rel_path = (
        Path(TARGET_LANGUAGE)
        / podcast_id
        / speaker_id
        / "flac"
        / f"{utterance_id}.flac"
    )
    return output_root / rel_path, rel_path.as_posix(), podcast_id, speaker_id, utterance_id


def probe_target_audio(path: Path) -> Tuple[int, int, float]:
    info = sf.info(path)
    if info.samplerate != SAMPLE_RATE:
        raise ValueError(f"{path} sample_rate={info.samplerate}, expected {SAMPLE_RATE}")
    if info.channels != 1:
        raise ValueError(f"{path} channels={info.channels}, expected mono")
    if info.frames <= 0:
        raise ValueError(f"{path} has no audio frames")
    num_samples = int(info.frames)
    return int(info.samplerate), num_samples, num_samples / int(info.samplerate)


def cut_flac(source_path: Path, target_path: Path, start_time: float, duration: float) -> Tuple[int, int, float]:
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
    max_frame_delta = max(2, int(round(0.05 * SAMPLE_RATE)))
    if abs(data.shape[0] - num_frames) > max_frame_delta:
        raise ValueError(
            f"{source_path} returned {data.shape[0]} frames, expected {num_frames}"
        )
    if data.shape[1] != 1:
        data = data[:, :1]
    target_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(target_path, data, sample_rate, format="FLAC", subtype="PCM_16")
    return probe_target_audio(target_path)


def build_output_record(
    entry: Dict,
    rel_wav: str,
    source_language: str,
    source_wav: Path,
    podcast_id: str,
    speaker: str,
    utterance_id: str,
    sample_rate: int,
    num_samples: int,
    duration: float,
) -> Dict:
    return {
        "id": utterance_id,
        "wav": rel_wav,
        "text": str(entry["text"]).strip(),
        "duration": round(duration, 12),
        "sampling_rate": sample_rate,
        "num_samples": num_samples,
        "language": TARGET_LANGUAGE,
        "source_language": source_language,
        "podcast": podcast_id,
        "speaker": speaker,
        "source_manifest_id": str(entry["id"]),
        "source_podcast_hash": str(entry["podcast_hash"]),
        "source_episode_hash": str(entry["episode_hash"]),
        "source_speaker": source_speaker(entry),
        "source_wav": str(source_wav),
        "source_start_time": float(entry["start_time"]),
        "source_end_time": float(entry["end_time"]),
        "source_duration": float(entry["duration"]),
    }


def write_lhotse_items(
    recording_writer,
    supervision_writer,
    output_root: Path,
    record: Dict,
) -> None:
    wav_path = output_root / record["wav"]
    sample_rate = int(record["sampling_rate"])
    num_samples = int(record["num_samples"])
    duration = num_samples / sample_rate
    recording = {
        "id": record["id"],
        "sources": [
            {
                "type": "file",
                "channels": [0],
                "source": str(wav_path),
            }
        ],
        "sampling_rate": sample_rate,
        "num_samples": num_samples,
        "duration": duration,
        "channel_ids": [0],
    }
    supervision = {
        "id": record["id"],
        "recording_id": record["id"],
        "start": 0.0,
        "duration": duration,
        "channel": 0,
        "text": record["text"],
        "language": TARGET_LANGUAGE,
        "speaker": record["speaker"],
        "custom": {
            "source_language": record["source_language"],
            "podcast": record["podcast"],
            "source_manifest_id": record["source_manifest_id"],
            "source_podcast_hash": record["source_podcast_hash"],
            "source_episode_hash": record["source_episode_hash"],
            "source_speaker": record["source_speaker"],
            "source_wav": record["source_wav"],
            "source_start_time": record["source_start_time"],
            "source_end_time": record["source_end_time"],
            "source_duration": record["source_duration"],
        },
    }
    recording_writer.write(json.dumps(recording, ensure_ascii=False) + "\n")
    supervision_writer.write(json.dumps(supervision, ensure_ascii=False) + "\n")


def flush_writers(*writers) -> None:
    for writer in writers:
        if writer is None:
            continue
        flush = getattr(writer, "flush", None)
        if flush is not None:
            flush()


def validate_entry(entry: Dict, source_language: str, raw_root: Path) -> Tuple[Optional[str], Optional[Path]]:
    text = str(entry.get("text", "")).strip()
    if not text:
        return "empty_text", None
    source_rel = entry.get("wav")
    if not source_rel:
        return "missing_wav", None
    source_wav = raw_root / source_language / str(source_rel)
    if not source_wav.is_file():
        return "missing_source_wav", source_wav
    try:
        start_time = float(entry.get("start_time"))
        end_time = float(entry.get("end_time"))
        duration = float(entry.get("duration"))
    except (TypeError, ValueError):
        return "invalid_time", source_wav
    if start_time < 0 or end_time <= start_time or duration <= 0:
        return "invalid_time", source_wav
    if abs((end_time - start_time) - duration) > 0.05:
        return "duration_mismatch", source_wav
    for field in ("id", "podcast_hash", "episode_hash"):
        if not entry.get(field):
            return f"missing_{field}", source_wav
    return None, source_wav


def process_language(
    *,
    language: str,
    args: argparse.Namespace,
    segment_writer,
    rejected_writer,
    recording_writer,
    supervision_writer,
    id_maps: Dict[str, Dict[str, int]],
) -> Counter:
    manifest_path = source_manifest_path(args.raw_root, language)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing source manifest: {manifest_path}")

    stats = Counter()
    expected = expected_language_lines(args, language)
    write_progress(
        args,
        {
            "phase": "cutting",
            "language": language,
            "language_lines_seen": 0,
            "language_expected_lines": expected,
            "percent": 0.0 if expected else None,
            "accepted": 0,
            "audio_written": 0,
            "audio_reused": 0,
            "rejected": 0,
        },
    )
    for line_index, entry in iter_manifest_entries(manifest_path):
        if args.max_lines_per_language > 0 and stats["lines_seen"] >= args.max_lines_per_language:
            break
        stats["lines_seen"] += 1
        should_report = (
            args.progress_interval_lines > 0
            and stats["lines_seen"] % args.progress_interval_lines == 0
        )
        if should_report:
            percent = (stats["lines_seen"] / expected) * 100.0 if expected else None
            logging.info(
                "Cutting %s: lines_seen=%d accepted=%d audio_written=%d rejected=%d %s",
                language,
                stats["lines_seen"],
                stats["accepted"],
                stats["audio_written"],
                sum(value for key, value in stats.items() if key.startswith("rejected_")),
                progress_bar(percent),
            )
            write_progress(
                args,
                {
                    "phase": "cutting",
                    "language": language,
                    "language_lines_seen": stats["lines_seen"],
                    "language_expected_lines": expected,
                    "percent": percent,
                    "accepted": stats["accepted"],
                    "audio_written": stats["audio_written"],
                    "audio_reused": stats["audio_reused"],
                    "rejected": sum(
                        value for key, value in stats.items() if key.startswith("rejected_")
                    ),
                },
            )
            flush_writers(segment_writer, rejected_writer, recording_writer, supervision_writer)

        entry_id = str(entry.get("id", ""))
        if not entry_id:
            rejected_writer.write(
                json.dumps(reject_entry(entry, "missing_id", language, None), ensure_ascii=False) + "\n"
            )
            stats["rejected_missing_id"] += 1
            continue

        if not shard_accepts(entry_id, args.num_shards, args.shard_index):
            stats["shard_skipped"] += 1
            continue

        reason, source_wav = validate_entry(entry, language, args.raw_root)
        if reason is not None:
            rejected_writer.write(
                json.dumps(reject_entry(entry, reason, language, source_wav), ensure_ascii=False) + "\n"
            )
            stats[f"rejected_{reason}"] += 1
            continue

        target_path, rel_wav, podcast_id, speaker, utterance_id = target_paths(
            args.output_root, entry, id_maps
        )
        if args.overwrite or not target_path.is_file():
            try:
                sample_rate, num_samples, actual_duration = cut_flac(
                    source_wav,
                    target_path,
                    start_time=float(entry["start_time"]),
                    duration=float(entry["duration"]),
                )
                stats["audio_written"] += 1
            except Exception as exc:
                logging.exception("Failed to cut %s from %s", entry_id, source_wav)
                rejected_writer.write(
                    json.dumps(reject_entry(entry, f"cut_error:{exc}", language, source_wav), ensure_ascii=False)
                    + "\n"
                )
                stats["rejected_cut_error"] += 1
                continue
        else:
            try:
                sample_rate, num_samples, actual_duration = probe_target_audio(target_path)
                expected_duration = float(entry["duration"])
                if abs(actual_duration - expected_duration) > 0.05:
                    raise ValueError(
                        f"{target_path} duration={actual_duration:.6f}, "
                        f"expected {expected_duration:.6f}"
                    )
                stats["audio_reused"] += 1
            except Exception as exc:
                logging.warning("Re-cutting existing target after probe failure: %s (%s)", target_path, exc)
                try:
                    sample_rate, num_samples, actual_duration = cut_flac(
                        source_wav,
                        target_path,
                        start_time=float(entry["start_time"]),
                        duration=float(entry["duration"]),
                    )
                    stats["audio_written"] += 1
                    stats["audio_repaired"] += 1
                except Exception as recut_exc:
                    logging.exception("Failed to repair existing target %s", target_path)
                    rejected_writer.write(
                        json.dumps(
                            reject_entry(
                                entry,
                                f"target_repair_error:{recut_exc}",
                                language,
                                source_wav,
                            ),
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    stats["rejected_target_repair_error"] += 1
                    continue

        output_record = build_output_record(
            entry,
            rel_wav,
            language,
            source_wav,
            podcast_id,
            speaker,
            utterance_id,
            sample_rate,
            num_samples,
            actual_duration,
        )
        segment_writer.write(json.dumps(output_record, ensure_ascii=False) + "\n")
        if recording_writer is not None and supervision_writer is not None:
            write_lhotse_items(recording_writer, supervision_writer, args.output_root, output_record)

        stats["accepted"] += 1
        stats["accepted_duration_sec"] += actual_duration
        if args.max_utterances_per_language > 0 and stats["accepted"] >= args.max_utterances_per_language:
            break

        if stats["accepted"] and stats["accepted"] % 1000 == 0:
            logging.info("%s accepted=%d line=%d", language, stats["accepted"], line_index + 1)

    write_progress(
        args,
        {
            "phase": "cutting_done",
            "language": language,
            "language_lines_seen": stats["lines_seen"],
            "language_expected_lines": expected,
            "percent": 100.0 if expected else None,
            "accepted": stats["accepted"],
            "audio_written": stats["audio_written"],
            "audio_reused": stats["audio_reused"],
            "rejected": sum(value for key, value in stats.items() if key.startswith("rejected_")),
        },
    )
    return stats


def write_summary(
    *,
    output_root: Path,
    manifest_dir: Path,
    segment_manifest_path: Path,
    rejected_manifest_path: Path,
    lhotse_recordings_path: Optional[Path],
    lhotse_supervisions_path: Optional[Path],
    per_language_stats: Dict[str, Counter],
    args: argparse.Namespace,
) -> None:
    total = Counter()
    for stats in per_language_stats.values():
        total += stats
    summary = {
        "status": "prepared",
        "target_language": TARGET_LANGUAGE,
        "raw_root": str(args.raw_root),
        "output_root": str(output_root),
        "segment_manifest": str(segment_manifest_path),
        "rejected_manifest": str(rejected_manifest_path),
        "lhotse_recordings": str(lhotse_recordings_path) if lhotse_recordings_path else None,
        "lhotse_supervisions": str(lhotse_supervisions_path) if lhotse_supervisions_path else None,
        "sample_rate": SAMPLE_RATE,
        "audio_format": "flac",
        "directory_layout": (
            f"{TARGET_LANGUAGE}/{TARGET_LANGUAGE}_P000000/"
            f"{TARGET_LANGUAGE}_P000000_S00000/flac/"
            f"{TARGET_LANGUAGE}_P000000_S00000_W00000000.flac"
        ),
        "id_policy": "podcasts and episode-local speakers are assigned numeric IDs in source manifest order; source hashes stay in manifest metadata",
        "speaker_policy": "episode-local source speaker ids are mapped to numeric S IDs under each numeric podcast",
        "policy_filtering": "content policy filtering is handled by manifest_policy_filter; raw_to_utterance only rejects records that cannot be sliced",
        "id_map_counts": {
            "podcasts": len(args.id_maps["podcasts"]),
            "speakers": len(args.id_maps["speakers"]),
        },
        "num_shards": args.num_shards,
        "shard_index": args.shard_index,
        "per_language_stats": {lang: dict(stats) for lang, stats in per_language_stats.items()},
        "total_stats": dict(total),
    }
    summary_path = manifest_dir / f"{args.manifest_stem}.summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logging.info("Summary written to %s", summary_path)


def main(
    default_target_language: Optional[str] = None,
    default_languages: Optional[list[str]] = None,
) -> None:
    global TARGET_LANGUAGE
    args = get_args(
        default_target_language=default_target_language,
        default_languages=default_languages,
    )
    TARGET_LANGUAGE = args.target_language
    if args.num_shards <= 0:
        raise ValueError("--num-shards must be positive")
    if not 0 <= args.shard_index < args.num_shards:
        raise ValueError("--shard-index must be in [0, num_shards)")
    if args.num_shards > 1:
        args.manifest_stem = (
            f"{args.manifest_stem}.shard{args.shard_index:05d}-of-{args.num_shards:05d}"
        )
    args.id_maps = build_id_maps(args)

    manifest_dir = args.output_root / "manifests" / TARGET_LANGUAGE
    manifest_dir.mkdir(parents=True, exist_ok=True)
    segment_manifest_path = manifest_dir / f"{args.manifest_stem}.jsonl.gz"
    rejected_stem = args.manifest_stem.replace("segments", "rejected")
    rejected_manifest_path = manifest_dir / f"{rejected_stem}.jsonl.gz"
    lhotse_recordings_path = manifest_dir / f"{args.manifest_stem.replace('segments', 'recordings')}.jsonl.gz"
    lhotse_supervisions_path = manifest_dir / f"{args.manifest_stem.replace('segments', 'supervisions')}.jsonl.gz"

    per_language_stats: Dict[str, Counter] = {}
    with open_jsonl_writer(segment_manifest_path) as segment_writer, open_jsonl_writer(
        rejected_manifest_path
    ) as rejected_writer:
        if args.skip_lhotse:
            recording_writer = None
            supervision_writer = None
            for language in args.languages:
                per_language_stats[language] = process_language(
                    language=language,
                    args=args,
                    segment_writer=segment_writer,
                    rejected_writer=rejected_writer,
                    recording_writer=recording_writer,
                    supervision_writer=supervision_writer,
                    id_maps=args.id_maps,
                )
        else:
            with open_jsonl_writer(lhotse_recordings_path) as recording_writer, open_jsonl_writer(
                lhotse_supervisions_path
            ) as supervision_writer:
                for language in args.languages:
                    per_language_stats[language] = process_language(
                        language=language,
                        args=args,
                        segment_writer=segment_writer,
                        rejected_writer=rejected_writer,
                        recording_writer=recording_writer,
                        supervision_writer=supervision_writer,
                        id_maps=args.id_maps,
                    )

    write_summary(
        output_root=args.output_root,
        manifest_dir=manifest_dir,
        segment_manifest_path=segment_manifest_path,
        rejected_manifest_path=rejected_manifest_path,
        lhotse_recordings_path=None if args.skip_lhotse else lhotse_recordings_path,
        lhotse_supervisions_path=None if args.skip_lhotse else lhotse_supervisions_path,
        per_language_stats=per_language_stats,
        args=args,
    )
    write_progress(
        args,
        {
            "phase": "done",
            "language": None,
            "percent": 100.0,
            "accepted": sum(stats["accepted"] for stats in per_language_stats.values()),
            "audio_written": sum(stats["audio_written"] for stats in per_language_stats.values()),
            "audio_reused": sum(stats["audio_reused"] for stats in per_language_stats.values()),
            "rejected": sum(
                value
                for stats in per_language_stats.values()
                for key, value in stats.items()
                if key.startswith("rejected_")
            ),
        },
    )


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
        level=logging.INFO,
    )
    main()
