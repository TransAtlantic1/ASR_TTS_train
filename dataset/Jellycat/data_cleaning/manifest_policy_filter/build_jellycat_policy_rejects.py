#!/usr/bin/env python3

import argparse
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator, Optional


BRACKET_PATTERNS = [
    ("square", re.compile(r"\[[^\[\]\n\r]{1,120}?\]")),
    ("full_square", re.compile(r"【[^【】\n\r]{1,120}?】")),
    ("paren", re.compile(r"\([^()\n\r]{1,120}?\)")),
    ("full_paren", re.compile(r"（[^（）\n\r]{1,120}?）")),
    ("angle", re.compile(r"<[^<>\n\r]{1,120}?>")),
    ("brace", re.compile(r"\{[^{}\n\r]{1,120}?\}")),
]


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            "Build a standalone Jellycat policy reject JSONL. The script scans "
            "input manifests and does not modify them."
        ),
    )
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--policy-name", default="duration_0p5_45_contains_bracket_v1")
    parser.add_argument("--min-duration-sec", type=float, default=0.5)
    parser.add_argument("--max-duration-sec", type=float, default=45.0)
    parser.add_argument("--id-field", default="id")
    parser.add_argument("--text-field", default="text")
    parser.add_argument("--duration-field", default="duration")
    parser.add_argument("--language-field", default="language")
    parser.add_argument("--progress-interval", type=int, default=1000000)
    return parser.parse_args()


def open_text(path: Path, mode: str):
    if path.name.endswith(".gz"):
        return gzip.open(path, mode, encoding="utf-8")
    return path.open(mode, encoding="utf-8")


def iter_jsonl(path: Path) -> Iterator[dict]:
    with open_text(path, "rt") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def default_summary_path(output: Path) -> Path:
    name = output.name
    if name.endswith(".jsonl.gz"):
        return output.with_name(name[:-9] + ".summary.json")
    if name.endswith(".jsonl"):
        return output.with_name(name[:-6] + ".summary.json")
    return output.with_name(name + ".summary.json")


def guess_language(path: Path, record: dict, language_field: str) -> str:
    value = record.get(language_field)
    if value:
        return str(value).upper()
    text = path.as_posix()
    if "/ZH/" in text or "_ZH_" in text or "jellycat_ZH" in text:
        return "ZH"
    if "/EN/" in text or "_EN_" in text or "jellycat_EN" in text:
        return "EN"
    return "UNKNOWN"


def bracket_matches(text: str) -> list[dict]:
    matches = []
    for bracket_type, pattern in BRACKET_PATTERNS:
        for match in pattern.finditer(text):
            matches.append(
                {
                    "type": bracket_type,
                    "span": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    matches.sort(key=lambda item: (item["start"], item["end"], item["type"]))
    return matches


def reject_reason(duration: float, text: str, min_duration: float, max_duration: float) -> tuple[Optional[str], list[dict]]:
    matches = bracket_matches(text)
    if duration < min_duration:
        return f"duration_lt_{min_duration:g}s", matches
    if duration > max_duration:
        return f"duration_gt_{max_duration:g}s", matches
    if matches:
        return "contains_bracket_span_v1", matches
    return None, matches


def add_duration(stats: Counter, prefix: str, duration: float) -> None:
    stats[f"{prefix}_records"] += 1
    stats[f"{prefix}_duration_ms"] += int(round(duration * 1000))


def update_nested_language(stats: dict, language: str, reason: str, duration: float) -> None:
    item = stats[language][reason]
    item["records"] += 1
    item["duration_ms"] += int(round(duration * 1000))


def make_reject_record(
    *,
    record: dict,
    record_id: str,
    language: str,
    duration: float,
    reason: str,
    matches: list[dict],
    source_manifest: Path,
    policy_name: str,
) -> dict:
    output = dict(record)
    output.update(
        {
            "id": record_id,
            "language": language,
            "reject_policy": policy_name,
            "reason": reason,
            "duration_sec": duration,
            "source_manifest": str(source_manifest),
        }
    )
    if matches:
        output["matched_spans"] = [item["span"] for item in matches]
        output["matched_bracket_types"] = sorted({item["type"] for item in matches})
        output["matched_bracket_details"] = matches
    return output


def main() -> None:
    args = get_args()
    summary_output = args.summary_output or default_summary_path(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)

    stats = Counter()
    by_language = defaultdict(lambda: defaultdict(lambda: {"records": 0, "duration_ms": 0}))
    by_input = defaultdict(Counter)
    bracket_types = Counter()
    examples = []

    with open_text(args.output, "wt") as out_f:
        for input_path in args.inputs:
            input_count = 0
            for record in iter_jsonl(input_path):
                input_count += 1
                stats["records_seen"] += 1
                if args.progress_interval > 0 and stats["records_seen"] % args.progress_interval == 0:
                    print(
                        f"seen={stats['records_seen']:,} rejected={stats['rejected_records']:,}",
                        flush=True,
                    )
                duration = float(record[args.duration_field])
                text = str(record.get(args.text_field, ""))
                language = guess_language(input_path, record, args.language_field)
                add_duration(stats, "seen", duration)
                by_input[str(input_path)]["records_seen"] += 1
                by_input[str(input_path)]["duration_seen_ms"] += int(round(duration * 1000))

                reason, matches = reject_reason(
                    duration,
                    text,
                    args.min_duration_sec,
                    args.max_duration_sec,
                )
                if reason is None:
                    add_duration(stats, "kept", duration)
                    by_input[str(input_path)]["records_kept"] += 1
                    by_input[str(input_path)]["duration_kept_ms"] += int(round(duration * 1000))
                    continue

                record_id = str(record[args.id_field])
                reject = make_reject_record(
                    record=record,
                    record_id=record_id,
                    language=language,
                    duration=duration,
                    reason=reason,
                    matches=matches,
                    source_manifest=input_path,
                    policy_name=args.policy_name,
                )
                out_f.write(json.dumps(reject, ensure_ascii=False) + "\n")
                add_duration(stats, "rejected", duration)
                add_duration(stats, reason, duration)
                update_nested_language(by_language, language, reason, duration)
                by_input[str(input_path)]["records_rejected"] += 1
                by_input[str(input_path)]["duration_rejected_ms"] += int(round(duration * 1000))
                for match in matches:
                    bracket_types[match["type"]] += 1
                if len(examples) < 20:
                    examples.append(reject)

            print(f"input_done\t{input_path}\t{input_count}", flush=True)

    summary = {
        "policy_name": args.policy_name,
        "inputs": [str(path) for path in args.inputs],
        "reject_output": str(args.output),
        "summary_output": str(summary_output),
        "min_duration_sec": args.min_duration_sec,
        "max_duration_sec": args.max_duration_sec,
        "records_seen": int(stats["records_seen"]),
        "records_kept": int(stats["kept_records"]),
        "records_rejected": int(stats["rejected_records"]),
        "duration_hours": {
            "seen": stats["seen_duration_ms"] / 1000.0 / 3600.0,
            "kept": stats["kept_duration_ms"] / 1000.0 / 3600.0,
            "rejected_total": stats["rejected_duration_ms"] / 1000.0 / 3600.0,
            "duration_lt_min": stats[f"duration_lt_{args.min_duration_sec:g}s_duration_ms"] / 1000.0 / 3600.0,
            "duration_gt_max": stats[f"duration_gt_{args.max_duration_sec:g}s_duration_ms"] / 1000.0 / 3600.0,
            "duration_policy_total": (
                stats[f"duration_lt_{args.min_duration_sec:g}s_duration_ms"]
                + stats[f"duration_gt_{args.max_duration_sec:g}s_duration_ms"]
            )
            / 1000.0
            / 3600.0,
            "contains_bracket_after_duration_policy": stats["contains_bracket_span_v1_duration_ms"] / 1000.0 / 3600.0,
        },
        "records_by_reason": {
            f"duration_lt_{args.min_duration_sec:g}s": int(stats[f"duration_lt_{args.min_duration_sec:g}s_records"]),
            f"duration_gt_{args.max_duration_sec:g}s": int(stats[f"duration_gt_{args.max_duration_sec:g}s_records"]),
            "contains_bracket_span_v1": int(stats["contains_bracket_span_v1_records"]),
        },
        "hours_by_reason": {
            f"duration_lt_{args.min_duration_sec:g}s": stats[f"duration_lt_{args.min_duration_sec:g}s_duration_ms"] / 1000.0 / 3600.0,
            f"duration_gt_{args.max_duration_sec:g}s": stats[f"duration_gt_{args.max_duration_sec:g}s_duration_ms"] / 1000.0 / 3600.0,
            "contains_bracket_span_v1": stats["contains_bracket_span_v1_duration_ms"] / 1000.0 / 3600.0,
        },
        "by_language": {
            language: {
                reason: {
                    "records": values["records"],
                    "hours": values["duration_ms"] / 1000.0 / 3600.0,
                }
                for reason, values in sorted(reason_map.items())
            }
            for language, reason_map in sorted(by_language.items())
        },
        "by_input": {
            path: {
                "records_seen": int(values["records_seen"]),
                "hours_seen": values["duration_seen_ms"] / 1000.0 / 3600.0,
                "records_kept": int(values["records_kept"]),
                "hours_kept": values["duration_kept_ms"] / 1000.0 / 3600.0,
                "records_rejected": int(values["records_rejected"]),
                "hours_rejected": values["duration_rejected_ms"] / 1000.0 / 3600.0,
            }
            for path, values in sorted(by_input.items())
        },
        "matched_bracket_types": dict(sorted(bracket_types.items())),
        "examples": examples,
    }
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
