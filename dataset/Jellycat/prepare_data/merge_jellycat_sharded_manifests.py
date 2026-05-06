#!/usr/bin/env python3

import argparse
import gzip
import json
import logging
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_MANIFEST_DIR = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/"
    "Jellycat/manifests/ZH"
)
DEFAULT_STEM = "jellycat_ZH"
DEFAULT_NUM_SHARDS = 16


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Merge Jellycat sharded manifests into single jsonl.gz files.",
    )
    parser.add_argument("--manifest-dir", type=Path, default=DEFAULT_MANIFEST_DIR)
    parser.add_argument("--stem", default=DEFAULT_STEM)
    parser.add_argument("--num-shards", type=int, default=DEFAULT_NUM_SHARDS)
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Directory for moving sharded manifests after successful merge.",
    )
    parser.add_argument(
        "--keep-shards",
        action="store_true",
        help="Keep sharded manifests in place instead of moving them to backup.",
    )
    return parser.parse_args()


def manifest_names(stem: str) -> list[str]:
    return [
        f"{stem}_segments",
        f"{stem}_rejected",
        f"{stem}_recordings",
        f"{stem}_supervisions",
    ]


def shard_path(manifest_dir: Path, name: str, shard_index: int, num_shards: int) -> Path:
    return manifest_dir / f"{name}.shard{shard_index:05d}-of-{num_shards:05d}.jsonl.gz"


def output_path(manifest_dir: Path, name: str) -> Path:
    return manifest_dir / f"{name}.jsonl.gz"


def summary_shard_path(manifest_dir: Path, stem: str, shard_index: int, num_shards: int) -> Path:
    return manifest_dir / (
        f"{stem}_segments.shard{shard_index:05d}-of-{num_shards:05d}.summary.json"
    )


def add_stats(left: dict, right: dict) -> dict:
    output = dict(left)
    for key, value in right.items():
        if isinstance(value, (int, float)):
            output[key] = output.get(key, 0) + value
        elif key not in output:
            output[key] = value
    return output


def load_summaries(manifest_dir: Path, stem: str, num_shards: int) -> list[dict]:
    summaries = []
    for shard_index in range(num_shards):
        path = summary_shard_path(manifest_dir, stem, shard_index, num_shards)
        if not path.is_file():
            raise FileNotFoundError(f"Missing shard summary: {path}")
        with path.open("r", encoding="utf-8") as f:
            summaries.append(json.load(f))
    return summaries


def combine_summaries(
    summaries: list[dict],
    manifest_dir: Path,
    stem: str,
    num_shards: int,
    line_counts: dict[str, int],
) -> dict:
    base = dict(summaries[0])
    total_stats = {}
    per_language_stats = {}
    id_map_counts = base.get("id_map_counts", {})

    for summary in summaries:
        total_stats = add_stats(total_stats, summary.get("total_stats", {}))
        for language, stats in summary.get("per_language_stats", {}).items():
            per_language_stats[language] = add_stats(
                per_language_stats.get(language, {}), stats
            )

    base.update(
        {
            "status": "prepared_merged",
            "summary_count": 1,
            "original_num_shards": num_shards,
            "num_shards": 1,
            "shard_index": 0,
            "segment_manifest": str(output_path(manifest_dir, f"{stem}_segments")),
            "rejected_manifest": str(output_path(manifest_dir, f"{stem}_rejected")),
            "lhotse_recordings": str(output_path(manifest_dir, f"{stem}_recordings")),
            "lhotse_supervisions": str(output_path(manifest_dir, f"{stem}_supervisions")),
            "total_stats": total_stats,
            "per_language_stats": per_language_stats,
            "id_map_counts": id_map_counts,
            "merged_line_counts": line_counts,
        }
    )
    return base


def validate_inputs(manifest_dir: Path, names: list[str], num_shards: int) -> None:
    missing = []
    existing_outputs = []
    for name in names:
        out_path = output_path(manifest_dir, name)
        if out_path.exists():
            existing_outputs.append(str(out_path))
        for shard_index in range(num_shards):
            path = shard_path(manifest_dir, name, shard_index, num_shards)
            if not path.is_file():
                missing.append(str(path))
    if existing_outputs:
        raise FileExistsError(
            "Merged manifest already exists; move it first: " + ", ".join(existing_outputs)
        )
    if missing:
        raise FileNotFoundError("Missing shard manifests:\n" + "\n".join(missing))


def merge_one(manifest_dir: Path, name: str, num_shards: int) -> int:
    out_path = output_path(manifest_dir, name)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    line_count = 0

    logging.info("Merging %s -> %s", name, out_path)
    with gzip.open(tmp_path, "wt", encoding="utf-8") as out_f:
        for shard_index in range(num_shards):
            in_path = shard_path(manifest_dir, name, shard_index, num_shards)
            shard_lines = 0
            with gzip.open(in_path, "rt", encoding="utf-8") as in_f:
                for line in in_f:
                    out_f.write(line)
                    line_count += 1
                    shard_lines += 1
            logging.info("%s shard %05d lines=%d", name, shard_index, shard_lines)

    tmp_path.replace(out_path)
    logging.info("Merged %s lines=%d", out_path, line_count)
    return line_count


def validate_merged(manifest_dir: Path, name: str, expected_lines: int) -> None:
    path = output_path(manifest_dir, name)
    actual = 0
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for actual, _ in enumerate(f, start=1):
            pass
    if actual != expected_lines:
        raise ValueError(f"{path} lines={actual}, expected={expected_lines}")
    logging.info("Validated %s lines=%d", path, actual)


def move_shards_to_backup(
    manifest_dir: Path,
    backup_dir: Path,
    names: list[str],
    stem: str,
    num_shards: int,
) -> None:
    backup_dir.mkdir(parents=True, exist_ok=False)
    moved = []
    for name in names:
        for shard_index in range(num_shards):
            src = shard_path(manifest_dir, name, shard_index, num_shards)
            dst = backup_dir / src.name
            shutil.move(str(src), str(dst))
            moved.append(dst.name)
    for shard_index in range(num_shards):
        src = summary_shard_path(manifest_dir, stem, shard_index, num_shards)
        dst = backup_dir / src.name
        shutil.move(str(src), str(dst))
        moved.append(dst.name)

    manifest = backup_dir / "backup_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_manifest_dir": str(manifest_dir),
                "moved_files": moved,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    logging.info("Moved %d sharded files to %s", len(moved), backup_dir)


def main() -> None:
    args = get_args()
    names = manifest_names(args.stem)
    validate_inputs(args.manifest_dir, names, args.num_shards)
    summaries = load_summaries(args.manifest_dir, args.stem, args.num_shards)

    line_counts = {}
    for name in names:
        line_counts[name] = merge_one(args.manifest_dir, name, args.num_shards)
    for name in names:
        validate_merged(args.manifest_dir, name, line_counts[name])

    summary = combine_summaries(
        summaries=summaries,
        manifest_dir=args.manifest_dir,
        stem=args.stem,
        num_shards=args.num_shards,
        line_counts=line_counts,
    )
    summary_path = args.manifest_dir / f"{args.stem}_segments.summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logging.info("Wrote merged summary: %s", summary_path)

    if not args.keep_shards:
        backup_dir = args.backup_dir
        if backup_dir is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_dir = args.manifest_dir / f"sharded_manifest_backup_{stamp}"
        move_shards_to_backup(
            manifest_dir=args.manifest_dir,
            backup_dir=backup_dir,
            names=names,
            stem=args.stem,
            num_shards=args.num_shards,
        )


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
        level=logging.INFO,
    )
    main()
