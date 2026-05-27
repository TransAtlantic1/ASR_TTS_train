#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from bench_registry import BENCH2_ROOT, specs_for
from prepare_bench import load_existing_registry, write_dataset_metadata
from validate_bench_assets import parse_csv, validate_datasets


def get_parser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--language", type=str, required=True, choices=["zh", "en"])
    parser.add_argument("--datasets", type=str, required=True)
    parser.add_argument("--stage-root", type=Path, required=True)
    parser.add_argument("--live-root", type=Path, default=BENCH2_ROOT)
    parser.add_argument("--metadata-root", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, default=None)
    parser.add_argument("--max-issues", type=int, default=20)
    return parser


def ensure_valid_assets(root: Path, dataset_ids: List[str], max_issues: int) -> None:
    results = validate_datasets(root, dataset_ids, max_issues=max_issues)
    failures = [result.dataset_id for result in results if not result.ok]
    if failures:
        raise ValueError(
            f"Asset validation failed under {root}: {', '.join(sorted(failures))}"
        )


def atomic_symlink_replace(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_link = target.parent / f".{target.name}.tmp-link"
    if tmp_link.exists() or tmp_link.is_symlink():
        tmp_link.unlink()
    tmp_link.symlink_to(source)
    tmp_link.replace(target)


def main() -> None:
    args = get_parser().parse_args()
    dataset_ids = parse_csv(args.datasets)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_root = args.archive_root or (args.live_root / "_archive" / timestamp)

    ensure_valid_assets(args.stage_root, dataset_ids, args.max_issues)

    promoted = {}
    for spec in specs_for(args.language, dataset_ids):
        staged_dataset_root = (args.stage_root / spec.dataset_id).resolve()
        if not staged_dataset_root.exists():
            raise FileNotFoundError(f"Missing staged dataset root: {staged_dataset_root}")

        live_dataset_root = args.live_root / spec.dataset_id
        archive_path = archive_root / spec.dataset_id
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        if live_dataset_root.exists() or live_dataset_root.is_symlink():
            if archive_path.exists() or archive_path.is_symlink():
                raise FileExistsError(f"Archive path already exists: {archive_path}")
            live_dataset_root.rename(archive_path)

        atomic_symlink_replace(staged_dataset_root, live_dataset_root)
        prepared_cut_path = live_dataset_root / "fbank" / f"{spec.dataset_id}_cuts.jsonl.gz"
        write_dataset_metadata(
            spec,
            args.live_root,
            prepared_cut_path,
            metadata_root=args.metadata_root,
            status="prepared",
        )
        promoted[spec.dataset_id] = str(prepared_cut_path)

    ensure_valid_assets(args.live_root, dataset_ids, args.max_issues)

    registry_path = args.live_root / "registry" / f"{args.language}_prepared.tsv"
    existing: Dict[str, str] = load_existing_registry(registry_path)
    existing.update(promoted)
    with open(registry_path, "w", encoding="utf-8") as f:
        f.write("dataset_id\tcuts_path\n")
        for dataset_id, cuts_path in sorted(existing.items()):
            f.write(f"{dataset_id}\t{cuts_path}\n")

    print(
        json.dumps(
            {
                "live_root": str(args.live_root),
                "stage_root": str(args.stage_root),
                "archive_root": str(archive_root),
                "datasets": dataset_ids,
                "registry_path": str(registry_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
