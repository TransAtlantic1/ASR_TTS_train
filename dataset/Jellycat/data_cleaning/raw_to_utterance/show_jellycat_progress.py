#!/usr/bin/env python3

import argparse
import glob
import json
import time
from collections import Counter
from pathlib import Path


def get_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--progress-path",
        type=Path,
        default=Path("dataset/Jellycat/logs/full_prepare.progress.json"),
    )
    parser.add_argument(
        "--progress-glob",
        default=None,
        help="Optional glob for sharded progress JSON files.",
    )
    parser.add_argument("--watch", action="store_true", help="Refresh once per second.")
    return parser.parse_args()


def progress_bar(percent, width: int = 40) -> str:
    if percent is None:
        return "[" + ("?" * width) + "]"
    percent = max(0.0, min(100.0, percent))
    filled = int(round((percent / 100.0) * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + f"] {percent:6.2f}%"


def render(progress_path: Path) -> str:
    if not progress_path.is_file():
        return f"Progress file not found: {progress_path}"
    data = json.loads(progress_path.read_text(encoding="utf-8"))
    lines = [
        f"{data.get('bar', '[pending]')} phase={data.get('phase')} language={data.get('language')}",
    ]
    for key in (
        "total_lines_seen",
        "total_expected_lines",
        "language_lines_seen",
        "language_expected_lines",
        "accepted",
        "accepted_so_far",
        "audio_written",
        "audio_reused",
        "rejected",
        "podcasts_so_far",
        "speakers_so_far",
    ):
        if key in data and data[key] is not None:
            lines.append(f"{key}: {data[key]}")
    return "\n".join(lines)


def render_sharded(progress_glob: str) -> str:
    paths = [Path(path) for path in sorted(glob.glob(progress_glob))]
    if not paths:
        return f"Progress files not found: {progress_glob}"

    items = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items.append((path, data))
    if not items:
        return f"No readable progress files: {progress_glob}"

    percents = [
        float(data["percent"])
        for _, data in items
        if data.get("percent") is not None
    ]
    average = sum(percents) / len(percents) if percents else None
    phases = Counter(data.get("phase", "unknown") for _, data in items)
    lines = [
        f"{progress_bar(average)} shards={len(items)} phases={dict(sorted(phases.items()))}",
    ]
    for path, data in items:
        lines.append(
            "{name}: {bar} phase={phase} language={language} accepted={accepted} "
            "written={written} reused={reused} rejected={rejected}".format(
                name=path.name.replace("full_prepare.", "").replace(".progress.json", ""),
                bar=data.get("bar", progress_bar(data.get("percent"))),
                phase=data.get("phase"),
                language=data.get("language"),
                accepted=data.get("accepted", data.get("accepted_so_far")),
                written=data.get("audio_written"),
                reused=data.get("audio_reused"),
                rejected=data.get("rejected"),
            )
        )
    return "\n".join(lines)


def main() -> None:
    args = get_args()
    while True:
        if args.progress_glob:
            print(render_sharded(args.progress_glob), flush=True)
        else:
            print(render(args.progress_path), flush=True)
        if not args.watch:
            break
        time.sleep(1)
        print("\033[H\033[J", end="")


if __name__ == "__main__":
    main()
