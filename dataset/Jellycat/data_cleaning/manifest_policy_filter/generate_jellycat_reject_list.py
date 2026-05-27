#!/usr/bin/env python3

import argparse
import gzip
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Tuple


DEFAULT_PODCAST_ROOT = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/ZH"
)
DEFAULT_OUTPUT_DIR = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH"
)


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Generate reject-list JSONL files for Jellycat abnormal utterances.",
    )
    parser.add_argument("--language", default="ZH")
    parser.add_argument("--podcast-root", type=Path, default=DEFAULT_PODCAST_ROOT)
    parser.add_argument(
        "--segment-manifest",
        type=Path,
        default=None,
        help="Optional merged segment JSONL/JSONL.GZ manifest to scan directly.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--prefix", default=None)
    parser.add_argument("--duration-threshold", type=float, default=60.0)
    parser.add_argument("--chars-per-sec-threshold", type=float, default=1.0)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--chunk-size", type=int, default=128)
    parser.add_argument("--examples-limit", type=int, default=20)
    return parser.parse_args()


def chunked(items: List[Path], chunk_size: int) -> Iterable[List[Path]]:
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_records(path: Path) -> Iterator[dict]:
    with open_text(path) as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def bucket_duration(duration: float) -> str:
    if duration <= 1:
        return "(0,1]"
    if duration <= 3:
        return "(1,3]"
    if duration <= 5:
        return "(3,5]"
    if duration <= 10:
        return "(5,10]"
    if duration <= 30:
        return "(10,30]"
    if duration <= 60:
        return "(30,60]"
    if duration <= 120:
        return "(60,120]"
    if duration <= 300:
        return "(120,300]"
    if duration <= 600:
        return "(300,600]"
    return "(600,inf)"


def bucket_text_len(text_len: int) -> str:
    if text_len == 0:
        return "0"
    if text_len <= 10:
        return "(0,10]"
    if text_len <= 30:
        return "(10,30]"
    if text_len <= 60:
        return "(30,60]"
    if text_len <= 120:
        return "(60,120]"
    if text_len <= 240:
        return "(120,240]"
    if text_len <= 480:
        return "(240,480]"
    if text_len <= 960:
        return "(480,960]"
    return "(960,inf)"


def bucket_chars_per_sec(chars_per_sec: float) -> str:
    if chars_per_sec < 0.1:
        return "[0,0.1)"
    if chars_per_sec < 0.5:
        return "[0.1,0.5)"
    if chars_per_sec < 1:
        return "[0.5,1)"
    if chars_per_sec < 2:
        return "[1,2)"
    if chars_per_sec < 4:
        return "[2,4)"
    if chars_per_sec < 8:
        return "[4,8)"
    if chars_per_sec < 16:
        return "[8,16)"
    return "[16,inf)"


def update_distribution_stats(stats: Counter, duration: float, text_len: int) -> None:
    chars_per_sec = text_len / duration if duration > 0 else 0.0
    stats["records"] += 1
    stats["duration_sum_sec"] += duration
    stats["text_len_sum"] += text_len
    stats["chars_per_sec_sum"] += chars_per_sec
    stats[f"duration_bucket:{bucket_duration(duration)}"] += 1
    stats[f"text_len_bucket:{bucket_text_len(text_len)}"] += 1
    stats[f"chars_per_sec_bucket:{bucket_chars_per_sec(chars_per_sec)}"] += 1
    stats["duration_min_sec"] = (
        duration
        if "duration_min_sec" not in stats
        else min(float(stats["duration_min_sec"]), duration)
    )
    stats["duration_max_sec"] = max(float(stats.get("duration_max_sec", 0.0)), duration)
    stats["text_len_min"] = (
        text_len
        if "text_len_min" not in stats
        else min(int(stats["text_len_min"]), text_len)
    )
    stats["text_len_max"] = max(int(stats.get("text_len_max", 0)), text_len)
    stats["chars_per_sec_min"] = (
        chars_per_sec
        if "chars_per_sec_min" not in stats
        else min(float(stats["chars_per_sec_min"]), chars_per_sec)
    )
    stats["chars_per_sec_max"] = max(
        float(stats.get("chars_per_sec_max", 0.0)), chars_per_sec
    )


def make_candidate(record: dict, duration: float, text: str, reason: str) -> Dict:
    text_len = len(text)
    return {
        "id": record["id"],
        "reason": reason,
        "duration_sec": duration,
        "text_len": text_len,
        "chars_per_sec": text_len / duration if duration > 0 else 0.0,
        "podcast": record.get("podcast"),
        "speaker": record.get("speaker"),
        "wav": record.get("wav"),
        "text": text,
        "source_language": record.get("source_language"),
        "source_manifest_id": record.get("source_manifest_id"),
        "source_wav": record.get("source_wav"),
        "source_start_time": record.get("source_start_time"),
        "source_end_time": record.get("source_end_time"),
    }


def scan_chunk(
    paths: List[str], duration_threshold: float, chars_per_sec_threshold: float
) -> Tuple[List[Dict], List[Dict], Dict]:
    broad = []
    strict = []
    stats = Counter()
    for path_s in paths:
        path = Path(path_s)
        for record in iter_records(path):
            duration = float(record["duration"])
            text = str(record.get("text", ""))
            text_len = len(text)
            update_distribution_stats(stats, duration, text_len)
            if duration <= duration_threshold:
                continue
            chars_per_sec = text_len / duration if duration > 0 else 0.0
            item = make_candidate(record, duration, text, "duration_gt_threshold")
            broad.append(item)
            stats["broad"] += 1
            stats[f"source_language:{record.get('source_language', 'unknown')}"] += 1
            if chars_per_sec < chars_per_sec_threshold:
                strict_item = dict(item)
                strict_item["reason"] = "duration_gt_threshold_and_low_chars_per_sec"
                strict.append(strict_item)
                stats["strict"] += 1
    return broad, strict, dict(stats)


def scan_manifest(
    path: Path, duration_threshold: float, chars_per_sec_threshold: float
) -> Tuple[List[Dict], List[Dict], Dict]:
    broad = []
    strict = []
    stats = Counter()
    for record in iter_records(path):
        duration = float(record["duration"])
        text = str(record.get("text", ""))
        text_len = len(text)
        update_distribution_stats(stats, duration, text_len)
        if duration <= duration_threshold:
            continue
        chars_per_sec = text_len / duration if duration > 0 else 0.0
        item = make_candidate(record, duration, text, "duration_gt_threshold")
        broad.append(item)
        stats["broad"] += 1
        stats[f"source_language:{record.get('source_language', 'unknown')}"] += 1
        if chars_per_sec < chars_per_sec_threshold:
            strict_item = dict(item)
            strict_item["reason"] = "duration_gt_threshold_and_low_chars_per_sec"
            strict.append(strict_item)
            stats["strict"] += 1
    return broad, strict, dict(stats)


def write_jsonl(path: Path, records: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def stats_with_prefix(stats: Counter, prefix: str) -> dict:
    return {
        key.split(":", 1)[1]: value
        for key, value in sorted(stats.items())
        if key.startswith(prefix)
    }


def merge_stats(left: Counter, right: Dict) -> None:
    for key, value in right.items():
        if key in {"duration_min_sec", "text_len_min", "chars_per_sec_min"}:
            left[key] = value if key not in left else min(left[key], value)
        elif key in {"duration_max_sec", "text_len_max", "chars_per_sec_max"}:
            left[key] = max(left.get(key, value), value)
        else:
            left[key] += value


def make_distribution_summary(stats: Counter) -> dict:
    records = int(stats.get("records", 0))
    duration_sum = float(stats.get("duration_sum_sec", 0.0))
    text_len_sum = int(stats.get("text_len_sum", 0))
    chars_per_sec_sum = float(stats.get("chars_per_sec_sum", 0.0))
    return {
        "records": records,
        "duration_sum_sec": duration_sum,
        "duration_mean_sec": duration_sum / records if records else 0.0,
        "duration_min_sec": float(stats.get("duration_min_sec", 0.0)),
        "duration_max_sec": float(stats.get("duration_max_sec", 0.0)),
        "text_len_mean": text_len_sum / records if records else 0.0,
        "text_len_min": int(stats.get("text_len_min", 0)),
        "text_len_max": int(stats.get("text_len_max", 0)),
        "chars_per_sec_mean": chars_per_sec_sum / records if records else 0.0,
        "chars_per_sec_min": float(stats.get("chars_per_sec_min", 0.0)),
        "chars_per_sec_max": float(stats.get("chars_per_sec_max", 0.0)),
        "duration_buckets": stats_with_prefix(stats, "duration_bucket:"),
        "text_len_buckets": stats_with_prefix(stats, "text_len_bucket:"),
        "chars_per_sec_buckets": stats_with_prefix(stats, "chars_per_sec_bucket:"),
    }


def main() -> None:
    args = get_args()
    language = args.language.upper()
    prefix = args.prefix or f"jellycat_{language}_reject_candidates"

    broad_records: List[Dict] = []
    strict_records: List[Dict] = []
    merged_stats = Counter()
    if args.segment_manifest is not None:
        paths = [args.segment_manifest]
        if not args.segment_manifest.is_file():
            raise FileNotFoundError(args.segment_manifest)
        broad, strict, stats = scan_manifest(
            args.segment_manifest,
            args.duration_threshold,
            args.chars_per_sec_threshold,
        )
        broad_records.extend(broad)
        strict_records.extend(strict)
        merge_stats(merged_stats, stats)
    else:
        paths = sorted(args.podcast_root.glob(f"{language}_P*.jsonl"))
        if not paths:
            raise FileNotFoundError(
                f"No podcast JSONL files found under {args.podcast_root}"
            )

        chunks = [[str(p) for p in chunk] for chunk in chunked(paths, args.chunk_size)]

        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futures = [
                ex.submit(
                    scan_chunk,
                    chunk,
                    args.duration_threshold,
                    args.chars_per_sec_threshold,
                )
        for chunk in chunks
            ]
            for future in as_completed(futures):
                broad, strict, stats = future.result()
                broad_records.extend(broad)
                strict_records.extend(strict)
                merge_stats(merged_stats, stats)

    broad_records.sort(key=lambda item: (-item["duration_sec"], item["id"]))
    strict_records.sort(
        key=lambda item: (item["chars_per_sec"], -item["duration_sec"], item["id"])
    )

    broad_name = f"{prefix}.duration_gt_{int(args.duration_threshold)}s.jsonl"
    strict_name = (
        f"{prefix}.duration_gt_{int(args.duration_threshold)}s"
        f".chars_per_sec_lt_{str(args.chars_per_sec_threshold).replace('.', 'p')}.jsonl"
    )
    broad_path = args.output_dir / broad_name
    strict_path = args.output_dir / strict_name
    summary_path = args.output_dir / f"{prefix}.summary.json"

    write_jsonl(broad_path, broad_records)
    write_jsonl(strict_path, strict_records)

    summary = {
        "language": language,
        "scan_source": "segment_manifest" if args.segment_manifest is not None else "podcast_manifests",
        "segment_manifest": str(args.segment_manifest) if args.segment_manifest else None,
        "podcast_root": str(args.podcast_root),
        "num_input_manifests": len(paths),
        "duration_threshold_sec": args.duration_threshold,
        "chars_per_sec_threshold": args.chars_per_sec_threshold,
        "broad_reject_jsonl": str(broad_path),
        "strict_reject_jsonl": str(strict_path),
        "broad_count": len(broad_records),
        "strict_count": len(strict_records),
        "distribution": make_distribution_summary(merged_stats),
        "source_languages": {
            key.split(":", 1)[1]: value
            for key, value in merged_stats.items()
            if key.startswith("source_language:")
        },
        "examples_strict_lowest_chars_per_sec": strict_records[: args.examples_limit],
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"broad_count\t{len(broad_records)}")
    print(f"strict_count\t{len(strict_records)}")
    print(f"broad_path\t{broad_path}")
    print(f"strict_path\t{strict_path}")
    print(f"summary_path\t{summary_path}")


if __name__ == "__main__":
    main()
