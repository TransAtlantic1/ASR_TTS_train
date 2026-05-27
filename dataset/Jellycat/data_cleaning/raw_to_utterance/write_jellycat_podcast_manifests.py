#!/usr/bin/env python3

import argparse
import gzip
import json
import logging
import time
from collections import Counter, OrderedDict
from pathlib import Path


DEFAULT_OUTPUT_ROOT = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat"
)


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Write Emilia-style per-podcast JSONL manifests for Jellycat.",
    )
    parser.add_argument("--segment-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--language", required=True, help="Target language, e.g. EN.")
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Optional merged summary JSON to update with podcast manifest metadata.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Optional standalone podcast manifest summary JSON path.",
    )
    parser.add_argument(
        "--progress-path",
        type=Path,
        default=None,
        help="Optional progress JSON path.",
    )
    parser.add_argument("--progress-interval-lines", type=int, default=100000)
    parser.add_argument("--max-open-files", type=int, default=256)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def progress_bar(percent, width: int = 40) -> str:
    if percent is None:
        return "[" + ("?" * width) + "]"
    percent = max(0.0, min(100.0, percent))
    filled = int(round((percent / 100.0) * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + f"] {percent:6.2f}%"


def write_progress(args: argparse.Namespace, payload: dict) -> None:
    if args.progress_path is None:
        return
    payload = dict(payload)
    payload["updated_at_unix"] = time.time()
    payload["bar"] = progress_bar(payload.get("percent"))
    args.progress_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = args.progress_path.with_suffix(args.progress_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(args.progress_path)


def normalize_record(record: dict, language: str) -> dict:
    output = dict(record)
    prefix = f"{language}/"
    wav = str(output.get("wav", ""))
    if wav.startswith(prefix):
        output["wav"] = wav[len(prefix):]
    return output


class WriterCache:
    def __init__(self, max_open: int):
        self.max_open = max_open
        self._writers = OrderedDict()

    def get(self, path: Path):
        writer = self._writers.pop(path, None)
        if writer is not None:
            self._writers[path] = writer
            return writer

        path.parent.mkdir(parents=True, exist_ok=True)
        writer = path.open("a", encoding="utf-8")
        self._writers[path] = writer
        while len(self._writers) > self.max_open:
            _, old_writer = self._writers.popitem(last=False)
            old_writer.close()
        return writer

    def close(self) -> None:
        for writer in self._writers.values():
            writer.close()
        self._writers.clear()


def preflight(language_root: Path, segment_manifest: Path, overwrite: bool) -> None:
    if not segment_manifest.is_file():
        raise FileNotFoundError(segment_manifest)
    if not language_root.is_dir():
        raise FileNotFoundError(language_root)
    existing = sorted(language_root.glob(f"{language_root.name}_P*.jsonl"))
    if existing and not overwrite:
        raise FileExistsError(
            "Podcast manifests already exist; pass --overwrite or move them first. "
            f"Example: {existing[0]}"
        )
    if overwrite:
        for path in existing:
            path.unlink()
        for path in language_root.glob(f"{language_root.name}_P*.jsonl.tmp"):
            path.unlink()


def write_podcast_manifests(args: argparse.Namespace) -> dict:
    language_root = args.output_root / args.language
    preflight(language_root, args.segment_manifest, args.overwrite)

    expected_total = None
    if args.summary and args.summary.is_file():
        with args.summary.open("r", encoding="utf-8") as f:
            summary = json.load(f)
        expected_total = int(summary.get("total_stats", {}).get("accepted", 0)) or None

    cache = WriterCache(max_open=args.max_open_files)
    counts = Counter()
    temp_paths = set()
    total = 0
    try:
        with open_text(args.segment_manifest) as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                podcast = str(record["podcast"])
                if not podcast.startswith(f"{args.language}_P"):
                    raise ValueError(f"Unexpected podcast id for {args.language}: {podcast}")
                tmp_path = language_root / f"{podcast}.jsonl.tmp"
                writer = cache.get(tmp_path)
                writer.write(
                    json.dumps(normalize_record(record, args.language), ensure_ascii=False)
                    + "\n"
                )
                temp_paths.add(tmp_path)
                counts[podcast] += 1
                total += 1

                should_report = (
                    args.progress_interval_lines > 0
                    and total % args.progress_interval_lines == 0
                )
                if should_report:
                    percent = (total / expected_total) * 100.0 if expected_total else None
                    logging.info(
                        "Podcast manifests: lines=%d podcasts=%d %s",
                        total,
                        len(counts),
                        progress_bar(percent),
                    )
                    write_progress(
                        args,
                        {
                            "phase": "writing_podcast_manifests",
                            "lines_seen": total,
                            "expected_lines": expected_total,
                            "podcasts": len(counts),
                            "percent": percent,
                        },
                    )
    finally:
        cache.close()

    for tmp_path in sorted(temp_paths):
        tmp_path.replace(tmp_path.with_suffix(""))

    if expected_total is not None and total != expected_total:
        raise ValueError(f"Podcast manifest lines={total}, expected={expected_total}")

    summary = {
        "status": "prepared",
        "language": args.language,
        "segment_manifest": str(args.segment_manifest),
        "manifest_root": str(language_root),
        "manifest_pattern": f"{args.language}/{args.language}_P000000.jsonl",
        "summary_output": str(args.summary_output) if args.summary_output else None,
        "wav_policy": "wav is relative to the language root, Emilia-style",
        "num_podcast_manifests": len(counts),
        "total_records": total,
        "min_records_per_podcast": min(counts.values()) if counts else 0,
        "max_records_per_podcast": max(counts.values()) if counts else 0,
    }
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.summary is not None:
        with args.summary.open("r", encoding="utf-8") as f:
            merged_summary = json.load(f)
        merged_summary["podcast_manifests"] = summary
        args.summary.write_text(
            json.dumps(merged_summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    write_progress(
        args,
        {
            "phase": "done",
            "lines_seen": total,
            "expected_lines": expected_total,
            "podcasts": len(counts),
            "percent": 100.0,
        },
    )
    return summary


def main() -> None:
    args = get_args()
    summary = write_podcast_manifests(args)
    logging.info(
        "Wrote %d podcast manifests with %d records under %s",
        summary["num_podcast_manifests"],
        summary["total_records"],
        summary["manifest_root"],
    )


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
        level=logging.INFO,
    )
    main()
