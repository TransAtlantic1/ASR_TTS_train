#!/usr/bin/env python3

import argparse
import json
import logging
import os
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from itertools import islice
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

import lhotse
import torchaudio
from lhotse import AudioSource, CutSet, Recording, RecordingSet, SupervisionSet
from lhotse.serialization import load_manifest_lazy_or_eager

from split_utils import manifest_prefix, validate_language
from text_policy import canonicalize_text


DEFAULT_SAMPLE_RATE_REPORT = (
    Path(__file__).resolve().parents[3]
    / "report"
    / "emilia_24k_original_sample_rate_scan.json"
)
BATCH_ID_PATTERN = re.compile(r"^[A-Z]{2}_B\d{5}$")
DEFAULT_RECORDING_PROBE_WORKERS = min(32, os.cpu_count() or 1)
DEFAULT_RECORDING_PROBE_CHUNKSIZE = 64
DEFAULT_RECORDING_PROBE_BATCH_SIZE = 4096


def trim_supervisions_to_recordings_sequentially(
    recordings,
    supervisions,
    output_path: Path,
) -> Dict[str, int]:
    """
    Streamingly align supervisions to recordings and trim any supervision whose
    end exceeds the corresponding recording duration.

    In this recipe, the recordings manifest order is preserved across stages,
    while transcript normalization may drop some supervisions. That means the
    supervisions are a subsequence of the recordings and can be aligned with a
    single forward pass without materializing a full recording-id index.
    """

    if output_path.exists():
        output_path.unlink()

    stats = {
        "trim_input_supervisions": 0,
        "trim_written_supervisions": 0,
        "trimmed_supervisions": 0,
        "removed_supervisions": 0,
        "skipped_recordings_without_supervision": 0,
    }

    recording_iter = iter(recordings)
    current_recording = next(recording_iter, None)
    previous_supervision_recording_id = None

    with SupervisionSet.open_writer(output_path) as writer:
        for sup in supervisions:
            stats["trim_input_supervisions"] += 1

            if previous_supervision_recording_id == sup.recording_id:
                raise ValueError(
                    "Expected at most one supervision per recording in Emilia "
                    f"stage 4, but saw multiple supervisions for recording_id="
                    f"{sup.recording_id}. "
                    "The sequential trimming logic relies on a 1:1 "
                    "recording-to-supervision mapping."
                )

            while (
                current_recording is not None
                and current_recording.id != sup.recording_id
            ):
                stats["skipped_recordings_without_supervision"] += 1
                current_recording = next(recording_iter, None)

            if current_recording is None:
                raise ValueError(
                    "Unable to align supervision "
                    f"{sup.id} with the recordings manifest. "
                    "This recipe expects normalized supervisions to remain "
                    "an ordered subsequence of recordings."
                )

            fixed_sup = sup
            if sup.start >= current_recording.duration:
                stats["removed_supervisions"] += 1
            else:
                if sup.end > current_recording.duration:
                    fixed_sup = sup.trim(end=current_recording.duration)
                    stats["trimmed_supervisions"] += 1

                if fixed_sup.duration <= 0:
                    stats["removed_supervisions"] += 1
                else:
                    writer.write(fixed_sup)
                    stats["trim_written_supervisions"] += 1

            previous_supervision_recording_id = sup.recording_id
            current_recording = next(recording_iter, None)

    return stats


def get_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--language",
        type=str,
        required=True,
        choices=["zh", "en"],
        help="Subset language to preprocess.",
    )
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        required=True,
        help="Input directory containing supervision manifests.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for normalized supervisions, fixed recordings, and raw cuts.",
    )
    parser.add_argument(
        "--recordings-manifest-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing recordings manifests to use when building raw cuts. "
            "If omitted, use --manifest-dir."
        ),
    )
    parser.add_argument(
        "--sample-rate-report",
        type=Path,
        default=DEFAULT_SAMPLE_RATE_REPORT,
        help=(
            "Path to the precomputed original sample-rate scan report. "
            "Used as a shortcut for uniform batches; mixed or unknown batches "
            "still probe the actual audio headers."
        ),
    )
    parser.add_argument(
        "--speed-perturb",
        action="store_true",
        help="Apply 0.9x/1.1x speed perturbation to the train split.",
    )
    parser.add_argument(
        "--recording-probe-workers",
        type=int,
        default=DEFAULT_RECORDING_PROBE_WORKERS,
        help=(
            "Number of worker processes to use for per-file audio-header probes "
            "when a batch cannot be resolved from the sample-rate report."
        ),
    )
    parser.add_argument(
        "--recording-probe-chunksize",
        type=int,
        default=DEFAULT_RECORDING_PROBE_CHUNKSIZE,
        help=(
            "Chunk size passed to ProcessPoolExecutor.map() for per-file "
            "audio-header probes."
        ),
    )
    return parser.parse_args()


def load_recordings(
    prefix: str, split: str, preferred_dir: Path, fallback_dir: Path
):
    candidate_dirs = [preferred_dir]
    if preferred_dir.resolve() != fallback_dir.resolve():
        candidate_dirs.append(fallback_dir)

    for manifest_dir in candidate_dirs:
        if split == "train":
            split_dirs = sorted(manifest_dir.glob("recordings_train_split_*"))
            for split_dir in split_dirs:
                pieces = sorted(
                    split_dir.glob(f"{prefix}_recordings_train.*.jsonl.gz")
                )
                if pieces:
                    logging.info(
                        "Loading %s train recording shards from %s",
                        len(pieces),
                        split_dir,
                    )
                    return lhotse.combine(
                        load_manifest_lazy_or_eager(p) for p in pieces
                    )

        recordings_path = manifest_dir / f"{prefix}_recordings_{split}.jsonl.gz"
        if not recordings_path.is_file():
            continue
        recordings = load_manifest_lazy_or_eager(recordings_path)
        if recordings is not None:
            logging.info("Using %s recordings from %s", split, recordings_path)
            return recordings

    return None


def load_sample_rate_plan(report_path: Path, language: str) -> Dict[str, Dict[str, object]]:
    language = validate_language(language).upper()
    if not report_path.is_file():
        logging.warning(
            "Sample-rate report %s is missing; falling back to per-file probes",
            report_path,
        )
        return {}

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    for language_entry in report.get("languages", []):
        if language_entry.get("language") != language:
            continue

        plan = {}
        for batch in language_entry.get("batches", []):
            plan[batch["batch"]] = {
                "status": batch.get("status", ""),
                "sample_rate_counts": {
                    int(sample_rate): int(count)
                    for sample_rate, count in batch.get(
                        "sample_rate_counts", {}
                    ).items()
                },
            }
        return plan

    logging.warning(
        "Sample-rate report %s does not contain language=%s; falling back to probes",
        report_path,
        language,
    )
    return {}


def extract_batch_id(source_path: str) -> Optional[str]:
    for part in Path(source_path).parts:
        if BATCH_ID_PATTERN.fullmatch(part):
            return part
    return None


def get_uniform_batch_sample_rate(
    batch_info: Optional[Dict[str, object]]
) -> Optional[int]:
    if not batch_info or batch_info.get("status") != "uniform":
        return None

    sample_rate_counts = batch_info.get("sample_rate_counts", {})
    if len(sample_rate_counts) != 1:
        return None

    sample_rate = next(iter(sample_rate_counts))
    if sample_rate not in (24000, 32000):
        return None
    return sample_rate


@lru_cache(maxsize=65536)
def probe_audio_info(source_path: str) -> Tuple[int, int]:
    info = torchaudio.info(source_path)
    if info.sample_rate <= 0 or info.num_frames <= 0:
        raise ValueError(f"Invalid audio info for {source_path}: {info}")
    return int(info.sample_rate), int(info.num_frames)


def build_fixed_recording(
    recording: Recording,
    sampling_rate: int,
    num_samples: int,
) -> Recording:
    source = recording.sources[0]
    return Recording(
        id=recording.id,
        sources=[
            AudioSource(
                type=source.type,
                channels=source.channels,
                source=source.source,
            )
        ],
        sampling_rate=sampling_rate,
        num_samples=num_samples,
        duration=num_samples / sampling_rate,
        channel_ids=recording.channel_ids,
        transforms=recording.transforms,
    )


def resolve_recording_metadata(
    recording: Recording,
    sample_rate_plan: Dict[str, Dict[str, object]],
) -> Tuple[Recording, str]:
    if len(recording.sources) != 1 or recording.sources[0].type != "file":
        return recording, "reused_original"

    source_path = str(recording.sources[0].source)
    batch_id = extract_batch_id(source_path)
    uniform_sample_rate = get_uniform_batch_sample_rate(sample_rate_plan.get(batch_id))

    if uniform_sample_rate is not None:
        num_samples = int(round(recording.duration * uniform_sample_rate))
        return (
            build_fixed_recording(
                recording=recording,
                sampling_rate=uniform_sample_rate,
                num_samples=num_samples,
            ),
            f"report_uniform_{uniform_sample_rate}",
        )

    sample_rate, num_frames = probe_audio_info(source_path)
    return (
        build_fixed_recording(
            recording=recording,
            sampling_rate=sample_rate,
            num_samples=num_frames,
        ),
        f"probed_{sample_rate}",
    )


def chunked_recordings(
    recordings: Iterable[Recording], chunk_size: int
) -> Iterator[List[Recording]]:
    recording_iter = iter(recordings)
    while True:
        chunk = list(islice(recording_iter, chunk_size))
        if not chunk:
            return
        yield chunk


def plan_recording_fix(
    recording: Recording,
    sample_rate_plan: Dict[str, Dict[str, object]],
) -> Tuple[str, Recording, str, Optional[str]]:
    if len(recording.sources) != 1 or recording.sources[0].type != "file":
        return "fixed", recording, "reused_original", None

    source_path = str(recording.sources[0].source)
    batch_id = extract_batch_id(source_path)
    uniform_sample_rate = get_uniform_batch_sample_rate(sample_rate_plan.get(batch_id))

    if uniform_sample_rate is not None:
        num_samples = int(round(recording.duration * uniform_sample_rate))
        return (
            "fixed",
            build_fixed_recording(
                recording=recording,
                sampling_rate=uniform_sample_rate,
                num_samples=num_samples,
            ),
            f"report_uniform_{uniform_sample_rate}",
            None,
        )

    return "probe", recording, "", source_path


def map_probe_audio_info(
    source_paths: List[str],
    probe_num_workers: int,
    probe_chunksize: int,
    executor: Optional[ProcessPoolExecutor] = None,
) -> Iterator[Tuple[int, int]]:
    if not source_paths:
        return iter(())

    if probe_num_workers <= 1:
        return map(probe_audio_info, source_paths)

    if executor is None:
        raise ValueError(
            "executor is required when probe_num_workers > 1"
        )
    return executor.map(
        probe_audio_info,
        source_paths,
        chunksize=probe_chunksize,
    )


def iter_fixed_recordings(
    recordings: Iterable[Recording],
    sample_rate_plan: Dict[str, Dict[str, object]],
    probe_num_workers: int,
    probe_chunksize: int,
) -> Iterator[Tuple[Recording, str]]:
    if probe_num_workers <= 0:
        raise ValueError("--recording-probe-workers must be > 0")
    if probe_chunksize <= 0:
        raise ValueError("--recording-probe-chunksize must be > 0")

    recording_batch_size = max(
        DEFAULT_RECORDING_PROBE_BATCH_SIZE,
        probe_num_workers * probe_chunksize,
    )
    executor = (
        ProcessPoolExecutor(max_workers=probe_num_workers)
        if probe_num_workers > 1
        else None
    )
    try:
        for recording_chunk in chunked_recordings(recordings, recording_batch_size):
            planned = []
            probe_paths = []
            for recording in recording_chunk:
                kind, payload, strategy, probe_path = plan_recording_fix(
                    recording=recording,
                    sample_rate_plan=sample_rate_plan,
                )
                planned.append((kind, payload, strategy))
                if probe_path is not None:
                    probe_paths.append(probe_path)

            probed_infos = iter(
                map_probe_audio_info(
                    source_paths=probe_paths,
                    probe_num_workers=probe_num_workers,
                    probe_chunksize=probe_chunksize,
                    executor=executor,
                )
            )
            for kind, payload, strategy in planned:
                if kind == "fixed":
                    yield payload, strategy
                    continue

                sample_rate, num_frames = next(probed_infos)
                yield (
                    build_fixed_recording(
                        recording=payload,
                        sampling_rate=sample_rate,
                        num_samples=num_frames,
                    ),
                    f"probed_{sample_rate}",
                )
    finally:
        if executor is not None:
            executor.shutdown()


def write_fixed_recordings(
    recordings,
    output_path: Path,
    sample_rate_plan: Dict[str, Dict[str, object]],
    probe_num_workers: int,
    probe_chunksize: int,
) -> Dict[str, int]:
    if output_path.exists():
        output_path.unlink()

    stats: Counter = Counter()
    with RecordingSet.open_writer(output_path) as writer:
        for fixed_recording, strategy in iter_fixed_recordings(
            recordings=recordings,
            sample_rate_plan=sample_rate_plan,
            probe_num_workers=probe_num_workers,
            probe_chunksize=probe_chunksize,
        ):
            stats["recordings_seen"] += 1
            writer.write(fixed_recording)
            stats[f"strategy_{strategy}"] += 1
            stats[f"sample_rate_{fixed_recording.sampling_rate}"] += 1
    return dict(stats)


def main():
    if not logging.getLogger().handlers:
        formatter = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s"
        logging.basicConfig(format=formatter, level=logging.INFO)

    args = get_args()
    if args.recording_probe_workers <= 0:
        raise ValueError("--recording-probe-workers must be > 0")
    if args.recording_probe_chunksize <= 0:
        raise ValueError("--recording-probe-chunksize must be > 0")
    language = validate_language(args.language)
    prefix = manifest_prefix(language)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    recordings_manifest_dir = args.recordings_manifest_dir or args.manifest_dir
    sample_rate_plan = load_sample_rate_plan(args.sample_rate_report, language)

    logging.info(
        "Stage4 recording probe config: workers=%s chunksize=%s",
        args.recording_probe_workers,
        args.recording_probe_chunksize,
    )

    summary = {}
    for split in ("train", "dev", "test"):
        supervisions_path = args.manifest_dir / f"{prefix}_supervisions_{split}.jsonl.gz"
        normalized_supervisions_path = (
            args.output_dir / f"{prefix}_supervisions_{split}_norm.jsonl.gz"
        )
        fixed_recordings_path = (
            args.output_dir / f"{prefix}_recordings_{split}_audio_fixed.jsonl.gz"
        )
        fixed_supervisions_path = (
            args.output_dir / f"{prefix}_supervisions_{split}_norm_fixed.jsonl.gz"
        )
        raw_cuts_path = args.output_dir / f"{prefix}_cuts_{split}_raw.jsonl.gz"

        for path in (
            normalized_supervisions_path,
            fixed_recordings_path,
            fixed_supervisions_path,
            raw_cuts_path,
        ):
            if path.exists():
                path.unlink()

        if not supervisions_path.exists():
            logging.warning(
                "Skipping %s split: %s does not exist", split, supervisions_path
            )
            summary[split] = {
                "total_supervisions": 0,
                "kept_supervisions": 0,
                "raw_cuts_path": str(raw_cuts_path),
            }
            continue

        total = 0
        kept = 0
        raw_sups = load_manifest_lazy_or_eager(supervisions_path)
        if raw_sups is None:
            if split in ("dev", "test"):
                logging.info(
                    "Skipping %s split: manifest is empty, which is expected "
                    "because Emilia recipe-local dev/test are disabled and "
                    "all Emilia utterances stay in train; use external "
                    "dev/eval cuts for validation or decoding.",
                    split,
                )
            else:
                logging.warning("Skipping %s split: manifest is empty", split)
            summary[split] = {
                "total_supervisions": 0,
                "kept_supervisions": 0,
                "raw_cuts_path": str(raw_cuts_path),
            }
            continue

        with SupervisionSet.open_writer(normalized_supervisions_path) as writer:
            for sup in raw_sups:
                total += 1
                normalized = canonicalize_text(sup.text, language)
                if not normalized:
                    continue
                sup.text = normalized
                writer.write(sup)
                kept += 1

        recordings = load_recordings(
            prefix=prefix,
            split=split,
            preferred_dir=recordings_manifest_dir,
            fallback_dir=args.manifest_dir,
        )
        supervisions = load_manifest_lazy_or_eager(normalized_supervisions_path)
        if recordings is None or supervisions is None:
            logging.warning(
                "Skipping %s split: recordings or supervisions empty after normalization",
                split,
            )
            summary[split] = {
                "total_supervisions": total,
                "kept_supervisions": kept,
                "raw_cuts_path": str(raw_cuts_path),
                "recordings_manifest_dir": str(recordings_manifest_dir),
            }
            continue

        recording_fix_stats = write_fixed_recordings(
            recordings=recordings,
            output_path=fixed_recordings_path,
            sample_rate_plan=sample_rate_plan,
            probe_num_workers=args.recording_probe_workers,
            probe_chunksize=args.recording_probe_chunksize,
        )
        fixed_recordings = load_manifest_lazy_or_eager(fixed_recordings_path)
        supervisions = load_manifest_lazy_or_eager(normalized_supervisions_path)
        if fixed_recordings is None or supervisions is None:
            raise ValueError(
                f"Failed to load normalized stage-4 inputs for split {split}: "
                f"recordings={fixed_recordings is not None}, "
                f"supervisions={supervisions is not None}"
            )

        trim_stats = trim_supervisions_to_recordings_sequentially(
            recordings=fixed_recordings,
            supervisions=supervisions,
            output_path=fixed_supervisions_path,
        )
        fixed_recordings = load_manifest_lazy_or_eager(fixed_recordings_path)
        supervisions = load_manifest_lazy_or_eager(fixed_supervisions_path)
        if fixed_recordings is None or supervisions is None:
            raise ValueError(
                f"Failed to reload fixed manifests for split {split}: "
                f"recordings={fixed_recordings is not None}, "
                f"supervisions={supervisions is not None}"
            )

        cuts = CutSet.from_manifests(
            recordings=fixed_recordings,
            supervisions=supervisions,
        )
        if split == "train" and args.speed_perturb:
            cuts = cuts + cuts.perturb_speed(0.9) + cuts.perturb_speed(1.1)

        cuts.to_file(raw_cuts_path)
        summary[split] = {
            "total_supervisions": total,
            "kept_supervisions": kept,
            "raw_cuts_path": str(raw_cuts_path),
            "recordings_manifest_dir": str(recordings_manifest_dir),
            "fixed_recordings_path": str(fixed_recordings_path),
            "fixed_supervisions_path": str(fixed_supervisions_path),
            "sample_rate_report": str(args.sample_rate_report),
            "recording_probe_workers": args.recording_probe_workers,
            "recording_probe_chunksize": args.recording_probe_chunksize,
            **recording_fix_stats,
            **trim_stats,
        }
        logging.info(
            "Prepared %s split: kept %s/%s supervisions, trimmed=%s removed=%s",
            split,
            kept,
            total,
            trim_stats["trimmed_supervisions"],
            trim_stats["removed_supervisions"],
        )

    summary_path = args.output_dir / f"{prefix}_preprocess_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logging.info("Wrote preprocess summary to %s", summary_path)


if __name__ == "__main__":
    main()
