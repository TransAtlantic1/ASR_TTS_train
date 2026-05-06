#!/usr/bin/env python3

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Dict, Iterator, List, Optional


DEFAULT_OUTPUT_ROOT = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat"
)


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            "Generate language-generic Jellycat VAD policy lists: direct rejects "
            "for long utterances and VAD candidates for 30-60s utterances."
        ),
    )
    parser.add_argument("--language", required=True, help="Target language, e.g. ZH or EN.")
    parser.add_argument(
        "--segment-manifest",
        type=Path,
        required=True,
        help="Segment-level Jellycat manifest to scan.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for policy JSONL outputs.",
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="Output filename prefix. Default: jellycat_<LANG>_vad_policy",
    )
    parser.add_argument("--vad-min-duration", type=float, default=30.0)
    parser.add_argument("--direct-reject-duration", type=float, default=60.0)
    parser.add_argument("--examples-limit", type=int, default=20)
    parser.add_argument("--progress-interval", type=int, default=1000000)
    parser.add_argument(
        "--max-records",
        type=int,
        default=-1,
        help="Optional development cap for smoke tests.",
    )
    return parser.parse_args()


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_records(path: Path) -> Iterator[dict]:
    with open_text(path) as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def make_policy_record(record: dict, reason: str, action: str) -> Dict:
    duration = float(record["duration"])
    text = str(record.get("text", ""))
    return {
        "id": record["id"],
        "reason": reason,
        "action": action,
        "duration_sec": duration,
        "text_len": len(text),
        "chars_per_sec": len(text) / duration if duration > 0 else 0.0,
        "language": record.get("language"),
        "source_language": record.get("source_language"),
        "podcast": record.get("podcast"),
        "speaker": record.get("speaker"),
        "wav": record.get("wav"),
        "text": text,
        "source_manifest_id": record.get("source_manifest_id"),
        "source_wav": record.get("source_wav"),
        "source_start_time": record.get("source_start_time"),
        "source_end_time": record.get("source_end_time"),
    }


def write_jsonl(path: Path, records: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def pct(part: float, total: float) -> float:
    return part / total * 100.0 if total else 0.0


def main() -> None:
    args = get_args()
    if args.vad_min_duration >= args.direct_reject_duration:
        raise ValueError(
            "--vad-min-duration must be smaller than --direct-reject-duration"
        )
    if not args.segment_manifest.is_file():
        raise FileNotFoundError(args.segment_manifest)

    language = args.language.upper()
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_ROOT / "manifests" / language
    prefix = args.prefix or f"jellycat_{language}_vad_policy"

    vad_candidates: List[Dict] = []
    direct_rejects: List[Dict] = []
    stats = Counter()
    duration_sums = Counter()

    for record in iter_records(args.segment_manifest):
        if args.max_records > 0 and stats["records"] >= args.max_records:
            break
        stats["records"] += 1
        duration = float(record["duration"])
        duration_sums["all"] += duration
        if duration > args.direct_reject_duration:
            item = make_policy_record(
                record,
                reason="duration_gt_direct_reject_threshold",
                action="direct_reject",
            )
            direct_rejects.append(item)
            stats["direct_reject"] += 1
            duration_sums["direct_reject"] += duration
        elif duration > args.vad_min_duration:
            item = make_policy_record(
                record,
                reason="duration_gt_vad_min_le_direct_reject_threshold",
                action="vad_split_candidate",
            )
            vad_candidates.append(item)
            stats["vad_candidate"] += 1
            duration_sums["vad_candidate"] += duration
        else:
            stats["keep_unchanged"] += 1

        if args.progress_interval > 0 and stats["records"] % args.progress_interval == 0:
            print(
                f"records={stats['records']:,} "
                f"vad_candidates={stats['vad_candidate']:,} "
                f"direct_rejects={stats['direct_reject']:,}",
                flush=True,
            )

    vad_candidates.sort(key=lambda item: (-item["duration_sec"], item["id"]))
    direct_rejects.sort(key=lambda item: (-item["duration_sec"], item["id"]))

    vad_path = (
        output_dir
        / f"{prefix}.duration_gt_{int(args.vad_min_duration)}s"
        f"_le_{int(args.direct_reject_duration)}s.vad_candidates.jsonl"
    )
    direct_path = (
        output_dir
        / f"{prefix}.duration_gt_{int(args.direct_reject_duration)}s.direct_reject.jsonl"
    )
    summary_path = output_dir / f"{prefix}.summary.json"

    write_jsonl(vad_path, vad_candidates)
    write_jsonl(direct_path, direct_rejects)

    summary = {
        "language": language,
        "segment_manifest": str(args.segment_manifest),
        "vad_min_duration_sec": args.vad_min_duration,
        "direct_reject_duration_sec": args.direct_reject_duration,
        "vad_candidates_jsonl": str(vad_path),
        "direct_reject_jsonl": str(direct_path),
        "summary_json": str(summary_path),
        "records": int(stats["records"]),
        "keep_unchanged_count": int(stats["keep_unchanged"]),
        "vad_candidate_count": len(vad_candidates),
        "direct_reject_count": len(direct_rejects),
        "keep_unchanged_percent": pct(stats["keep_unchanged"], stats["records"]),
        "vad_candidate_percent": pct(len(vad_candidates), stats["records"]),
        "direct_reject_percent": pct(len(direct_rejects), stats["records"]),
        "duration_hours": {
            "all": duration_sums["all"] / 3600.0,
            "vad_candidate": duration_sums["vad_candidate"] / 3600.0,
            "direct_reject": duration_sums["direct_reject"] / 3600.0,
        },
        "examples_vad_candidates_longest": vad_candidates[: args.examples_limit],
        "examples_direct_reject_longest": direct_rejects[: args.examples_limit],
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"records\t{stats['records']}")
    print(f"vad_candidate_count\t{len(vad_candidates)}")
    print(f"direct_reject_count\t{len(direct_rejects)}")
    print(f"vad_candidates_jsonl\t{vad_path}")
    print(f"direct_reject_jsonl\t{direct_path}")
    print(f"summary_json\t{summary_path}")


if __name__ == "__main__":
    main()
