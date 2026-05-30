#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from typing import Iterator

from add_jellycat_context_fields import add_context, add_language_prefix, iter_jsonl, open_text, write_jsonl


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Merge reject JSONLs and optionally write reject-filtered podcast manifests.",
    )
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--id-field", default="id")
    parser.add_argument("--keep", choices=["first", "last"], default="first")
    parser.add_argument("--language", default=None)
    parser.add_argument("--podcast-root", type=Path, default=None)
    parser.add_argument("--output-podcast-root", type=Path, default=None)
    parser.add_argument("--segment-output", type=Path, default=None)
    parser.add_argument("--cut-input", type=Path, action="append", default=[])
    parser.add_argument("--cut-output", type=Path, action="append", default=[])
    parser.add_argument("--far-threshold-sec", type=float, default=30.0)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def load_merged_rejects(paths: list[Path], id_field: str, keep: str) -> tuple[dict[str, dict], list[str], int]:
    merged = {}
    seen_order = []
    input_lines = 0
    for path in paths:
        for record in iter_jsonl(path):
            input_lines += 1
            record_id = str(record[id_field])
            if record_id not in merged:
                seen_order.append(record_id)
                merged[record_id] = record
            elif keep == "last":
                merged[record_id] = record
    return merged, seen_order, input_lines


def write_merged_rejects(path: Path, merged: dict[str, dict], seen_order: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open_text(path, "wt") as f:
        for record_id in seen_order:
            f.write(json.dumps(merged[record_id], ensure_ascii=False) + "\n")


def podcast_paths(root: Path, language: str) -> list[Path]:
    return sorted(root.glob(f"{language}_P*.jsonl"))




def cut_reject_ids(cut: dict) -> set[str]:
    ids = set()
    cut_id = cut.get("id")
    if cut_id is not None:
        ids.add(str(cut_id))
    recording = cut.get("recording")
    if isinstance(recording, dict) and recording.get("id") is not None:
        ids.add(str(recording["id"]))
    for supervision in cut.get("supervisions") or []:
        if not isinstance(supervision, dict):
            continue
        for key in ("id", "recording_id"):
            value = supervision.get(key)
            if value is not None:
                ids.add(str(value))
    return ids


def filter_cut_manifest(input_path: Path, output_path: Path, reject_ids: set[str], overwrite: bool) -> tuple[int, int]:
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"{output_path} exists; pass --overwrite")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    rejected = 0
    with open_text(input_path, "rt") as in_f, open_text(output_path, "wt") as out_f:
        for line in in_f:
            if not line.strip():
                continue
            cut = json.loads(line)
            if cut_reject_ids(cut) & reject_ids:
                rejected += 1
                continue
            out_f.write(json.dumps(cut, ensure_ascii=False) + "\n")
            kept += 1
    return kept, rejected


def filter_cut_manifests(args: argparse.Namespace, reject_ids: set[str]) -> None:
    if len(args.cut_input) != len(args.cut_output):
        raise ValueError("--cut-input and --cut-output must be provided the same number of times")
    for input_path, output_path in zip(args.cut_input, args.cut_output):
        kept, rejected = filter_cut_manifest(input_path, output_path, reject_ids, args.overwrite)
        print(f"cut_input\t{input_path}")
        print(f"cut_output\t{output_path}")
        print(f"cut_records_kept\t{kept}")
        print(f"cut_records_rejected\t{rejected}")


def write_podcast_manifests(args: argparse.Namespace, reject_ids: set[str]) -> tuple[int, int, int]:
    if args.language is None:
        raise ValueError("--language is required with --podcast-root")
    if args.output_podcast_root is None:
        raise ValueError("--output-podcast-root is required with --podcast-root")
    language = args.language.upper()
    paths = podcast_paths(args.podcast_root, language)
    if not paths:
        raise FileNotFoundError(f"No {language}_P*.jsonl files under {args.podcast_root}")

    kept_total = 0
    rejected_total = 0
    segment_writer = None
    try:
        if args.segment_output is not None:
            if args.segment_output.exists() and not args.overwrite:
                raise FileExistsError(f"{args.segment_output} exists; pass --overwrite")
            args.segment_output.parent.mkdir(parents=True, exist_ok=True)
            segment_writer = open_text(args.segment_output, "wt")

        for index, path in enumerate(paths, start=1):
            records = list(iter_jsonl(path))
            kept = [record for record in records if str(record[args.id_field]) not in reject_ids]
            rejected_total += len(records) - len(kept)
            enriched = add_context(kept, args.far_threshold_sec)
            write_jsonl(args.output_podcast_root / path.name, enriched, overwrite=args.overwrite)
            kept_total += len(enriched)
            if segment_writer is not None:
                for record in enriched:
                    segment_writer.write(json.dumps(add_language_prefix(record, language), ensure_ascii=False) + "\n")
            if index % 100 == 0 or index == len(paths):
                print(
                    f"podcasts={index:,}/{len(paths):,} kept={kept_total:,} rejected={rejected_total:,}",
                    flush=True,
                )
    finally:
        if segment_writer is not None:
            segment_writer.close()
    return len(paths), kept_total, rejected_total


def main() -> None:
    args = get_args()
    merged, seen_order, input_lines = load_merged_rejects(args.inputs, args.id_field, args.keep)
    write_merged_rejects(args.output, merged, seen_order)

    print(f"input_lines\t{input_lines}")
    print(f"unique_ids\t{len(seen_order)}")
    print(f"duplicates\t{input_lines - len(seen_order)}")
    print(f"output\t{args.output}")

    reject_ids = set(merged)
    if args.cut_input or args.cut_output:
        filter_cut_manifests(args, reject_ids)

    if args.podcast_root is not None:
        files, kept, rejected = write_podcast_manifests(args, reject_ids)
        print(f"podcast_files\t{files}")
        print(f"podcast_records_kept\t{kept}")
        print(f"podcast_records_rejected\t{rejected}")
        print(f"output_podcast_root\t{args.output_podcast_root}")
        if args.segment_output is not None:
            print(f"segment_output\t{args.segment_output}")


if __name__ == "__main__":
    main()
