#!/usr/bin/env python3

import argparse
import gzip
import json
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            "Rewrite JSONL/JSONL.GZ files by applying a reject id list and an "
            "optional parent-to-children split map. Designed for Jellycat "
            "manifests and stage7-before Lhotse raw cut JSONLs."
        ),
    )
    parser.add_argument("--reject-jsonl", type=Path, default=None)
    parser.add_argument("--split-map-jsonl", type=Path, default=None)
    parser.add_argument(
        "--input",
        type=Path,
        action="append",
        required=True,
        help="Input JSONL/JSONL.GZ file. Can be repeated.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--match-field",
        choices=["auto", "id", "recording.id", "supervision.recording_id"],
        default="auto",
        help=(
            "Field used to match reject/split parent ids. `auto` uses "
            "recording.id for Lhotse MonoCut-like records, otherwise id."
        ),
    )
    parser.add_argument(
        "--child-field",
        default="auto",
        help=(
            "Child payload field in split-map records. `auto` accepts `cut`, "
            "`record`, `segment`, or the child object itself."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting output files.",
    )
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


def load_reject_ids(path: Optional[Path]) -> Set[str]:
    if path is None:
        return set()
    ids = set()
    for record in iter_jsonl(path):
        ids.add(str(record["id"]))
    return ids


def child_payload(child: dict, child_field: str) -> dict:
    if child_field != "auto":
        if child_field not in child:
            raise KeyError(f"Missing child field `{child_field}` in split child: {child}")
        return child[child_field]
    for key in ("cut", "record", "segment"):
        value = child.get(key)
        if isinstance(value, dict):
            return value
    return child


def load_split_map(path: Optional[Path], child_field: str) -> Dict[str, List[dict]]:
    if path is None:
        return {}
    mapping: Dict[str, List[dict]] = {}
    for record in iter_jsonl(path):
        parent_id = str(record["parent_id"])
        children = record.get("children", [])
        if not isinstance(children, list):
            raise ValueError(f"`children` must be a list for parent {parent_id}")
        mapping[parent_id] = [child_payload(child, child_field) for child in children]
    return mapping


def nested_get(record: dict, path: str) -> Optional[str]:
    value = record
    for part in path.split("."):
        if isinstance(value, list):
            if not value:
                return None
            value = value[0]
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return str(value)


def match_id(record: dict, match_field: str) -> str:
    if match_field == "id":
        return str(record["id"])
    if match_field == "recording.id":
        value = nested_get(record, "recording.id")
        if value is None:
            raise KeyError("recording.id")
        return value
    if match_field == "supervision.recording_id":
        value = nested_get(record, "supervisions.recording_id")
        if value is None:
            raise KeyError("supervisions[0].recording_id")
        return value

    recording_id = nested_get(record, "recording.id")
    if recording_id is not None:
        return recording_id
    return str(record["id"])


def output_path_for(input_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / input_path.name


def rewrite_one(
    *,
    input_path: Path,
    output_path: Path,
    reject_ids: Set[str],
    split_map: Dict[str, List[dict]],
    match_field: str,
    overwrite: bool,
) -> dict:
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"{output_path} exists; pass --overwrite")

    stats = {
        "input": str(input_path),
        "output": str(output_path),
        "seen": 0,
        "kept": 0,
        "rejected": 0,
        "split_parents": 0,
        "split_children_written": 0,
    }
    with open_text(output_path, "wt") as out_f:
        for record in iter_jsonl(input_path):
            stats["seen"] += 1
            key = match_id(record, match_field)
            if key in split_map:
                stats["split_parents"] += 1
                for child in split_map[key]:
                    out_f.write(json.dumps(child, ensure_ascii=False) + "\n")
                    stats["split_children_written"] += 1
                continue
            if key in reject_ids:
                stats["rejected"] += 1
                continue
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            stats["kept"] += 1
    return stats


def main() -> None:
    args = get_args()
    reject_ids = load_reject_ids(args.reject_jsonl)
    split_map = load_split_map(args.split_map_jsonl, args.child_field)

    summaries = []
    for input_path in args.input:
        if not input_path.is_file():
            raise FileNotFoundError(input_path)
        out_path = output_path_for(input_path, args.output_dir)
        summaries.append(
            rewrite_one(
                input_path=input_path,
                output_path=out_path,
                reject_ids=reject_ids,
                split_map=split_map,
                match_field=args.match_field,
                overwrite=args.overwrite,
            )
        )

    summary = {
        "reject_jsonl": str(args.reject_jsonl) if args.reject_jsonl else None,
        "split_map_jsonl": str(args.split_map_jsonl) if args.split_map_jsonl else None,
        "output_dir": str(args.output_dir),
        "inputs": summaries,
    }
    summary_path = args.output_dir / "rewrite_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
