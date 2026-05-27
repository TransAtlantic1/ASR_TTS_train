#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
from pathlib import Path

from lhotse import RecordingSet, SupervisionSet
from lhotse.serialization import load_manifest_lazy_or_eager


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--recordings-manifest", type=Path, required=True)
    parser.add_argument("--supervisions-manifest", type=Path, required=True)
    parser.add_argument("--recording-output-dir", type=Path, required=True)
    parser.add_argument("--supervision-output-dir", type=Path, required=True)
    parser.add_argument("--manifest-prefix", type=str, required=True)
    parser.add_argument("--num-splits", type=int, required=True)
    return parser.parse_args()


def iter_manifest(path: Path):
    manifest = load_manifest_lazy_or_eager(path)
    if manifest is None:
        raise ValueError(f"Unable to load manifest: {path}")
    return iter(manifest)


def count_items(path: Path) -> int:
    return sum(1 for _ in iter_manifest(path))


def unlink_old(output_dir: Path, pattern: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob(pattern):
        path.unlink()
    marker = output_dir / ".split_completed"
    if marker.exists():
        marker.unlink()


def main() -> None:
    args = get_args()
    if args.num_splits <= 0:
        raise ValueError(f"--num-splits must be positive, got {args.num_splits}")

    num_recordings = count_items(args.recordings_manifest)
    num_supervisions = count_items(args.supervisions_manifest)
    if num_recordings != num_supervisions:
        raise ValueError(
            "Expected 1:1 train recordings/supervisions before paired split, "
            f"got recordings={num_recordings}, supervisions={num_supervisions}"
        )

    unlink_old(
        args.recording_output_dir,
        f"{args.manifest_prefix}_recordings_train.*.jsonl.gz",
    )
    unlink_old(
        args.supervision_output_dir,
        f"{args.manifest_prefix}_supervisions_train.*.jsonl.gz",
    )

    shard_size = max(1, math.ceil(num_recordings / args.num_splits))
    rec_iter = iter_manifest(args.recordings_manifest)
    sup_iter = iter_manifest(args.supervisions_manifest)

    written = 0
    for shard_idx in range(args.num_splits):
        rec_path = (
            args.recording_output_dir
            / f"{args.manifest_prefix}_recordings_train.{shard_idx:04d}.jsonl.gz"
        )
        sup_path = (
            args.supervision_output_dir
            / f"{args.manifest_prefix}_supervisions_train.{shard_idx:04d}.jsonl.gz"
        )
        with RecordingSet.open_writer(rec_path) as rec_writer, SupervisionSet.open_writer(
            sup_path
        ) as sup_writer:
            for _ in range(shard_size):
                try:
                    recording = next(rec_iter)
                    supervision = next(sup_iter)
                except StopIteration:
                    break
                if supervision.recording_id != recording.id:
                    raise ValueError(
                        "Recording/supervision order mismatch while splitting: "
                        f"recording.id={recording.id}, "
                        f"supervision.recording_id={supervision.recording_id}"
                    )
                rec_writer.write(recording)
                sup_writer.write(supervision)
                written += 1

    if written != num_recordings:
        raise ValueError(f"Expected to write {num_recordings} pairs, wrote {written}")

    try:
        next(rec_iter)
        raise ValueError("Recording iterator has unexpected remaining items")
    except StopIteration:
        pass
    try:
        next(sup_iter)
        raise ValueError("Supervision iterator has unexpected remaining items")
    except StopIteration:
        pass

    (args.recording_output_dir / ".split_completed").touch()
    (args.supervision_output_dir / ".split_completed").touch()
    print(
        f"split {written} paired train items into {args.num_splits} shards "
        f"under {args.recording_output_dir} and {args.supervision_output_dir}"
    )


if __name__ == "__main__":
    main()
