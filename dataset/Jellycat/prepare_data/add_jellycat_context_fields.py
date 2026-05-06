#!/usr/bin/env python3

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            "Add nearest prefix/suffix annotated-audio context fields to "
            "Jellycat podcast-level JSONLs and optionally write a merged "
            "segment manifest."
        ),
    )
    parser.add_argument("--language", required=True, help="Target language, e.g. ZH.")
    parser.add_argument(
        "--podcast-root",
        type=Path,
        required=True,
        help="Input language root containing <LANG>_P*.jsonl podcast manifests.",
    )
    parser.add_argument(
        "--output-podcast-root",
        type=Path,
        required=True,
        help="Output language root for enriched podcast manifests.",
    )
    parser.add_argument(
        "--segment-output",
        type=Path,
        default=None,
        help="Optional merged segment JSONL/JSONL.GZ output path.",
    )
    parser.add_argument(
        "--far-threshold-sec",
        type=float,
        default=30.0,
        help="Gap threshold for prefix_far/suffix_far.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=-1,
        help="Optional development cap on podcast files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing output podcast JSONLs and segment output.",
    )
    return parser.parse_args()


def open_text(path: Path, mode: str):
    if path.suffix == ".gz":
        return gzip.open(path, mode, encoding="utf-8")
    return path.open(mode, encoding="utf-8")


def iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, records: Iterable[dict], overwrite: bool) -> int:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} exists; pass --overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def source_episode_key(record: dict) -> str:
    source_wav = record.get("source_wav")
    if source_wav:
        return f"source_wav:{source_wav}"
    source_episode_hash = record.get("source_episode_hash")
    if source_episode_hash:
        return f"source_episode_hash:{source_episode_hash}"
    return f"podcast:{record.get('podcast', 'unknown')}"


def time_bounds(record: dict) -> Tuple[float, float]:
    if record.get("source_start_time") is not None and record.get("source_end_time") is not None:
        return float(record["source_start_time"]), float(record["source_end_time"])
    start = 0.0
    return start, start + float(record["duration"])


def context_object(record: Optional[dict]) -> Optional[dict]:
    if record is None:
        return None
    start, end = time_bounds(record)
    return {
        "id": record.get("id"),
        "wav": record.get("wav"),
        "start_time": start,
        "end_time": end,
        "duration": float(record.get("duration", end - start)),
        "speaker": record.get("speaker"),
        "text": record.get("text", ""),
    }


def add_context_to_group(
    records: List[dict],
    far_threshold_sec: float,
) -> Dict[str, dict]:
    enriched_by_id = {}
    sorted_records = sorted(
        records,
        key=lambda record: (
            time_bounds(record)[0],
            time_bounds(record)[1],
            str(record.get("id", "")),
        ),
    )
    for index, record in enumerate(sorted_records):
        current_start, current_end = time_bounds(record)
        prefix = sorted_records[index - 1] if index > 0 else None
        suffix = sorted_records[index + 1] if index + 1 < len(sorted_records) else None

        output = dict(record)
        output["prefix_context"] = context_object(prefix)
        if prefix is None:
            output["prefix_far"] = None
        else:
            _, prefix_end = time_bounds(prefix)
            output["prefix_far"] = (current_start - prefix_end) > far_threshold_sec

        output["suffix_context"] = context_object(suffix)
        if suffix is None:
            output["suffix_far"] = None
        else:
            suffix_start, _ = time_bounds(suffix)
            output["suffix_far"] = (suffix_start - current_end) > far_threshold_sec

        enriched_by_id[str(record["id"])] = output
    return enriched_by_id


def add_context(records: List[dict], far_threshold_sec: float) -> List[dict]:
    groups = defaultdict(list)
    for record in records:
        groups[source_episode_key(record)].append(record)

    enriched_by_id = {}
    for group_records in groups.values():
        enriched_by_id.update(add_context_to_group(group_records, far_threshold_sec))
    return [enriched_by_id[str(record["id"])] for record in records]


def add_language_prefix(record: dict, language: str) -> dict:
    output = dict(record)
    prefix = f"{language}/"
    wav = str(output.get("wav", ""))
    if wav and not wav.startswith(prefix):
        output["wav"] = prefix + wav
    for key in ("prefix_context", "suffix_context"):
        context = output.get(key)
        if isinstance(context, dict):
            context = dict(context)
            context_wav = str(context.get("wav", ""))
            if context_wav and not context_wav.startswith(prefix):
                context["wav"] = prefix + context_wav
            output[key] = context
    return output


def main() -> None:
    args = get_args()
    language = args.language.upper()
    if not args.podcast_root.is_dir():
        raise FileNotFoundError(args.podcast_root)
    if args.segment_output and args.segment_output.exists() and not args.overwrite:
        raise FileExistsError(f"{args.segment_output} exists; pass --overwrite")

    paths = sorted(args.podcast_root.glob(f"{language}_P*.jsonl"))
    if args.max_files > 0:
        paths = paths[: args.max_files]
    if not paths:
        raise FileNotFoundError(f"No {language}_P*.jsonl files under {args.podcast_root}")

    total = 0
    segment_writer = None
    try:
        if args.segment_output is not None:
            args.segment_output.parent.mkdir(parents=True, exist_ok=True)
            segment_writer = open_text(args.segment_output, "wt")

        for index, path in enumerate(paths, start=1):
            records = list(iter_jsonl(path))
            enriched = add_context(records, args.far_threshold_sec)
            out_path = args.output_podcast_root / path.name
            written = write_jsonl(out_path, enriched, overwrite=args.overwrite)
            total += written
            if segment_writer is not None:
                for record in enriched:
                    segment_writer.write(
                        json.dumps(
                            add_language_prefix(record, language),
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            if index % 100 == 0 or index == len(paths):
                print(
                    f"processed_podcasts={index:,}/{len(paths):,} records={total:,}",
                    flush=True,
                )
    finally:
        if segment_writer is not None:
            segment_writer.close()

    print(f"podcast_files\t{len(paths)}")
    print(f"records\t{total}")
    print(f"output_podcast_root\t{args.output_podcast_root}")
    if args.segment_output is not None:
        print(f"segment_output\t{args.segment_output}")


if __name__ == "__main__":
    main()
