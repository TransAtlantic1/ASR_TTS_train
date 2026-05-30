#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import heapq
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, TextIO


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with open_text(path) as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc


def record_id(record: Dict[str, Any], id_field: str) -> str | None:
    value = record.get(id_field)
    if value is None:
        value = record.get("task_id")
    if value is None:
        return None
    return str(value)


def duration_value(record: Dict[str, Any], duration_field: str) -> float:
    try:
        value = float(record.get(duration_field))
    except (TypeError, ValueError):
        return 0.0
    if value != value or value < 0:
        return 0.0
    return value


def load_done_ids(paths: list[Path], id_field: str) -> set[str]:
    done: set[str] = set()
    for path in paths:
        if not path.exists():
            print(f"[WARN] done output missing, skipping: {path}", file=sys.stderr)
            continue
        for rec in iter_jsonl(path):
            rec_id = record_id(rec, id_field)
            if rec_id is not None:
                done.add(rec_id)
        print(f"[INFO] loaded done ids={len(done)} after {path}", file=sys.stderr)
    return done


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Split remaining Jellycat manifest records into balanced JSONL parts. "
            "Records whose id already appears in --done-output are skipped."
        )
    )
    ap.add_argument("--manifest", required=True, help="Input source manifest, .jsonl or .jsonl.gz")
    ap.add_argument(
        "--done-output",
        action="append",
        default=[],
        help="Existing sidecar output JSONL to treat as completed; can repeat.",
    )
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--prefix", default="zh.remaining")
    ap.add_argument("--parts", type=int, default=2)
    ap.add_argument("--id-field", default="id")
    ap.add_argument("--duration-field", default="duration")
    ap.add_argument("--progress-interval", type=int, default=500000)
    ap.add_argument("--summary", help="Optional summary JSON path; defaults to output-dir/summary.json")
    ap.add_argument("--overwrite", action="store_true")
    return ap


def main() -> int:
    args = build_arg_parser().parse_args()
    if args.parts < 2:
        raise SystemExit("--parts must be at least 2")

    manifest = Path(args.manifest)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = Path(args.summary) if args.summary else output_dir / "summary.json"

    part_paths = [output_dir / f"{args.prefix}.part{i:02d}.jsonl" for i in range(args.parts)]
    tmp_paths = [path.with_suffix(path.suffix + ".tmp") for path in part_paths]
    if not args.overwrite:
        existing = [str(path) for path in [*part_paths, *tmp_paths, summary_path] if path.exists()]
        if existing:
            raise SystemExit("Refusing to overwrite existing outputs:\n" + "\n".join(existing))

    for path in tmp_paths:
        if path.exists():
            path.unlink()

    done_ids = load_done_ids([Path(p) for p in args.done_output], args.id_field)

    started = utc_now()
    part_counts = [0 for _ in range(args.parts)]
    part_durations = [0.0 for _ in range(args.parts)]
    heap = [(0.0, idx) for idx in range(args.parts)]
    heapq.heapify(heap)

    total = 0
    kept = 0
    skipped_done = 0
    missing_id = 0
    missing_duration = 0

    files = [path.open("w", encoding="utf-8") for path in tmp_paths]
    try:
        for rec in iter_jsonl(manifest):
            total += 1
            rec_id = record_id(rec, args.id_field)
            if rec_id is None:
                missing_id += 1
                continue
            if rec_id in done_ids:
                skipped_done += 1
                continue

            dur = duration_value(rec, args.duration_field)
            if dur <= 0:
                missing_duration += 1

            current_duration, part_idx = heapq.heappop(heap)
            files[part_idx].write(json.dumps(rec, ensure_ascii=False) + "\n")
            part_counts[part_idx] += 1
            part_durations[part_idx] += dur
            kept += 1
            heapq.heappush(heap, (current_duration + dur, part_idx))

            if args.progress_interval > 0 and total % args.progress_interval == 0:
                print(
                    f"[INFO] scanned={total} kept={kept} skipped_done={skipped_done} "
                    f"part_counts={part_counts}",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        for f in files:
            f.close()

    for tmp, final in zip(tmp_paths, part_paths):
        tmp.replace(final)

    summary = {
        "started_utc": started,
        "finished_utc": utc_now(),
        "manifest": str(manifest),
        "done_outputs": [str(Path(p)) for p in args.done_output],
        "done_ids": len(done_ids),
        "scanned_records": total,
        "remaining_records": kept,
        "skipped_done": skipped_done,
        "missing_id": missing_id,
        "missing_or_invalid_duration": missing_duration,
        "parts": [
            {
                "index": idx,
                "path": str(path),
                "records": part_counts[idx],
                "duration_sec": round(part_durations[idx], 3),
                "duration_hours": round(part_durations[idx] / 3600.0, 6),
            }
            for idx, path in enumerate(part_paths)
        ],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
