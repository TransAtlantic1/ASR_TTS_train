#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def avg(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return mean(values)


def summarize_file(path: Path) -> Dict[str, Any]:
    timing_path = path.with_suffix(".time.json")
    timing = {}
    if timing_path.exists():
        timing = json.loads(timing_path.read_text(encoding="utf-8"))

    rows = list(iter_jsonl(path))
    failed = [row for row in rows if row.get("error")]
    ok = [row for row in rows if not row.get("error")]
    duration_sec = sum(float(row.get("duration") or 0.0) for row in rows)
    wers = [float(row["wer"]) for row in ok if row.get("wer") is not None]
    cers = [float(row["cer"]) for row in ok if row.get("cer") is not None]
    zh_wers = [
        float(row["zh_pinyin_tone3_wer"])
        for row in ok
        if row.get("zh_pinyin_tone3_wer") is not None
    ]
    wall_sec = float(timing.get("wall_sec") or 0.0)
    return {
        "file": str(path),
        "language": timing.get("language") or infer_language(path),
        "limit": timing.get("limit"),
        "workers_per_port": timing.get("workers_per_port"),
        "ports": timing.get("ports"),
        "rows": len(rows),
        "failed": len(failed),
        "success": len(ok),
        "duration_sec": duration_sec,
        "wall_sec": wall_sec,
        "utt_per_sec": len(rows) / wall_sec if wall_sec > 0 else None,
        "audio_hours_per_wall_hour": duration_sec / wall_sec if wall_sec > 0 else None,
        "mean_wer": avg(wers),
        "mean_cer": avg(cers),
        "mean_zh_pinyin_tone3_wer": avg(zh_wers),
        "first_errors": [row.get("error") for row in failed[:5]],
    }


def infer_language(path: Path) -> str:
    stem = path.stem.lower()
    if stem.endswith("_zh"):
        return "ZH"
    if stem.endswith("_en"):
        return "EN"
    return "UNKNOWN"


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def write_markdown(rows: List[Dict[str, Any]], path: Path) -> None:
    lines = [
        "# H200 ASR Benchmark Summary",
        "",
        "| file | lang | limit | wpp | rows | failed | wall_sec | utt_per_sec | audio_hours_per_wall_hour | mean_wer | mean_cer |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        file_name = Path(row["file"]).name
        lines.append(
            "| "
            + " | ".join(
                [
                    file_name,
                    fmt(row["language"]),
                    fmt(row["limit"]),
                    fmt(row["workers_per_port"]),
                    fmt(row["rows"]),
                    fmt(row["failed"]),
                    fmt(row["wall_sec"]),
                    fmt(row["utt_per_sec"]),
                    fmt(row["audio_hours_per_wall_hour"]),
                    fmt(row["mean_wer"]),
                    fmt(row["mean_cer"]),
                ]
            )
            + " |"
        )
    lines.append("")
    errors = [row for row in rows if row["failed"]]
    if errors:
        lines.append("## First Errors")
        lines.append("")
        for row in errors:
            lines.append(f"- `{Path(row['file']).name}`: {row['first_errors']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize H200 ASR benchmark outputs.")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    bench_dir = run_dir / "benchmarks"
    if not bench_dir.exists():
        raise SystemExit(f"missing benchmark dir: {bench_dir}")

    files = sorted(
        path
        for path in bench_dir.glob("*.jsonl")
        if not path.name.endswith(".failed.jsonl")
    )
    if not files:
        raise SystemExit(f"no benchmark jsonl found under {bench_dir}")

    rows = [summarize_file(path) for path in files]
    summary_json = run_dir / "summary.json"
    summary_md = run_dir / "summary.md"
    summary_json.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(rows, summary_md)
    print(f"wrote {summary_md}")
    print(f"wrote {summary_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
