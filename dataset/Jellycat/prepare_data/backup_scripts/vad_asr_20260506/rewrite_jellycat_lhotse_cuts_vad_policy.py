#!/usr/bin/env python3

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set


DEFAULT_JELLYCAT_ROOT = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat"
)


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            "Rewrite Lhotse MonoCut JSONL/JSONL.GZ files for the Jellycat "
            "duration60+VAD30 policy. Parent rejects are dropped; split "
            "parents are replaced by VAD child cuts. Outputs are versioned "
            "copies and inputs are never modified."
        ),
    )
    parser.add_argument(
        "--reject-jsonl",
        type=Path,
        action="append",
        default=[],
        help="Reject JSONL/JSONL.GZ. Child-scope rejects are ignored for old cut removal.",
    )
    parser.add_argument(
        "--split-map-jsonl",
        type=Path,
        action="append",
        default=[],
        help="VAD split map JSONL/JSONL.GZ. Can be repeated for shards.",
    )
    parser.add_argument(
        "--child-segment-jsonl",
        type=Path,
        action="append",
        default=[],
        help=(
            "Optional ASR-backfilled child segment JSONL/JSONL.GZ. If provided, "
            "these rows override split-map child segment payloads by id."
        ),
    )
    parser.add_argument(
        "--input-jsonl",
        type=Path,
        action="append",
        default=[],
        required=True,
        help="Input Lhotse MonoCut JSONL/JSONL.GZ to rewrite. Can be repeated.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for rewritten outputs and per-file summaries.",
    )
    parser.add_argument(
        "--output-suffix",
        default=".duration60_vad30",
        help=(
            "Suffix inserted before .jsonl or .jsonl.gz when writing into "
            "output-dir."
        ),
    )
    parser.add_argument(
        "--audio-root",
        type=Path,
        default=DEFAULT_JELLYCAT_ROOT,
        help="Root used to resolve relative child segment wav paths.",
    )
    parser.add_argument("--require-audio-exists", action="store_true")
    parser.add_argument("--allow-overwrite", action="store_true")
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


def jsonl_writer(path: Path, allow_overwrite: bool):
    if path.exists() and not allow_overwrite:
        raise FileExistsError(f"{path} exists; pass --allow-overwrite to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    return open_text(path, "wt")


def output_path_for(input_path: Path, output_dir: Path, suffix: str) -> Path:
    name = input_path.name
    if name.endswith(".jsonl.gz"):
        out_name = name[: -len(".jsonl.gz")] + suffix + ".jsonl.gz"
    elif name.endswith(".jsonl"):
        out_name = name[: -len(".jsonl")] + suffix + ".jsonl"
    else:
        out_name = name + suffix + ".jsonl"
    return output_dir / out_name


def load_parent_reject_ids(paths: List[Path]) -> Set[str]:
    ids = set()
    for path in paths:
        for record in iter_jsonl(path):
            if record.get("reject_scope") == "child":
                continue
            ids.add(str(record["id"]))
    return ids


def load_split_children(paths: List[Path]) -> Dict[str, List[dict]]:
    mapping: Dict[str, List[dict]] = {}
    for path in paths:
        for record in iter_jsonl(path):
            parent_id = str(record["parent_id"])
            children = mapping.setdefault(parent_id, [])
            for child in record.get("children", []):
                segment = child.get("segment") if isinstance(child, dict) else None
                if isinstance(segment, dict):
                    children.append(segment)
    return mapping


def load_child_segments(paths: List[Path]) -> Dict[str, dict]:
    children = {}
    for path in paths:
        for record in iter_jsonl(path):
            record_id = str(record.get("id", ""))
            if record_id:
                children[record_id] = record
    return children


def get_recording_id(cut: dict) -> Optional[str]:
    recording = cut.get("recording")
    if isinstance(recording, dict) and recording.get("id") is not None:
        return str(recording["id"])
    supervisions = cut.get("supervisions") or []
    if supervisions and supervisions[0].get("recording_id") is not None:
        return str(supervisions[0]["recording_id"])
    cut_id = str(cut.get("id", ""))
    if cut_id.endswith("-0"):
        return cut_id[:-2]
    return cut_id or None


def resolve_wav(audio_root: Path, wav: str) -> Path:
    path = Path(wav)
    if path.is_absolute():
        return path
    return audio_root / path


def child_custom(child: dict) -> dict:
    standard_fields = {
        "id",
        "wav",
        "text",
        "speaker",
        "duration",
        "sampling_rate",
        "num_samples",
    }
    return {
        key: value
        for key, value in child.items()
        if key not in standard_fields and value is not None
    }


def make_child_cut(parent_cut: dict, child: dict, audio_root: Path) -> dict:
    child_id = str(child["id"])
    duration = float(child["duration"])
    sample_rate = int(child["sampling_rate"])
    num_samples = int(child["num_samples"])
    child_wav = resolve_wav(audio_root, str(child["wav"]))

    cut = dict(parent_cut)
    cut["id"] = f"{child_id}-0"
    cut["start"] = 0
    cut["duration"] = duration
    cut["channel"] = int(cut.get("channel", 0))
    cut["type"] = cut.get("type", "MonoCut")

    parent_supervisions = parent_cut.get("supervisions") or [{}]
    parent_supervision = parent_supervisions[0] if parent_supervisions else {}
    supervision = dict(parent_supervision)
    supervision["id"] = child_id
    supervision["recording_id"] = child_id
    supervision["start"] = 0.0
    supervision["duration"] = duration
    supervision["channel"] = int(supervision.get("channel", 0))
    supervision["text"] = child.get("text", "")
    supervision["language"] = child.get("language", supervision.get("language"))
    supervision["speaker"] = child.get("speaker", supervision.get("speaker"))
    supervision["custom"] = child_custom(child)
    cut["supervisions"] = [supervision]

    parent_recording = parent_cut.get("recording") or {}
    recording = dict(parent_recording)
    recording["id"] = child_id
    recording["sources"] = [
        {
            "type": "file",
            "channels": [0],
            "source": str(child_wav),
        }
    ]
    recording["sampling_rate"] = sample_rate
    recording["num_samples"] = num_samples
    recording["duration"] = duration
    recording["channel_ids"] = [0]
    cut["recording"] = recording
    return cut


def rewrite_one(
    *,
    input_path: Path,
    output_path: Path,
    parent_reject_ids: Set[str],
    split_children: Dict[str, List[dict]],
    child_overrides: Dict[str, dict],
    audio_root: Path,
    require_audio_exists: bool,
    allow_overwrite: bool,
    max_records: int,
    progress_interval: int,
) -> dict:
    stats = Counter()
    examples = []
    with jsonl_writer(output_path, allow_overwrite=allow_overwrite) as out_f:
        for cut in iter_jsonl(input_path):
            if max_records > 0 and stats["records_seen"] >= max_records:
                break
            stats["records_seen"] += 1
            recording_id = get_recording_id(cut)
            if recording_id is None:
                stats["missing_recording_id"] += 1
                if len(examples) < 10:
                    examples.append({"cut_id": cut.get("id"), "error": "missing_recording_id"})
                continue

            if recording_id in parent_reject_ids:
                stats["parent_rejected"] += 1
                continue

            children = split_children.get(recording_id)
            if children:
                stats["split_parents"] += 1
                for child in children:
                    child_id = str(child["id"])
                    child_payload = child_overrides.get(child_id, child)
                    wav_path = resolve_wav(audio_root, str(child_payload["wav"]))
                    if require_audio_exists and not wav_path.is_file():
                        stats["missing_child_audio"] += 1
                        if len(examples) < 10:
                            examples.append(
                                {
                                    "parent_id": recording_id,
                                    "child_id": child_id,
                                    "error": "missing_child_audio",
                                    "wav": str(wav_path),
                                }
                            )
                        continue
                    out_f.write(
                        json.dumps(
                            make_child_cut(cut, child_payload, audio_root),
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    stats["children_written"] += 1
                continue

            out_f.write(json.dumps(cut, ensure_ascii=False) + "\n")
            stats["original_kept"] += 1

            if progress_interval > 0 and stats["records_seen"] % progress_interval == 0:
                print(
                    f"{input_path.name}: records_seen={stats['records_seen']:,} "
                    f"original_kept={stats['original_kept']:,} "
                    f"parent_rejected={stats['parent_rejected']:,} "
                    f"split_parents={stats['split_parents']:,} "
                    f"children_written={stats['children_written']:,}",
                    flush=True,
                )

    return {
        "input": str(input_path),
        "output": str(output_path),
        "stats": {key: int(value) for key, value in sorted(stats.items())},
        "examples": examples,
    }


def main() -> None:
    args = get_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    parent_reject_ids = load_parent_reject_ids(args.reject_jsonl)
    split_children = load_split_children(args.split_map_jsonl)
    child_overrides = load_child_segments(args.child_segment_jsonl)

    summaries = []
    for input_path in args.input_jsonl:
        output_path = output_path_for(input_path, args.output_dir, args.output_suffix)
        summary = rewrite_one(
            input_path=input_path,
            output_path=output_path,
            parent_reject_ids=parent_reject_ids,
            split_children=split_children,
            child_overrides=child_overrides,
            audio_root=args.audio_root,
            require_audio_exists=args.require_audio_exists,
            allow_overwrite=args.allow_overwrite,
            max_records=args.max_records,
            progress_interval=args.progress_interval,
        )
        summaries.append(summary)
        summary_path = output_path.with_suffix(output_path.suffix + ".summary.json")
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    combined = {
        "reject_jsonl": [str(path) for path in args.reject_jsonl],
        "split_map_jsonl": [str(path) for path in args.split_map_jsonl],
        "child_segment_jsonl": [str(path) for path in args.child_segment_jsonl],
        "audio_root": str(args.audio_root),
        "outputs": summaries,
    }
    combined_path = args.output_dir / "rewrite_lhotse_cuts_vad_policy.summary.json"
    combined_path.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
