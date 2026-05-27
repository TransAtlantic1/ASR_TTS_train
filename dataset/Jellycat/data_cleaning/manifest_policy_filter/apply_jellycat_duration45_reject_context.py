#!/usr/bin/env python3

import argparse
import gzip
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple


DEFAULT_JELLYCAT_ROOT = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat"
)


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            "Apply the Jellycat duration>=45s direct reject policy to the total "
            "segment JSONL.GZ and podcast-level JSONLs, then add reject-aware "
            "prefix/suffix context fields. This script does not touch raw_data "
            "or stage0-6 artifacts."
        ),
    )
    parser.add_argument("--language", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--podcast-root", type=Path, required=True)
    parser.add_argument("--jellycat-root", type=Path, default=DEFAULT_JELLYCAT_ROOT)
    parser.add_argument("--reject-root", type=Path, required=True)
    parser.add_argument("--policy-name", default="duration_ge45_direct_reject_v1")
    parser.add_argument("--reject-threshold-sec", type=float, default=45.0)
    parser.add_argument("--far-threshold-sec", type=float, default=30.0)
    parser.add_argument("--apply", action="store_true", help="Actually replace JSONLs.")
    parser.add_argument("--delete-audio", action="store_true", help="Delete rejected FLAC files; requires --apply.")
    parser.add_argument("--overwrite-backup", action="store_true")
    parser.add_argument("--max-podcast-files", type=int, default=-1)
    parser.add_argument("--progress-interval", type=int, default=100)
    return parser.parse_args()


def open_text(path: Path, mode: str):
    if path.suffix == ".gz":
        return gzip.open(path, mode, encoding="utf-8")
    return path.open(mode, encoding="utf-8")


def temp_manifest_path(path: Path, policy_name: str) -> Path:
    if path.name.endswith(".gz"):
        return path.with_name(path.name[:-3] + f".{policy_name}.tmp.gz")
    return path.with_name(path.name + f".{policy_name}.tmp")


def iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def dump_jsonl(path: Path, records: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def source_episode_key(record: dict) -> str:
    source_wav = record.get("source_wav")
    if source_wav:
        return f"source_wav:{source_wav}"
    source_episode_hash = record.get("source_episode_hash")
    if source_episode_hash:
        return f"source_episode_hash:{source_episode_hash}"
    return f"podcast:{record.get('podcast', 'unknown')}"


def time_bounds(record: dict) -> Tuple[float, float]:
    if record.get("source_start_time") is not None and record.get("source_end_time") is not None:
        return float(record["source_start_time"]), float(record["source_end_time"])
    start = 0.0
    return start, start + float(record["duration"])


def is_reject(record: dict, threshold_sec: float) -> bool:
    return float(record["duration"]) >= threshold_sec


def context_object(record: dict) -> dict:
    start, end = time_bounds(record)
    return {
        "id": record.get("id"),
        "wav": record.get("wav"),
        "start_time": start,
        "end_time": end,
        "duration": float(record.get("duration", end - start)),
        "speaker": record.get("speaker"),
        "text": record.get("text", ""),
    }


def maybe_context(
    *,
    current: dict,
    neighbor: Optional[dict],
    reject_ids: set[str],
    far_threshold_sec: float,
    direction: str,
) -> Tuple[Optional[dict], Optional[bool]]:
    if neighbor is None:
        return None, None
    if str(neighbor["id"]) in reject_ids:
        return None, None
    current_start, current_end = time_bounds(current)
    neighbor_start, neighbor_end = time_bounds(neighbor)
    if direction == "prefix":
        far = (current_start - neighbor_end) > far_threshold_sec
    else:
        far = (neighbor_start - current_end) > far_threshold_sec
    return context_object(neighbor), far


def enrich_podcast_records(
    records: List[dict],
    threshold_sec: float,
    far_threshold_sec: float,
) -> Tuple[List[dict], List[dict], Counter]:
    reject_ids = {str(record["id"]) for record in records if is_reject(record, threshold_sec)}
    groups = defaultdict(list)
    for record in records:
        groups[source_episode_key(record)].append(record)

    enriched_by_id: Dict[str, dict] = {}
    context_stats = Counter()
    for group_records in groups.values():
        sorted_records = sorted(
            group_records,
            key=lambda record: (
                time_bounds(record)[0],
                time_bounds(record)[1],
                str(record.get("id", "")),
            ),
        )
        for index, record in enumerate(sorted_records):
            record_id = str(record["id"])
            if record_id in reject_ids:
                continue
            prefix = sorted_records[index - 1] if index > 0 else None
            suffix = sorted_records[index + 1] if index + 1 < len(sorted_records) else None
            output = dict(record)
            output["prefix_context"], output["prefix_far"] = maybe_context(
                current=record,
                neighbor=prefix,
                reject_ids=reject_ids,
                far_threshold_sec=far_threshold_sec,
                direction="prefix",
            )
            output["suffix_context"], output["suffix_far"] = maybe_context(
                current=record,
                neighbor=suffix,
                reject_ids=reject_ids,
                far_threshold_sec=far_threshold_sec,
                direction="suffix",
            )
            if prefix is not None and str(prefix["id"]) in reject_ids:
                context_stats["prefix_null_due_to_reject"] += 1
            if suffix is not None and str(suffix["id"]) in reject_ids:
                context_stats["suffix_null_due_to_reject"] += 1
            if output["prefix_context"] is not None:
                context_stats["prefix_present"] += 1
                if output["prefix_far"]:
                    context_stats["prefix_far_true"] += 1
            if output["suffix_context"] is not None:
                context_stats["suffix_present"] += 1
                if output["suffix_far"]:
                    context_stats["suffix_far_true"] += 1
            enriched_by_id[record_id] = output

    kept = []
    rejected = []
    for record in records:
        record_id = str(record["id"])
        if record_id in reject_ids:
            rejected.append(record)
        else:
            kept.append(enriched_by_id[record_id])
    return kept, rejected, context_stats


def add_language_prefix(record: dict, language: str) -> dict:
    output = dict(record)
    prefix = f"{language}/"
    wav = str(output.get("wav", ""))
    if wav and not wav.startswith(prefix):
        output["wav"] = prefix + wav
    for key in ("prefix_context", "suffix_context"):
        context = output.get(key)
        if isinstance(context, dict):
            context = dict(context)
            context_wav = str(context.get("wav", ""))
            if context_wav and not context_wav.startswith(prefix):
                context["wav"] = prefix + context_wav
            output[key] = context
    return output


def hardlink_backup(source: Path, backup: Path, overwrite: bool) -> None:
    backup.parent.mkdir(parents=True, exist_ok=True)
    if backup.exists():
        if overwrite:
            backup.unlink()
        else:
            return
    os.link(source, backup)


def reject_record(
    *,
    record: dict,
    language: str,
    policy_name: str,
    threshold_sec: float,
    audio_path: Path,
    delete_status: Optional[str],
    delete_error: Optional[str],
) -> dict:
    output = dict(record)
    output.update(
        {
            "language": language,
            "policy": policy_name,
            "reject_scope": "parent",
            "reason": f"duration_ge_{threshold_sec:g}s",
            "reject_threshold_sec": threshold_sec,
            "duration_sec": float(record["duration"]),
            "audio_path": str(audio_path),
            "audio_delete_status": delete_status,
            "audio_delete_error": delete_error,
        }
    )
    return output


def main() -> None:
    args = get_args()
    language = args.language.upper()
    if args.delete_audio and not args.apply:
        raise ValueError("--delete-audio requires --apply")
    if not args.manifest.is_file():
        raise FileNotFoundError(args.manifest)
    if not args.podcast_root.is_dir():
        raise FileNotFoundError(args.podcast_root)

    paths = sorted(args.podcast_root.glob(f"{language}_P*.jsonl"))
    if args.max_podcast_files > 0:
        paths = paths[: args.max_podcast_files]
    if not paths:
        raise FileNotFoundError(f"No {language}_P*.jsonl files under {args.podcast_root}")

    args.reject_root.mkdir(parents=True, exist_ok=True)
    backup_root = args.reject_root / "backup_before_apply"
    podcast_backup_root = backup_root / "podcast_jsonl"
    manifest_backup = backup_root / args.manifest.name
    reject_output = args.reject_root / f"jellycat_{language}_{args.policy_name}.reject_long_audio.jsonl"
    summary_output = args.reject_root / f"jellycat_{language}_{args.policy_name}.summary.json"
    manifest_tmp = temp_manifest_path(args.manifest, args.policy_name)

    stats = Counter()
    context_stats = Counter()
    rejected_items = []
    changed_podcast_paths = []

    if args.apply:
        hardlink_backup(args.manifest, manifest_backup, args.overwrite_backup)

    segment_writer = None
    try:
        if args.apply:
            segment_writer = open_text(manifest_tmp, "wt")

        for index, path in enumerate(paths, start=1):
            records = list(iter_jsonl(path))
            kept, rejected, local_context_stats = enrich_podcast_records(
                records,
                threshold_sec=args.reject_threshold_sec,
                far_threshold_sec=args.far_threshold_sec,
            )
            stats["podcast_files_seen"] += 1
            stats["records_seen"] += len(records)
            stats["records_kept"] += len(kept)
            stats["records_rejected"] += len(rejected)
            for record in records:
                stats["duration_seen_ms"] += int(round(float(record["duration"]) * 1000))
            for record in kept:
                stats["duration_kept_ms"] += int(round(float(record["duration"]) * 1000))
            for record in rejected:
                stats["duration_rejected_ms"] += int(round(float(record["duration"]) * 1000))
                audio_path = args.jellycat_root / f"{language}/{record['wav']}"
                rejected_items.append((record, audio_path))
            context_stats.update(local_context_stats)

            if args.apply:
                hardlink_backup(path, podcast_backup_root / path.name, args.overwrite_backup)
                tmp_path = path.with_name(path.name + f".{args.policy_name}.tmp")
                dump_jsonl(tmp_path, kept)
                os.replace(tmp_path, path)
                changed_podcast_paths.append(str(path))
                for record in kept:
                    segment_writer.write(
                        json.dumps(add_language_prefix(record, language), ensure_ascii=False)
                        + "\n"
                    )

            if args.progress_interval > 0 and (index % args.progress_interval == 0 or index == len(paths)):
                print(
                    f"{language}: podcasts={index:,}/{len(paths):,} "
                    f"records={stats['records_seen']:,} "
                    f"rejected={stats['records_rejected']:,}",
                    flush=True,
                )
    finally:
        if segment_writer is not None:
            segment_writer.close()

    delete_results = {}
    if args.apply:
        os.replace(manifest_tmp, args.manifest)
        if args.delete_audio:
            for _, audio_path in rejected_items:
                key = str(audio_path)
                if key in delete_results:
                    continue
                if audio_path.exists():
                    try:
                        audio_path.unlink()
                        delete_results[key] = ("deleted", None)
                        stats["audio_deleted"] += 1
                    except Exception as exc:
                        delete_results[key] = ("delete_error", repr(exc))
                        stats["audio_delete_error"] += 1
                else:
                    delete_results[key] = ("missing_before_delete", None)
                    stats["audio_missing_before_delete"] += 1
        else:
            for _, audio_path in rejected_items:
                delete_results[str(audio_path)] = ("not_requested", None)

        with reject_output.open("w", encoding="utf-8") as f:
            for record, audio_path in rejected_items:
                status, error = delete_results[str(audio_path)]
                f.write(
                    json.dumps(
                        reject_record(
                            record=record,
                            language=language,
                            policy_name=args.policy_name,
                            threshold_sec=args.reject_threshold_sec,
                            audio_path=audio_path,
                            delete_status=status,
                            delete_error=error,
                        ),
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    else:
        reject_output = None

    summary = {
        "language": language,
        "policy_name": args.policy_name,
        "reject_threshold_sec": args.reject_threshold_sec,
        "far_threshold_sec": args.far_threshold_sec,
        "applied": bool(args.apply),
        "delete_audio": bool(args.delete_audio),
        "manifest": str(args.manifest),
        "podcast_root": str(args.podcast_root),
        "jellycat_root": str(args.jellycat_root),
        "reject_output": str(reject_output) if reject_output is not None else None,
        "summary_output": str(summary_output),
        "backup_root": str(backup_root) if args.apply else None,
        "stats": {key: int(value) for key, value in sorted(stats.items())},
        "duration_hours": {
            "seen": stats["duration_seen_ms"] / 1000.0 / 3600.0,
            "kept": stats["duration_kept_ms"] / 1000.0 / 3600.0,
            "rejected": stats["duration_rejected_ms"] / 1000.0 / 3600.0,
        },
        "context_stats": {key: int(value) for key, value in sorted(context_stats.items())},
        "changed_podcast_paths_count": len(changed_podcast_paths),
    }
    summary_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
