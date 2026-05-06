#!/usr/bin/env python3

import argparse
import gzip
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set

import soundfile as sf


DEFAULT_JELLYCAT_ROOT = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat"
)
PURE_TAG_RE = re.compile(r"^(?:\[[^\[\]]+\]\s*)+$")


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            "Backfill VibeVoice ASR sidecar JSON into Jellycat VAD-split "
            "manifests. Split parents are replaced by kept VAD children; "
            "parent rejects are dropped."
        ),
    )
    parser.add_argument("--language", required=True)
    parser.add_argument("--segment-manifest", type=Path, required=True)
    parser.add_argument("--split-map-jsonl", type=Path, required=True)
    parser.add_argument(
        "--parent-reject-jsonl",
        type=Path,
        action="append",
        default=[],
        help="Parent-level rejects to drop, e.g. >60s and vad_no_kept_children.",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_JELLYCAT_ROOT)
    parser.add_argument("--segment-output", type=Path, required=True)
    parser.add_argument("--recordings-output", type=Path, default=None)
    parser.add_argument("--supervisions-output", type=Path, default=None)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument(
        "--allow-missing-asr",
        action="store_true",
        help="Keep child rows with empty text if VibeVoice sidecar JSON is missing.",
    )
    parser.add_argument(
        "--drop-empty-asr",
        action="store_true",
        help="Drop child rows whose parsed ASR text is empty.",
    )
    parser.add_argument(
        "--num-shards",
        type=int,
        default=1,
        help="Process only records whose original JSONL index mod num_shards == shard_index.",
    )
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--max-records", type=int, default=-1)
    parser.add_argument("--progress-interval", type=int, default=100000)
    return parser.parse_args()


def open_text(path: Path, mode: str):
    if path.suffix == ".gz":
        return gzip.open(path, mode, encoding="utf-8")
    return path.open(mode, encoding="utf-8")


def iter_jsonl(path: Path) -> Iterator[dict]:
    with open_text(path, "rt") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def jsonl_writer(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    return open_text(path, "wt")


def load_parent_reject_ids(paths: List[Path]) -> Set[str]:
    ids = set()
    for path in paths:
        for record in iter_jsonl(path):
            if record.get("reject_scope") == "child":
                continue
            ids.add(str(record["id"]))
    return ids


def load_split_map(path: Path) -> Dict[str, List[dict]]:
    mapping: Dict[str, List[dict]] = {}
    for record in iter_jsonl(path):
        children = []
        for child in record.get("children", []):
            segment = child.get("segment") if isinstance(child, dict) else None
            if isinstance(segment, dict):
                children.append(segment)
        mapping[str(record["parent_id"])] = children
    return mapping


def is_non_speech_tag(text: str) -> bool:
    return bool(PURE_TAG_RE.fullmatch(text.strip()))


def parse_vibevoice_text(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    parts = []
    for segment in payload.get("segments", []):
        text = str(segment.get("text", "")).strip()
        if not text or is_non_speech_tag(text):
            continue
        parts.append(text)
    return "".join(parts).strip()


def probe_audio(path: Path) -> tuple[int, int, float]:
    info = sf.info(path)
    if info.channels != 1:
        raise ValueError(f"{path} channels={info.channels}, expected mono")
    sample_rate = int(info.samplerate)
    num_samples = int(info.frames)
    return sample_rate, num_samples, num_samples / sample_rate


def make_recording(record: dict, output_root: Path) -> dict:
    wav_path = output_root / record["wav"]
    return {
        "id": record["id"],
        "sources": [
            {
                "type": "file",
                "channels": [0],
                "source": str(wav_path),
            }
        ],
        "sampling_rate": int(record["sampling_rate"]),
        "num_samples": int(record["num_samples"]),
        "duration": float(record["duration"]),
        "channel_ids": [0],
    }


def make_supervision(record: dict, language: str) -> dict:
    standard_fields = {
        "id",
        "wav",
        "text",
        "speaker",
        "duration",
        "sampling_rate",
        "num_samples",
    }
    custom = {
        key: value
        for key, value in record.items()
        if key not in standard_fields and value is not None
    }
    return {
        "id": record["id"],
        "recording_id": record["id"],
        "start": 0.0,
        "duration": float(record["duration"]),
        "channel": 0,
        "text": record.get("text", ""),
        "language": language,
        "speaker": record.get("speaker"),
        "custom": custom,
    }


def prepare_child_record(child: dict, output_root: Path, allow_missing_asr: bool) -> Optional[dict]:
    child = dict(child)
    child_wav_path = output_root / child["wav"]
    asr_path = child_wav_path.with_suffix(".json")
    text = parse_vibevoice_text(asr_path)
    if text is None and not allow_missing_asr:
        raise FileNotFoundError(asr_path)
    if text is None:
        text = ""
    sample_rate, num_samples, duration = probe_audio(child_wav_path)
    child["text"] = text
    child["sampling_rate"] = sample_rate
    child["num_samples"] = num_samples
    child["duration"] = round(duration, 12)
    child["source_duration"] = round(duration, 12)
    child["audio_write_pending"] = False
    child["needs_text_annotation"] = False
    child["annotation_text"] = text
    child["asr_source"] = "vibevoice_sidecar_json" if asr_path.is_file() else "missing_allowed_empty"
    child["asr_json"] = str(asr_path) if asr_path.is_file() else None
    return child


def main() -> None:
    args = get_args()
    language = args.language.upper()
    if args.num_shards <= 0:
        raise ValueError("--num-shards must be positive")
    if not 0 <= args.shard_index < args.num_shards:
        raise ValueError("--shard-index must satisfy 0 <= shard_index < num_shards")

    parent_reject_ids = load_parent_reject_ids(args.parent_reject_jsonl)
    split_map = load_split_map(args.split_map_jsonl)
    stats = Counter()
    examples = []
    summary_output = args.summary_output or args.segment_output.with_suffix(
        args.segment_output.suffix + ".summary.json"
    )

    with jsonl_writer(args.segment_output) as segment_f:
        recordings_f = (
            jsonl_writer(args.recordings_output)
            if args.recordings_output is not None
            else None
        )
        supervisions_f = (
            jsonl_writer(args.supervisions_output)
            if args.supervisions_output is not None
            else None
        )
        try:
            for index, record in enumerate(iter_jsonl(args.segment_manifest)):
                if index % args.num_shards != args.shard_index:
                    continue
                if args.max_records > 0 and stats["records_seen"] >= args.max_records:
                    break
                stats["records_seen"] += 1
                record_id = str(record["id"])
                if record_id in parent_reject_ids:
                    stats["parent_rejected"] += 1
                    continue
                if record_id in split_map:
                    stats["split_parents"] += 1
                    for child in split_map[record_id]:
                        try:
                            child_record = prepare_child_record(
                                child,
                                args.output_root,
                                allow_missing_asr=args.allow_missing_asr,
                            )
                        except Exception as exc:
                            stats["child_backfill_error"] += 1
                            if len(examples) < 10:
                                examples.append({"id": child.get("id"), "error": repr(exc)})
                            continue
                        if args.drop_empty_asr and not child_record.get("text"):
                            stats["child_dropped_empty_asr"] += 1
                            continue
                        segment_f.write(json.dumps(child_record, ensure_ascii=False) + "\n")
                        stats["children_written"] += 1
                        if recordings_f is not None:
                            recordings_f.write(json.dumps(make_recording(child_record, args.output_root), ensure_ascii=False) + "\n")
                        if supervisions_f is not None:
                            supervisions_f.write(json.dumps(make_supervision(child_record, language), ensure_ascii=False) + "\n")
                    continue

                segment_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                stats["original_kept"] += 1
                if recordings_f is not None:
                    recordings_f.write(json.dumps(make_recording(record, args.output_root), ensure_ascii=False) + "\n")
                if supervisions_f is not None:
                    supervisions_f.write(json.dumps(make_supervision(record, language), ensure_ascii=False) + "\n")

                if args.progress_interval > 0 and stats["records_seen"] % args.progress_interval == 0:
                    print(
                        f"records_seen={stats['records_seen']:,} "
                        f"original_kept={stats['original_kept']:,} "
                        f"split_parents={stats['split_parents']:,} "
                        f"children_written={stats['children_written']:,} "
                        f"parent_rejected={stats['parent_rejected']:,}",
                        flush=True,
                    )
        finally:
            if recordings_f is not None:
                recordings_f.close()
            if supervisions_f is not None:
                supervisions_f.close()

    summary = {
        "language": language,
        "segment_manifest": str(args.segment_manifest),
        "split_map_jsonl": str(args.split_map_jsonl),
        "parent_reject_jsonl": [str(path) for path in args.parent_reject_jsonl],
        "output_root": str(args.output_root),
        "segment_output": str(args.segment_output),
        "recordings_output": str(args.recordings_output) if args.recordings_output else None,
        "supervisions_output": str(args.supervisions_output) if args.supervisions_output else None,
        "num_shards": args.num_shards,
        "shard_index": args.shard_index,
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
