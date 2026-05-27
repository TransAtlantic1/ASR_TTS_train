#!/usr/bin/env python3

import argparse
import gzip
import glob
import json
import logging
import multiprocessing as mp
import os
import shutil
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from typing import Dict, List

from lhotse import AudioSource, Recording, RecordingSet, SupervisionSegment, SupervisionSet


SUPPORTED_LANGUAGES = {"zh", "en"}


def validate_language(language: str) -> str:
    normalized = language.lower()
    if normalized not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    return normalized


def speaker_to_bucket(speaker: str) -> float:
    import hashlib

    digest = hashlib.sha1(speaker.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def speaker_to_split(speaker: str, dev_ratio: float, test_ratio: float) -> str:
    if dev_ratio < 0 or test_ratio < 0 or dev_ratio + test_ratio >= 1.0:
        raise ValueError(
            f"Invalid split ratios: dev_ratio={dev_ratio}, test_ratio={test_ratio}"
        )
    bucket = speaker_to_bucket(speaker)
    if bucket < test_ratio:
        return "test"
    if bucket < test_ratio + dev_ratio:
        return "dev"
    return "train"


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--manifest-source",
        choices=["emilia_jsonl", "prebuilt_lhotse"],
        required=True,
        help="Source format used to create recipe-local Lhotse manifests.",
    )
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--language", choices=sorted(SUPPORTED_LANGUAGES), required=True)
    parser.add_argument("--dataset-name", default="dataset")
    parser.add_argument("--manifest-prefix", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-recordings-manifest", type=Path, default=None)
    parser.add_argument("--source-supervisions-manifest", type=Path, default=None)
    parser.add_argument("--source-sample-rate", type=int, default=32000)
    parser.add_argument("--manifest-link-mode", choices=["copy", "hardlink", "symlink"], default="symlink")
    parser.add_argument(
        "--recording-num-splits",
        type=int,
        default=0,
        help=(
            "Expected number of prebuilt recording/supervision shards. "
            "Only used when source manifest paths are glob patterns."
        ),
    )
    parser.add_argument("--dev-ratio", type=float, default=0.001)
    parser.add_argument("--test-ratio", type=float, default=0.001)
    parser.add_argument("--max-jsonl-files", type=int, default=-1)
    parser.add_argument("--max-utterances", type=int, default=-1)
    parser.add_argument("--num-workers", type=int, default=8)
    return parser.parse_args()


def unlink_if_exists(path: Path) -> None:
    if path.exists() or path.is_symlink():
        path.unlink()


def empty_gzip(path: Path) -> None:
    unlink_if_exists(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8"):
        pass


def install_manifest(source: Path, target: Path, mode: str) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Missing source manifest: {source}")
    unlink_if_exists(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode == "symlink":
        os.symlink(source, target)
    elif mode == "hardlink":
        try:
            os.link(source, target)
        except OSError:
            shutil.copyfile(source, target)
    else:
        shutil.copyfile(source, target)


def resolve_source_manifests(path: Path) -> List[Path]:
    raw = str(path)
    if any(char in raw for char in "*?[]"):
        matches = [Path(p).resolve(strict=False) for p in sorted(glob.glob(raw))]
        if not matches:
            raise FileNotFoundError(f"No source manifests matched: {raw}")
        return matches
    if not path.is_file():
        raise FileNotFoundError(f"Missing source manifest: {path}")
    return [path.resolve(strict=False)]


def install_sharded_manifests(
    sources: List[Path],
    split_dir: Path,
    prefix: str,
    kind: str,
    mode: str,
) -> None:
    split_dir.mkdir(parents=True, exist_ok=True)
    for old_path in split_dir.glob(f"{prefix}_{kind}_train.*.jsonl.gz"):
        unlink_if_exists(old_path)
    for index, source in enumerate(sources):
        target = split_dir / f"{prefix}_{kind}_train.{index:04d}.jsonl.gz"
        install_manifest(source, target, mode)
    (split_dir / ".split_completed").touch()


def prepare_prebuilt_lhotse(args: argparse.Namespace) -> None:
    if args.dev_ratio != 0.0 or args.test_ratio != 0.0:
        raise ValueError(
            "prebuilt_lhotse currently expects --dev-ratio 0.0 and --test-ratio 0.0; "
            "keep recipe-local dev/test disabled and use the external eval flow."
        )
    if args.source_recordings_manifest is None or args.source_supervisions_manifest is None:
        raise ValueError(
            "prebuilt_lhotse requires --source-recordings-manifest and "
            "--source-supervisions-manifest"
        )

    prefix = args.manifest_prefix
    recording_sources = resolve_source_manifests(args.source_recordings_manifest)
    supervision_sources = resolve_source_manifests(args.source_supervisions_manifest)
    if len(recording_sources) != len(supervision_sources):
        raise ValueError(
            "Mismatched prebuilt shard counts: "
            f"recordings={len(recording_sources)} supervisions={len(supervision_sources)}"
        )
    if len(recording_sources) > 1 and args.recording_num_splits not in (
        0,
        len(recording_sources),
    ):
        raise ValueError(
            f"--recording-num-splits={args.recording_num_splits} does not match "
            f"{len(recording_sources)} prebuilt shards"
        )

    targets = {
        "train_recordings": args.output_dir / f"{prefix}_recordings_train.jsonl.gz",
        "train_supervisions": args.output_dir / f"{prefix}_supervisions_train.jsonl.gz",
        "dev_recordings": args.output_dir / f"{prefix}_recordings_dev.jsonl.gz",
        "dev_supervisions": args.output_dir / f"{prefix}_supervisions_dev.jsonl.gz",
        "test_recordings": args.output_dir / f"{prefix}_recordings_test.jsonl.gz",
        "test_supervisions": args.output_dir / f"{prefix}_supervisions_test.jsonl.gz",
    }

    if len(recording_sources) == 1:
        install_manifest(
            recording_sources[0],
            targets["train_recordings"],
            args.manifest_link_mode,
        )
        install_manifest(
            supervision_sources[0],
            targets["train_supervisions"],
            args.manifest_link_mode,
        )
    else:
        split_count = args.recording_num_splits or len(recording_sources)
        install_sharded_manifests(
            recording_sources,
            args.output_dir / f"recordings_train_split_{split_count}",
            prefix,
            "recordings",
            args.manifest_link_mode,
        )
        install_sharded_manifests(
            supervision_sources,
            args.output_dir / f"supervisions_train_split_{split_count}",
            prefix,
            "supervisions",
            args.manifest_link_mode,
        )
        for key in ("train_recordings", "train_supervisions"):
            empty_gzip(targets[key])

    for key in ("dev_recordings", "dev_supervisions", "test_recordings", "test_supervisions"):
        empty_gzip(targets[key])

    summary = {
        "dataset_name": args.dataset_name,
        "language": args.language,
        "manifest_source": args.manifest_source,
        "manifest_prefix": prefix,
        "source_recordings_manifest": str(args.source_recordings_manifest),
        "source_supervisions_manifest": str(args.source_supervisions_manifest),
        "source_recording_shards": [str(p) for p in recording_sources],
        "source_supervision_shards": [str(p) for p in supervision_sources],
        "manifest_link_mode": args.manifest_link_mode,
        "split_counts": {"train": "prebuilt", "dev": 0, "test": 0},
    }
    summary_path = args.output_dir / f"{prefix}_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logging.info("Installed prebuilt %s manifests under %s", args.dataset_name, args.output_dir)


def process_jsonl_file(args_tuple):
    (
        jsonl_path,
        language_dir,
        language,
        manifest_prefix,
        source_sample_rate,
        dev_ratio,
        test_ratio,
        max_utterances,
    ) = args_tuple

    recordings: Dict[str, List[Recording]] = {"train": [], "dev": [], "test": []}
    supervisions: Dict[str, List[SupervisionSegment]] = {"train": [], "dev": [], "test": []}
    stats = Counter()
    split_counts = Counter()

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if max_utterances > 0 and stats["written"] >= max_utterances:
                break

            stats["seen"] += 1
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                stats["json_error"] += 1
                continue

            entry_language = str(entry.get("language", language)).lower()
            if entry_language != language:
                stats["language_mismatch"] += 1
                continue

            utterance_id = str(entry["id"])
            speaker = str(entry.get("speaker") or utterance_id)
            duration = float(entry.get("duration", 0.0) or 0.0)
            if duration <= 0:
                stats["invalid_duration"] += 1
                continue

            audio_rel_path = entry.get("wav", "")
            if not audio_rel_path:
                stats["missing_wav_field"] += 1
                continue

            audio_path = str(language_dir / audio_rel_path)
            recording = Recording(
                id=utterance_id,
                sources=[AudioSource(type="file", channels=[0], source=audio_path)],
                sampling_rate=source_sample_rate,
                num_samples=int(duration * source_sample_rate),
                duration=duration,
            )

            raw_text = str(entry.get("text", ""))
            split = speaker_to_split(
                speaker=speaker,
                dev_ratio=dev_ratio,
                test_ratio=test_ratio,
            )
            supervision = SupervisionSegment(
                id=utterance_id,
                recording_id=recording.id,
                start=0.0,
                duration=duration,
                channel=0,
                text=raw_text,
                language=language,
                speaker=speaker,
                custom={
                    "raw_text": raw_text,
                    "dnsmos": entry.get("dnsmos"),
                    "source_jsonl": Path(jsonl_path).name,
                    "manifest_prefix": manifest_prefix,
                },
            )

            recordings[split].append(recording)
            supervisions[split].append(supervision)
            split_counts[split] += 1
            stats["written"] += 1

    logging.info("Done %s: written=%d", Path(jsonl_path).name, stats["written"])
    return recordings, supervisions, stats, split_counts


def prepare_emilia_jsonl(args: argparse.Namespace) -> None:
    language = validate_language(args.language)
    prefix = args.manifest_prefix
    language_dir = args.dataset_root / language.upper()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    jsonl_files = sorted(language_dir.glob("*.jsonl"))
    if args.max_jsonl_files > 0:
        jsonl_files = jsonl_files[: args.max_jsonl_files]
    if not jsonl_files:
        raise FileNotFoundError(f"No JSONL files found in {language_dir}")

    split_paths = {
        split: {
            "recordings": args.output_dir / f"{prefix}_recordings_{split}.jsonl.gz",
            "supervisions": args.output_dir / f"{prefix}_supervisions_{split}.jsonl.gz",
        }
        for split in ("train", "dev", "test")
    }
    for paths in split_paths.values():
        unlink_if_exists(paths["recordings"])
        unlink_if_exists(paths["supervisions"])

    worker_args = [
        (
            str(jsonl_path),
            language_dir,
            language,
            prefix,
            args.source_sample_rate,
            args.dev_ratio,
            args.test_ratio,
            args.max_utterances,
        )
        for jsonl_path in jsonl_files
    ]
    num_workers = max(1, min(args.num_workers, len(jsonl_files)))
    total_stats = Counter()
    total_split_counts = Counter()

    with ExitStack() as stack:
        recording_writers = {
            split: stack.enter_context(RecordingSet.open_writer(paths["recordings"]))
            for split, paths in split_paths.items()
        }
        supervision_writers = {
            split: stack.enter_context(SupervisionSet.open_writer(paths["supervisions"]))
            for split, paths in split_paths.items()
        }

        with mp.Pool(processes=num_workers) as pool:
            for i, (recordings, supervisions, stats, split_counts) in enumerate(
                pool.imap_unordered(process_jsonl_file, worker_args)
            ):
                total_stats += stats
                total_split_counts += split_counts
                for split in ("train", "dev", "test"):
                    for rec in recordings[split]:
                        recording_writers[split].write(rec)
                    for sup in supervisions[split]:
                        supervision_writers[split].write(sup)
                if (i + 1) % 10 == 0 or (i + 1) == len(jsonl_files):
                    logging.info(
                        "Progress: %d/%d files done, total written=%d",
                        i + 1,
                        len(jsonl_files),
                        total_stats["written"],
                    )
                if args.max_utterances > 0 and total_stats["written"] >= args.max_utterances:
                    pool.terminate()
                    break

    summary = {
        "dataset_name": args.dataset_name,
        "language": language,
        "dataset_root": str(args.dataset_root),
        "manifest_source": args.manifest_source,
        "manifest_prefix": prefix,
        "source_sample_rate": args.source_sample_rate,
        "processed_jsonl_files": [p.name for p in jsonl_files],
        "stats": dict(total_stats),
        "split_counts": dict(total_split_counts),
    }
    summary_path = args.output_dir / f"{prefix}_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logging.info("Finished preparing %s %s manifests", args.dataset_name, language)


def main() -> None:
    args = get_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.manifest_source == "prebuilt_lhotse":
        prepare_prebuilt_lhotse(args)
    else:
        prepare_emilia_jsonl(args)


if __name__ == "__main__":
    formatter = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s"
    logging.basicConfig(format=formatter, level=logging.INFO)
    main()
